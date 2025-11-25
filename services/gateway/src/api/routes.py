"""API route handlers."""
from typing import List, Optional, Dict, Any
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import Response

from ..api.schemas import (
    ChatRequest, ChatResponse, ConversationHistory,
    STTResponse, TTSRequest,
    AISettings, AISettingsResponse, ModelInfo, ModelLoadOptions, CharacterCard, UserProfile,
    ModelMetadata, MemoryEstimate, MessageMetadata, ConversationRenameRequest
)
from ..services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint - simple and fast, no blocking operations."""
    # Keep this endpoint simple and fast - don't check services that might block
    return {
        "status": "healthy",
        "service": "personal-assistant",
        "message": "Backend is running"
    }


@router.get("/api/services/status")
async def get_services_status():
    """Get real-time status for all services from cached polling data."""
    if not service_manager.status_manager:
        raise HTTPException(
            status_code=503,
            detail="Status manager not initialized"
        )
    
    all_statuses = service_manager.status_manager.get_all_statuses()
    
    # Organize by service type for frontend consumption
    return {
        "stt": all_statuses.get("stt", {"status": "offline"}),
        "tts": {
            "piper": all_statuses.get("tts_piper", {"status": "offline"}),
            "chatterbox": all_statuses.get("tts_chatterbox", {"status": "offline"}),
            "kokoro": all_statuses.get("tts_kokoro", {"status": "offline"}),
        },
        "llm": all_statuses.get("llm", {"status": "offline"}),
        "last_poll": max(
            (s.get("last_check") for s in all_statuses.values() if s.get("last_check")),
            default=None
        )
    }


@router.get("/api/system/info")
async def get_system_info():
    """Get system information including CPU count and GPU info."""
    import os
    import multiprocessing
    
    cpu_count = os.cpu_count() or multiprocessing.cpu_count()
    
    # Get GPU information if available
    gpu_info = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpus = []
            for i in range(gpu_count):
                props = torch.cuda.get_device_properties(i)
                gpus.append({
                    "id": i,
                    "name": props.name,
                    "total_memory_gb": props.total_memory / (1024**3),
                    "compute_capability": f"{props.major}.{props.minor}"
                })
            gpu_info = {
                "available": True,
                "count": gpu_count,
                "cuda_version": torch.version.cuda,
                "devices": gpus
            }
            
            # Check if llama-cpp-python supports CUDA
            from ..services.llm.cuda_installer import check_llama_cuda_support
            has_llama_cuda, error = check_llama_cuda_support()
            gpu_info["llama_cpp_cuda"] = has_llama_cuda
            if not has_llama_cuda:
                gpu_info["warning"] = "CUDA available but llama-cpp-python not compiled with CUDA support"
                
        else:
            gpu_info = {"available": False, "reason": "CUDA not available"}
    except ImportError:
        gpu_info = {"available": False, "reason": "PyTorch not installed"}
    except Exception as e:
        gpu_info = {"available": False, "reason": str(e)}
    
    return {
        "cpu_count": cpu_count,
        "cpu_threads_available": cpu_count,  # Logical cores = thread count
        "platform": os.name,
        "system": os.uname().system if hasattr(os, 'uname') else "unknown",
        "gpu": gpu_info
    }


@router.get("/api/system/status")
async def get_system_status():
    """Get real-time system status including per-service RAM/VRAM usage."""
    from ..services.system_monitor import system_monitor
    return system_monitor.get_status()
@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat request."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    if not service_manager.llm_manager or not await service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded. Please load a model first."
        )
    
    try:
        import time
        start_time = time.time()
        
        # Apply settings from request if provided
        if request.character_card:
            character_card_dict = {
                "name": request.character_card.name,
                "personality": request.character_card.personality,
                "background": request.character_card.background,
                "instructions": request.character_card.instructions
            }
            service_manager.llm_manager.update_character_card(character_card_dict)
        
        if request.user_profile:
            user_profile_dict = {
                "name": request.user_profile.name,
                "about": request.user_profile.about,
                "preferences": request.user_profile.preferences
            }
            service_manager.llm_manager.update_user_profile(user_profile_dict)
        
        # Apply sampler settings if provided
        settings_dict = {}
        if request.temperature is not None:
            settings_dict["temperature"] = request.temperature
        if request.top_p is not None:
            settings_dict["top_p"] = request.top_p
        if request.top_k is not None:
            settings_dict["top_k"] = request.top_k
        if request.repeat_penalty is not None:
            settings_dict["repeat_penalty"] = request.repeat_penalty
        
        if settings_dict:
            service_manager.llm_manager.update_settings(settings_dict)
        
        # Get current settings for metadata
        current_settings = service_manager.llm_manager.get_settings()
        
        result = await service_manager.chat_manager.send_message(
            message=request.message,
            conversation_id=request.conversation_id
        )
        
        # Calculate generation time
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Create metadata
        metadata = MessageMetadata(
            model_name=service_manager.llm_manager.current_model_name,
            generation_time_ms=round(generation_time_ms, 2),
            context_length=service_manager.llm_manager.loader._n_ctx if service_manager.llm_manager.loader else None,
            temperature=current_settings.get("temperature"),
            top_p=current_settings.get("top_p"),
            top_k=current_settings.get("top_k"),
            repeat_penalty=current_settings.get("repeat_penalty"),
            retrieved_context=result.get("context_used", []),
            n_threads=load_options.get("n_threads"),
            n_gpu_layers=load_options.get("n_gpu_layers"),
            use_flash_attention=load_options.get("use_flash_attention"),
            flash_attn=load_options.get("flash_attn", False),
            use_mmap=load_options.get("use_mmap"),
            use_mlock=load_options.get("use_mlock"),
            n_batch=load_options.get("n_batch"),
            n_predict=load_options.get("n_predict"),
            rope_freq_base=load_options.get("rope_freq_base"),
            rope_freq_scale=load_options.get("rope_freq_scale"),
            main_gpu=load_options.get("main_gpu", 0),
            tensor_split=load_options.get("tensor_split"),
            n_cpu_moe=load_options.get("n_cpu_moe")
        )
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            context_used=result.get("context_used", []),
            tool_calls=result.get("tool_calls"),
            metadata=metadata
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


@router.post("/api/conversations/new")
async def create_conversation():
    """Create a new conversation."""
    logger.info("POST /api/conversations/new - Creating new conversation")
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        conversation_id = await service_manager.chat_manager.create_conversation()
        name = await service_manager.chat_manager.get_conversation_name(conversation_id)
        logger.info(f"Created conversation: {conversation_id} ({name})")
        return {
            "conversation_id": conversation_id,
            "name": name,
            "status": "created"
        }
    except Exception as e:
        logger.error(f"Error creating conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}") from e


@router.get("/api/conversations", response_model=List[ConversationHistory])
async def list_conversations():
    """List all conversations."""
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        # Get conversations from persistent storage (includes names)
        stored_conversations = await service_manager.memory_store.list_conversations()
        logger.info(f"Found {len(stored_conversations)} conversations in database")
        conversations = []
        
        for conv_data in stored_conversations:
            conv_id = conv_data["conversation_id"]
            try:
                messages = await service_manager.chat_manager.get_conversation(conv_id)
                if messages is None:
                    messages = []
                
                # Convert to ChatMessage format
                chat_messages = [
                    {
                        "role": msg.get("role", "unknown"),
                        "content": msg.get("content", ""),
                        "timestamp": msg.get("timestamp")
                    }
                    for msg in messages
                ]
                
                # Get conversation name
                name = conv_data.get("name") or await service_manager.chat_manager.get_conversation_name(conv_id)
                
                conversations.append(ConversationHistory(
                    conversation_id=conv_id,
                    messages=chat_messages,
                    name=name,
                    created_at=conv_data.get("created_at"),
                    updated_at=conv_data.get("updated_at")
                ))
            except Exception as e:
                logger.error(f"Error loading conversation {conv_id}: {e}", exc_info=True)
                # Still include the conversation even if messages fail to load
                conversations.append(ConversationHistory(
                    conversation_id=conv_id,
                    messages=[],
                    name=conv_data.get("name"),
                    created_at=conv_data.get("created_at"),
                    updated_at=conv_data.get("updated_at")
                ))
        
        # Sort by updated_at descending (most recent first)
        conversations.sort(key=lambda x: x.updated_at or "", reverse=True)
        logger.info(f"Returning {len(conversations)} conversations")
        return conversations
    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list conversations: {str(e)}"
        ) from e


@router.get("/api/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation(conversation_id: str):
    """Get conversation by ID."""
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    # Check if conversation exists (even if empty)
    messages = await service_manager.chat_manager.get_conversation(conversation_id)
    if messages is None:  # None means conversation doesn't exist, [] means it exists but is empty
        logger.warning(f"Conversation {conversation_id} not found")
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Get conversation metadata from database
    stored_conversations = await service_manager.memory_store.list_conversations()
    conv_metadata = next((c for c in stored_conversations if c["conversation_id"] == conversation_id), None)
    
    chat_messages = [
        {
            "role": msg.get("role", "unknown"),
            "content": msg.get("content", ""),
            "timestamp": msg.get("timestamp")
        }
        for msg in messages
    ]
    
    # Get conversation name
    name = conv_metadata.get("name") if conv_metadata else await service_manager.chat_manager.get_conversation_name(conversation_id)
    
    return ConversationHistory(
        conversation_id=conversation_id,
        messages=chat_messages,
        name=name,
        created_at=conv_metadata.get("created_at") if conv_metadata else (messages[0].get("timestamp") if messages else None),
        updated_at=conv_metadata.get("updated_at") if conv_metadata else (messages[-1].get("timestamp") if messages else None)
    )


@router.post("/api/voice/stt", response_model=STTResponse)
async def speech_to_text(
    audio: UploadFile = File(...),
    language: Optional[str] = None
):
    """Convert speech to text."""
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="STT service not initialized"
        )
    
    try:
        # Save uploaded file temporarily
        import tempfile
        import aiofiles
        from pathlib import Path
        
        # Get file extension
        file_ext = Path(audio.filename).suffix if audio.filename else ".wav"
        
        with tempfile.NamedTemporaryFile(
            suffix=file_ext,
            delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        # Write uploaded file to temp file
        async with aiofiles.open(tmp_path, 'wb') as f:
            content = await audio.read()
            await f.write(content)
        
        try:
            # Transcribe audio
            text, detected_language = await service_manager.stt_service.transcribe(
                tmp_path,
                language=language
            )
            
            return STTResponse(
                text=text,
                language=detected_language
            )
        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()
    
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Audio file error: {str(e)}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"STT error: {str(e)}"
        ) from e


@router.post("/api/voice/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty"
        )
    
    try:
        # Synthesize speech
        audio_data = await service_manager.tts_service.synthesize(
            text=request.text,
            voice=request.voice,
            output_format="wav"
        )
        
        # Return audio as streaming response
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"TTS error: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends")
async def get_tts_backends():
    """Get list of all available TTS backends with their status."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        backends = service_manager.tts_service.get_available_backends()
        return {"backends": backends}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backends: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}")
async def get_tts_backend_info(backend_name: str):
    """Get detailed information about a specific TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        info = await service_manager.tts_service.get_backend_info(backend_name)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backend info: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/{backend_name}/switch")
async def switch_tts_backend(backend_name: str):
    """Switch to a different TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        success = await service_manager.tts_service.switch_backend(backend_name)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Save backend selection to settings
        await service_manager.memory_store.set_setting("tts_backend", backend_name)
        
        # Return updated backend info (even if initialization failed)
        info = await service_manager.tts_service.get_backend_info(backend_name)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Determine message based on backend status
        if info.get("status") == "ready":
            message = f"Switched to TTS backend: {backend_name}"
            status = "success"
        elif info.get("status") == "error":
            message = f"Switched to TTS backend: {backend_name} (initialization failed: {info.get('error_message', 'Unknown error')})"
            status = "warning"
        else:
            message = f"Switched to TTS backend: {backend_name}"
            status = "success"
        
        return {
            "status": status,
            "message": message,
            "backend_info": info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error switching TTS backend: {str(e)}"
        )

@router.post("/api/voice/tts/backends/{backend_name}/start")
async def start_tts_backend(backend_name: str):
    """Start a TTS backend service (if supported)."""
    backend = service_manager.tts_service.manager.get_backend(backend_name)
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    
    if hasattr(backend, "start_service"):
        success = await backend.start_service()
        if success:
            # Re-initialize to update status
            await backend.initialize()
            return {"status": "success", "message": f"Started {backend_name} service"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start {backend_name} service")
    
    return {"status": "ignored", "message": "Service control not supported for this backend"}





@router.get("/api/voice/tts/backends/{backend_name}/voices")
async def get_tts_voices(backend_name: str):
    """Get available voices for a TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        voices = await service_manager.tts_service.get_available_voices(backend_name)
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS voices: {str(e)}"
        ) from e


@router.put("/api/voice/tts/backends/{backend_name}/options")
async def set_tts_backend_options(backend_name: str, options: dict):
    """Set options for a TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        success = service_manager.tts_service.set_backend_options(backend_name, options)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to set options for TTS backend '{backend_name}'"
            )
        
        # Return updated backend info
        info = service_manager.tts_service.get_backend_info(backend_name)
        return {
            "status": "success",
            "message": f"Options updated for TTS backend: {backend_name}",
            "backend": info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting TTS backend options: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}/models")
async def get_tts_backend_models(backend_name: str):
    """Get available models for a TTS backend (e.g., Coqui)."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        backend = service_manager.tts_service.manager.get_backend(backend_name)
        if not backend:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Check if backend has get_available_models method
        if hasattr(backend, 'get_available_models'):
            models = backend.get_available_models()
            return {"models": models}
        else:
            return {"models": []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backend models: {str(e)}"
        ) from e


@router.get("/api/voice/tts/settings")
async def get_tts_settings():
    """Get all TTS settings including current backend, voices, and options."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        current_backend = service_manager.tts_service.get_current_backend_name()
        backends = service_manager.tts_service.get_available_backends()
        
        # Get detailed info for current backend
        current_info = None
        if service_manager.tts_service.manager.current_backend:
            current_info = await service_manager.tts_service.get_backend_info(current_backend)
        
        return {
            "current_backend": current_backend,
            "current_backend_info": current_info,
            "available_backends": backends
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS settings: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}/health")
async def check_tts_backend_health(backend_name: str):
    """Check if a TTS backend service is running and accessible."""
    # Map backend names to their service URLs
    service_urls = {
        "piper": "http://localhost:8004",
        "whisper": "http://localhost:8003",  # STT service for reference
        "chatterbox": "http://localhost:4123",
        "kokoro": "http://localhost:8880"
    }
    
    
    # Special handling for OpenAI backend - test actual API connectivity
    if backend_name == "openai":
        if service_manager.tts_service:
            backend = service_manager.tts_service.manager.backends.get("openai")
            if backend and hasattr(backend, 'api_url') and backend.api_url:
                # Test actual API connectivity with a minimal request
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        # Try to list models as a connectivity test
                        headers = {}
                        if hasattr(backend, 'api_key') and backend.api_key:
                            headers["Authorization"] = f"Bearer {backend.api_key}"
                        
                        test_url = f"{backend.api_url.rstrip('/')}/v1/models"
                        resp = await client.get(test_url, headers=headers)
                        
                        if resp.status_code == 200:
                            return {
                                "accessible": True,
                                "is_service": False,
                                "is_external": True,
                                "status": "API endpoint accessible",
                                "url": backend.api_url,
                                "authenticated": bool(backend.api_key)
                            }
                        elif resp.status_code == 401:
                            return {
                                "accessible": False,
                                "is_service": False,
                                "is_external": True,
                                "error": "Authentication failed - invalid API key",
                                "url": backend.api_url,
                                "status_code": 401
                            }
                        else:
                            return {
                                "accessible": False,
                                "is_service": False,
                                "is_external": True,
                                "error": f"API returned status {resp.status_code}",
                                "url": backend.api_url,
                                "status_code": resp.status_code
                            }
                except httpx.TimeoutException:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": "Connection timeout - API endpoint not responding",
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
                except httpx.ConnectError:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": "Connection failed - cannot reach API endpoint",
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
                except Exception as e:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": str(e),
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
            else:
                return {
                    "accessible": False,
                    "is_service": False,
                    "is_external": True,
                    "error": "OpenAI backend not configured - no API URL set",
                    "needs_configuration": True
                }
        return {
            "accessible": False,
            "is_service": False,
            "is_external": True,
            "reason": "TTS service not initialized"
        }
    
    # Other non-service backends (pyttsx3, etc.)
    if backend_name not in service_urls:
        # For pyttsx3, etc. - check if backend exists and is initialized
        if service_manager.tts_service:
            backend = service_manager.tts_service.manager.backends.get(backend_name)
            if backend:
                return {
                    "accessible": True,
                    "is_service": False,
                    "status": "Local backend - no service required"
                }
        return {
            "accessible": False,
            "is_service": False,
            "reason": "Backend not found"
        }

    
    # Check service-based backends
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{service_urls[backend_name]}/health")
            return {
                "accessible": resp.status_code == 200,
                "is_service": True,
                "status_code": resp.status_code,
                "url": service_urls[backend_name]
            }
    except httpx.TimeoutException:
        return {
            "accessible": False,
            "is_service": True,
            "error": "Connection timeout",
            "url": service_urls[backend_name]
        }
    except httpx.ConnectError:
        return {
            "accessible": False,
            "is_service": True,
            "error": "Service not running",
            "url": service_urls[backend_name]
        }
    except Exception as e:
        return {
            "accessible": False,
            "is_service": True,
            "error": str(e),
            "url": service_urls[backend_name]
        }


@router.get("/api/voice/tts/backends/chatterbox/service")
async def get_chatterbox_service_status():
    """Get Chatterbox TTS API service status."""
    try:
        from ..services.external.chatterbox_service import chatterbox_service
        return chatterbox_service.get_status()
    except Exception as e:
        logger.error(f"Error getting Chatterbox service status: {e}", exc_info=True)
        # Return a safe default status
        return {
            "status": "error",
            "is_running": False,
            "api_url": None,
            "frontend_url": None,
            "installed": False,
            "dependencies_installed": False,
            "device": "unknown",
            "cuda_available": False,
            "gpu_name": None,
            "pytorch_version": None,
            "error_message": str(e),
            "base_dir": None
        }


@router.post("/api/voice/tts/backends/chatterbox/service/install")
async def install_chatterbox_service(background_tasks: BackgroundTasks):
    """Install Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    
    # Check if already installing
    status = chatterbox_service.get_status()
    if status.get("is_installing"):
        return {"status": "started", "message": "Installation already in progress"}
    
    # Start installation in background
    background_tasks.add_task(chatterbox_service.install)
    
    return {"status": "started", "message": "Installation started in background"}


@router.post("/api/voice/tts/backends/chatterbox/service/start")
async def start_chatterbox_service():
    """Start Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.start()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/stop")
async def stop_chatterbox_service():
    """Stop Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.stop()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/restart")
async def restart_chatterbox_service():
    """Restart Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.restart()
    return result


@router.get("/api/voice/tts/backends/chatterbox/service/logs")
async def get_chatterbox_service_logs():
    """Get Chatterbox TTS API service logs."""
    from ..services.external.chatterbox_service import chatterbox_service
    return {"logs": chatterbox_service.get_logs()}


@router.get("/api/voice/stt/settings")
async def get_stt_settings():
    """Get all STT settings from cached status."""
    try:
        # Ensure proxy exists (it should be always on now)
        if not service_manager.stt_service:
            service_manager.enable_stt()
        
        if not service_manager.status_manager:
            # Fallback if status manager not initialized
            return {
                "status": "offline",
                "provider": "Whisper",
                "model_size": True,
                "available_languages": ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "hi"],
                "default_language": "en",
                "model_initialized": False
            }
        
        stt_service = service_manager.stt_service
        
        # Get cached status instead of real-time check
        cached_status = service_manager.status_manager.get_service_status("stt") or {}
        is_healthy = cached_status.get("status") == "ready"
            
        # Return info with cached status
        return {
            "status": "ready" if is_healthy else "offline",
            "provider": stt_service.provider,
            "model_size": True,
            "available_languages": ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "hi"],
            "default_language": "en",
            "model_initialized": is_healthy,
            "last_check": cached_status.get("last_check"),
            "response_time_ms": cached_status.get("response_time_ms")
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting STT settings: {str(e)}"
        ) from e


@router.post("/api/voice/stt/initialize")
async def initialize_stt():
    """Initialize STT service (loads model on demand)."""
    # Enable STT service if not already enabled
    service_manager.enable_stt()
    
    # Persist setting so it auto-starts next time
    if service_manager.memory_store:
        await service_manager.memory_store.update_setting("stt_enabled", "true")
    
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="Failed to enable STT service"
        )
    
    try:
        stt_service = service_manager.stt_service
        # For remote service, we assume it's initialized if the object exists
        # The actual remote service (Whisper) should be running
        
        return {
            "status": "success",
            "message": "STT service initialized successfully",
            "initialized": True,
            "provider": stt_service.provider
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error initializing STT service: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error initializing STT service: {error_msg}"
        ) from e


@router.post("/api/voice/tts/backends/openai/config")
async def configure_openai_tts(config: Dict[str, str]):
    """Configure OpenAI TTS backend."""
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    
    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="api_url and api_key are required")
    
    # Save to settings
    await service_manager.memory_store.set_setting("tts_openai_url", api_url)
    await service_manager.memory_store.set_setting("tts_openai_key", api_key, encrypted=True)
    
    # Configure the backend
    backend = service_manager.tts_service.manager.backends.get("openai")
    if backend:
        backend.configure(api_url, api_key)
        await backend.initialize()
    
    return {"status": "success", "message": "OpenAI TTS configured"}


@router.post("/api/voice/stt/config")
async def configure_stt(config: Dict[str, str]):
    """Configure STT service (Whisper or OpenAI)."""
    provider = config.get("provider", "whisper")
    enabled = config.get("enabled", "true")
    
    # Save settings
    await service_manager.memory_store.set_setting("stt_provider", provider)
    await service_manager.memory_store.set_setting("stt_enabled", enabled)
    
    if provider == "openai":
        api_url = config.get("api_url")
        api_key = config.get("api_key")
        
        if api_url and api_key:
            await service_manager.memory_store.set_setting("stt_openai_url", api_url)
            await service_manager.memory_store.set_setting("stt_openai_key", api_key, encrypted=True)
    
    return {"status": "success", "message": "STT configured", "provider": provider, "enabled": enabled}


@router.get("/api/voice/config")
async def get_voice_config():
    """Get current voice service configuration."""
    tts_backend = await service_manager.memory_store.get_setting("tts_backend", "pyttsx3")
    stt_enabled = await service_manager.memory_store.get_setting("stt_enabled", "false")
    stt_provider = await service_manager.memory_store.get_setting("stt_provider", "whisper")
    
    # Get OpenAI config (don't expose keys, just indicate if configured)
    tts_openai_url = await service_manager.memory_store.get_setting("tts_openai_url")
    stt_openai_url = await service_manager.memory_store.get_setting("stt_openai_url")
    
    return {
        "tts": {
            "backend": tts_backend,
            "openai_configured": bool(tts_openai_url)
        },
        "stt": {
            "enabled": stt_enabled == "true",
            "provider": stt_provider,
            "openai_configured": bool(stt_openai_url)
        }
    }



@router.get("/api/settings", response_model=AISettingsResponse)
async def get_settings():
    """Get current AI settings."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    settings_dict = service_manager.llm_manager.get_settings()
    system_prompt = service_manager.llm_manager.get_system_prompt()
    character_card = service_manager.llm_manager.get_character_card()
    user_profile = service_manager.llm_manager.get_user_profile()
    model_loaded = await service_manager.llm_manager.is_model_loaded()
    current_model = service_manager.llm_manager.get_current_model_path()
    
    default_load_options = service_manager.llm_manager.get_default_load_options()
    
    return AISettingsResponse(
        settings=AISettings(
            temperature=settings_dict["temperature"],
            top_p=settings_dict["top_p"],
            top_k=settings_dict["top_k"],
            repeat_penalty=settings_dict["repeat_penalty"],
            system_prompt=system_prompt,
            character_card=CharacterCard(**character_card) if character_card else None,
            user_profile=UserProfile(**user_profile) if user_profile else None,
            default_load_options=ModelLoadOptions(**default_load_options) if default_load_options else None
        ),
        model_loaded=model_loaded,
        current_model=current_model
    )


@router.put("/api/settings", response_model=AISettingsResponse)
async def update_settings(settings_update: AISettings):
    """Update AI settings."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Update sampler settings
    settings_dict = {}
    if settings_update.temperature is not None:
        settings_dict["temperature"] = settings_update.temperature
    if settings_update.top_p is not None:
        settings_dict["top_p"] = settings_update.top_p
    if settings_update.top_k is not None:
        settings_dict["top_k"] = settings_update.top_k
    if settings_update.repeat_penalty is not None:
        settings_dict["repeat_penalty"] = settings_update.repeat_penalty
    
    if settings_dict:
        service_manager.llm_manager.update_settings(settings_dict)
    
    # Update system prompt if provided
    if settings_update.system_prompt is not None:
        service_manager.llm_manager.update_system_prompt(settings_update.system_prompt)
    
    # Update character card if provided
    if settings_update.character_card is not None:
        character_card_dict = {
            "name": settings_update.character_card.name,
            "personality": settings_update.character_card.personality,
            "background": settings_update.character_card.background,
            "instructions": settings_update.character_card.instructions
        }
        service_manager.llm_manager.update_character_card(character_card_dict)
    
    # Update user profile if provided
    if settings_update.user_profile is not None:
        user_profile_dict = {
            "name": settings_update.user_profile.name,
            "about": settings_update.user_profile.about,
            "preferences": settings_update.user_profile.preferences
        }
        service_manager.llm_manager.update_user_profile(user_profile_dict)
    
    # Return updated settings
    return await get_settings()


@router.get("/api/models", response_model=List[ModelInfo])
async def list_models():
    """List available/downloaded models."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_infos = []
    
    for model_path in downloaded_models:
        try:
            info = service_manager.llm_manager.downloader.get_model_info(model_path)
            model_infos.append(ModelInfo(
                model_id=model_path.name,
                name=info["name"],
                size=f"{info['size_gb']} GB" if info['size_gb'] >= 1 else f"{info['size_mb']} MB",
                format="gguf",
                downloaded=True
            ))
        except Exception:
            # Skip models that can't be read
            continue
    
    return model_infos


@router.get("/api/models/files")
async def get_model_files(repo_id: str = Query(..., description="HuggingFace repository ID")):
    """Get list of files in a HuggingFace model repository."""
    logger.info("get_model_files called with repo_id: %s", repo_id)
    
    if not service_manager.llm_manager:
        logger.error("LLM manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    try:
        # URL decode the repo_id in case it was double-encoded
        from urllib.parse import unquote
        decoded_repo_id = unquote(repo_id)
        logger.info("Decoded repo_id: %s", decoded_repo_id)
        
        # Additional validation: ensure repo_id has proper format
        if not decoded_repo_id or not decoded_repo_id.strip():
            logger.warning("Empty repo_id after decoding")
            raise HTTPException(
                status_code=400,
                detail="Repository ID cannot be empty"
            )
        
        # Validate format (should contain at least one slash)
        if '/' not in decoded_repo_id:
            logger.warning("Invalid repo_id format (no slash): %s", decoded_repo_id)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repository ID format: '{decoded_repo_id}'. Expected format: 'username/model-name'"
            )
        
        logger.info("Calling downloader.get_model_files with: %s", decoded_repo_id)
        files = await service_manager.llm_manager.downloader.get_model_files(
            repo_id=decoded_repo_id
        )
        logger.info("Successfully retrieved %d files", len(files) if files else 0)
        return files
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Repository not found or invalid format
        error_msg = str(e)
        logger.warning("Invalid repository ID or not found: %s (decoded: %s) - %s", repo_id, decoded_repo_id, error_msg)
        # Check if it's actually a 404 or just a validation error
        if "not found" in error_msg.lower() or "not found on HuggingFace" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from e
        else:
            # Validation error, return 400
            raise HTTPException(status_code=400, detail=error_msg) from e
    except Exception as e:
        import traceback
        error_detail = f"Failed to list files for repository '{repo_id}': {str(e)}"
        logger.error("Error listing files: %s\n%s", error_detail, traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail) from e


@router.post("/api/models/download")
async def download_model(
    repo_id: str = Query(..., description="HuggingFace repository ID"),
    filename: Optional[str] = Query(None, description="Specific GGUF filename to download")
):
    """Download model from HuggingFace."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    try:
        model_path = await service_manager.llm_manager.downloader.download_model(
            repo_id=repo_id,
            filename=filename
        )
        
        return {
            "status": "success",
            "message": "Model downloaded successfully",
            "model_path": str(model_path),
            "model_id": model_path.name
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}") from e


@router.post("/api/models/{model_id}/load")
async def load_model(
    model_id: str,
    options: Optional[ModelLoadOptions] = None
):
    """Load a model for inference with optional configuration.
    
    Args:
        model_id: Model identifier or filename
        options: Optional model loading configuration
    """
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        # Try as direct path
        from pathlib import Path
        potential_path = Path(model_id)
        if potential_path.exists() and potential_path.suffix == ".gguf":
            model_path = potential_path
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} not found. Please download it first."
            )
    
    try:
        # Unload current model if loaded
        if await service_manager.llm_manager.is_model_loaded():
            await service_manager.llm_manager.unload_model()
        
        # Prepare load options
        load_options = {}
        if options:
            if options.n_ctx is not None:
                load_options['n_ctx'] = options.n_ctx
            if options.n_threads is not None:
                load_options['n_threads'] = options.n_threads
            if options.n_gpu_layers is not None:
                load_options['n_gpu_layers'] = options.n_gpu_layers
                logger.info("GPU layers explicitly set to: %d", options.n_gpu_layers)
            else:
                # Use auto-detected GPU layers if not specified
                gpu_layers = service_manager.llm_manager.loader._gpu_layers
                load_options['n_gpu_layers'] = gpu_layers
                logger.info("GPU layers not specified, using auto-detected: %d", gpu_layers)
            if options.use_flash_attention is not None:
                load_options['use_flash_attention'] = options.use_flash_attention
            if options.use_mmap is not None:
                load_options['use_mmap'] = options.use_mmap
            if options.use_mlock is not None:
                load_options['use_mlock'] = options.use_mlock
            if options.n_batch is not None:
                load_options['n_batch'] = options.n_batch
            if options.n_predict is not None:
                load_options['n_predict'] = options.n_predict
            if options.rope_freq_base is not None:
                load_options['rope_freq_base'] = options.rope_freq_base
            if options.rope_freq_scale is not None:
                load_options['rope_freq_scale'] = options.rope_freq_scale
            if options.low_vram is not None:
                load_options['low_vram'] = options.low_vram
            if options.main_gpu is not None:
                load_options['main_gpu'] = options.main_gpu
            if options.tensor_split is not None:
                load_options['tensor_split'] = options.tensor_split
            if options.n_cpu_moe is not None:
                load_options['n_cpu_moe'] = options.n_cpu_moe
            if options.cache_type_k is not None:
                load_options['cache_type_k'] = options.cache_type_k
            if options.cache_type_v is not None:
                load_options['cache_type_v'] = options.cache_type_v
        else:
            # No options provided, use auto-detected GPU layers
            gpu_layers = service_manager.llm_manager.loader._gpu_layers
            load_options['n_gpu_layers'] = gpu_layers
            logger.info("No load options provided, using auto-detected GPU layers: %d", gpu_layers)
        
        logger.info("=" * 60)
        logger.info("API: Loading model %s", model_id)
        logger.info("Options: %s", load_options)
        logger.info("=" * 60)
        
        # Load new model with options
        success = await service_manager.llm_manager.load_model(
            str(model_path),
            **load_options
        )
        
        if success:
            logger.info("API: Model %s loaded successfully", model_id)
            return {
                "status": "success",
                "message": f"Model {model_id} loaded successfully",
                "model_path": str(model_path),
                "options_used": load_options
            }
        else:
            error_msg = f"Failed to load model {model_id}"
            logger.error("API: %s", error_msg)
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Load failed: {str(e)}") from e


@router.get("/api/models/{model_id}/info", response_model=ModelMetadata)
async def get_model_info(model_id: str):
    """Get detailed model metadata including architecture, parameters, context length, MoE info."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        return ModelMetadata(**info)
    except Exception as e:
        logger.error(f"Error extracting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract model info: {str(e)}")


@router.get("/api/models/{model_id}/memory-estimate", response_model=MemoryEstimate)
async def get_memory_estimate(
    model_id: str,
    context_length: int = Query(2048, ge=512, le=32768),
    batch_size: int = Query(1, ge=1, le=32)
):
    """Get memory requirement estimate for a model with given context length."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    from ..services.llm.memory_calculator import memory_calculator
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        # Extract model info
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        # Calculate memory estimate
        model_params = {
            "num_parameters": info.get("num_parameters"),
            "num_layers": info.get("num_layers", 32),
            "hidden_size": info.get("hidden_size", 4096),
            "quantization": info.get("quantization"),
            "model_name": info.get("name")
        }
        
        estimate = memory_calculator.estimate_total_memory(
            model_params,
            context_length=context_length,
            batch_size=batch_size
        )
        
        # Get recommended VRAM
        recommended_vram = memory_calculator.get_recommended_vram(estimate["total_gb"])
        estimate["recommended_vram_gb"] = recommended_vram
        
        # Check if it will fit
        try:
            import torch
            if torch.cuda.is_available():
                available_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                estimate["will_fit"] = estimate["total_gb"] <= available_vram
            else:
                estimate["will_fit"] = None
        except:
            estimate["will_fit"] = None
        
        return MemoryEstimate(**estimate)
    except Exception as e:
        logger.error(f"Error calculating memory estimate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate memory estimate: {str(e)}")


@router.get("/api/models/{model_id}/config")
async def get_model_config(model_id: str):
    """Get configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    return service_manager.llm_manager.get_model_config(model_id)

@router.put("/api/models/{model_id}/config")
async def save_model_config(model_id: str, config: ModelLoadOptions):
    """Save configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    service_manager.llm_manager.save_model_config(model_id, config.model_dump(exclude_unset=True))
    return {"status": "success"}

@router.post("/api/models/load")
async def load_model(request: Dict[str, Any]):
    """Load a model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
        
    model_path = request.get("model_path")
    if not model_path:
        raise HTTPException(status_code=400, detail="model_path is required")
        
    # Remove model_path from kwargs
    kwargs = {k: v for k, v in request.items() if k != "model_path"}
    
    success = await service_manager.llm_manager.load_model(model_path, **kwargs)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to load model")
        
    return {"status": "success", "message": f"Loaded {model_path}"}

@router.post("/api/conversations/{conversation_id}/rename")
async def rename_conversation(request: ConversationRenameRequest):
    """Rename a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    
    try:
        # Update conversation name
        success = await service_manager.chat_manager.set_conversation_name(
            request.conversation_id,
            request.new_name
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Conversation {request.conversation_id} not found")
        
        return {
            "status": "success",
            "conversation_id": request.conversation_id,
            "new_name": request.new_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename conversation: {str(e)}")


@router.post("/api/models/install-llama-cuda")
async def install_llama_cuda():
    """Install llama-cpp-python with CUDA support."""
    from ..services.llm.cuda_installer import install_llama_cuda, check_cuda_available, check_llama_cuda_support
    
    # Check if CUDA is available
    if not check_cuda_available():
        raise HTTPException(
            status_code=400,
            detail="No CUDA GPU detected. Cannot install CUDA-enabled llama-cpp-python."
        )
    
    # Check if already installed with CUDA
    has_cuda, error = check_llama_cuda_support()
    if has_cuda:
        return {
            "status": "success",
            "message": "llama-cpp-python already has CUDA support",
            "cuda_available": True
        }
    
    try:
        # Get Python executable
        import sys
        python_exe = sys.executable
        
        # Install with CUDA
        success, message = install_llama_cuda(python_exe)
        
        if success:
            return {
                "status": "success",
                "message": message,
                "cuda_available": True
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Installation failed: {message}"
            )
    except Exception as e:
        logger.error("Failed to install llama-cpp-python with CUDA: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Installation error: {str(e)}"
        ) from e


@router.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a downloaded model.
    
    Args:
        model_id: Model identifier or filename
    """
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Check if model is currently loaded
    current_model_path = service_manager.llm_manager.get_current_model_path()
    if current_model_path:
        from pathlib import Path
        current_model_name = Path(current_model_path).name
        if current_model_name == model_id or str(current_model_path) == model_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete model '{model_id}' - it is currently loaded. Please unload it first."
            )
    
    try:
        success = service_manager.llm_manager.downloader.delete_model(model_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Model {model_id} deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} not found"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("Delete failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}") from e


@router.get("/api/models/search")
async def search_models(
    query: str = Query(..., description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results")
):
    """Search for models on HuggingFace."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    try:
        results = await service_manager.llm_manager.downloader.search_models(
            query=query,
            limit=limit
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/api/tools")
async def list_tools():
    """List all available tools with their schemas."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        tools = service_manager.tool_manager.registry.list_tools()
        return {
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}") from e


@router.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get information about a specific tool."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    tool = service_manager.tool_manager.registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found"
        )
    
    return {
        "name": tool.name,
        "description": tool.description,
        "schema": tool.schema
    }


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    # Delete from chat manager (which also deletes from memory store)
    deleted = await service_manager.chat_manager.delete_conversation(conversation_id)
    
    if deleted:
        return {
            "status": "success",
            "message": f"Conversation {conversation_id} deleted"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )


@router.get("/api/debug/info")
async def get_debug_info():
    """Get debug information about system status."""
    logger.info("GET /api/debug/info - Fetching debug information")
    debug_info = {
        "services": {},
        "model": {},
        "memory": {},
        "conversations": {}
    }
    
    # Service status
    debug_info["services"] = {
        "llm_manager": service_manager.llm_manager is not None,
        "chat_manager": service_manager.chat_manager is not None,
        "memory_store": service_manager.memory_store is not None,
        "tool_manager": service_manager.tool_manager is not None,
        "stt_service": service_manager.stt_service is not None,
        "tts_service": service_manager.tts_service is not None
    }
    
    # Model information
    if service_manager.llm_manager:
        sampler_settings = service_manager.llm_manager.get_settings()
        debug_info["model"] = {
            "loaded": await service_manager.llm_manager.is_model_loaded(),
            "current_model": service_manager.llm_manager.get_current_model_path(),
            "gpu_layers": getattr(service_manager.llm_manager.loader, '_gpu_layers', 0) if hasattr(service_manager.llm_manager, 'loader') else 0,
            "last_request_time": getattr(service_manager.llm_manager, '_last_request_time', None),
            "last_request_info": getattr(service_manager.llm_manager, '_last_request_info', None),
            "sampler_settings": sampler_settings
        }
    
    # Memory information
    if service_manager.memory_store:
        debug_info["memory"] = {
            "conversation_count": await service_manager.memory_store.get_conversation_count(),
            "message_count": await service_manager.memory_store.get_message_count(),
            "db_size_bytes": await service_manager.memory_store.get_db_size(),
            "last_entry": await service_manager.memory_store.get_last_entry_timestamp(),
            "vector_store": await service_manager.memory_store.get_vector_store_stats()
        }
    
    # Conversation information
    if service_manager.chat_manager:
        try:
            conversation_ids = await service_manager.chat_manager.list_conversations()
            debug_info["conversations"] = {
                "active_count": len(conversation_ids),
                "conversation_ids": conversation_ids
            }
        except Exception as e:
            logger.error(f"Error getting conversation info: {e}", exc_info=True)
            debug_info["conversations"] = {
                "active_count": 0,
                "conversation_ids": [],
                "error": str(e)
            }
    
    return debug_info
