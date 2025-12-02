import logging
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from src.llm.manager import LLMManager
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LLM Service", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Manager
llm_manager = LLMManager()

# Models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None

class LoadModelRequest(BaseModel):
    model_path: str
    n_ctx: Optional[int] = None
    n_gpu_layers: Optional[int] = None
    n_threads: Optional[int] = None
    n_cpu_moe: Optional[int] = None

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "llm"}

@app.get("/v1/models")
async def list_loaded_models():
    """List loaded models (OpenAI compatible)."""
    if llm_manager.is_model_loaded():
        return {
            "object": "list",
            "data": [{
                "id": llm_manager.current_model_name,
                "object": "model",
                "created": 0,
                "owned_by": "user"
            }]
        }
    return {"object": "list", "data": ["no model loaded"]}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Generate chat completion."""
    if not llm_manager.is_model_loaded():
        raise HTTPException(status_code=503, detail="No model loaded")
    
    # Convert messages to dict
    history = [msg.model_dump() for msg in request.messages[:-1]]
    message = request.messages[-1].content
    
    # Update settings if provided
    settings_update = {}
    if request.temperature is not None: settings_update["temperature"] = request.temperature
    if request.top_p is not None: settings_update["top_p"] = request.top_p
    if request.max_tokens is not None: settings_update["max_tokens"] = request.max_tokens
    
    if settings_update:
        llm_manager.update_settings(settings_update)
        
    try:
        response = await llm_manager.generate_response(
            message=message,
            history=history,
            stream=request.stream
        )
        
        if request.stream:
            from fastapi.responses import StreamingResponse
            return StreamingResponse(response["stream"], media_type="text/event-stream")
            
        # Format response as OpenAI object
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 0,
            "model": llm_manager.current_model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response["response"],
                    "tool_calls": response.get("tool_calls")
                },
                "finish_reason": "stop"
            }]
        }
        
    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Management Endpoints

@app.get("/api/models")
async def list_available_models():
    """List all available GGUF models on disk."""
    models = []
    if settings.models_dir.exists():
        import re
        # Regex to parse common GGUF filenames
        # e.g. llama-2-7b-chat.Q4_K_M.gguf
        # e.g. mistral-7b-instruct-v0.1.Q5_K_M.gguf
        # Group 1: Name, Group 2: Quantization
        name_pattern = re.compile(r'(.+?)[.-]([qQ]\d+[_a-zA-Z0-9]*|f16|f32)\.gguf$')
        
        for f in settings.models_dir.glob("**/*.gguf"):
            stat = f.stat()
            size_mb = stat.st_size / (1024 * 1024)
            size_gb = size_mb / 1024
            
            # Parse filename
            match = name_pattern.search(f.name)
            if match:
                clean_name = match.group(1).replace("-", " ").title()
                quant = match.group(2).upper()
            else:
                clean_name = f.stem.replace("-", " ").title()
                quant = "Unknown"
            
            # Heuristics for parameters
            params = "Unknown"
            if "7b" in f.name.lower(): params = "7B"
            elif "13b" in f.name.lower(): params = "13B"
            elif "30b" in f.name.lower(): params = "30B"
            elif "34b" in f.name.lower(): params = "34B"
            elif "70b" in f.name.lower(): params = "70B"
            elif "8x7b" in f.name.lower(): params = "8x7B (MoE)"
            
            models.append({
                "id": f.name,
                "name": clean_name,
                "path": str(f),
                "size": stat.st_size,
                "size_formatted": f"{size_gb:.2f} GB" if size_gb >= 1 else f"{size_mb:.0f} MB",
                "quantization": quant,
                "parameters": params,
                "modified": stat.st_mtime
            })
    return models

@app.post("/api/models/load")
async def load_model(request: LoadModelRequest):
    """Load a model."""
    success = await llm_manager.load_model(
        model_path=request.model_path,
        n_ctx=request.n_ctx,
        n_gpu_layers=request.n_gpu_layers,
        n_threads=request.n_threads,
        n_cpu_moe=request.n_cpu_moe
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load model")
    return {"status": "success", "message": f"Loaded {request.model_path}"}

@app.post("/api/models/unload")
async def unload_model():
    """Unload current model."""
    await llm_manager.unload_model()
    return {"status": "success"}

@app.get("/api/memory")
async def get_memory_info():
    """Get VRAM/RAM info."""
    # TODO: Implement memory calculator endpoint
    return {"status": "not_implemented"}

@app.get("/api/models/search")
async def search_models(query: str, limit: int = 20):
    """Search HuggingFace models."""
    return await llm_manager.downloader.search_models(query, limit)

@app.post("/api/models/download")
async def download_model(repo_id: str, filename: Optional[str] = None):
    """Download a model."""
    try:
        path = await llm_manager.downloader.download_model(repo_id, filename)
        return {"status": "success", "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a model."""
    try:
        success = llm_manager.downloader.delete_model(model_id)
        if not success:
            raise HTTPException(status_code=404, detail="Model not found")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/models/{model_id}/info")
async def get_model_info(model_id: str):
    """Get model info."""
    try:
        # This is a simplified version, real implementation might need ModelInfoExtractor
        return {"id": model_id, "info": "not_implemented_remotely_yet"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
