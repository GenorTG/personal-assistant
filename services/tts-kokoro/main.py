import os
import logging
import io
import soundfile as sf
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from kokoro_onnx import Kokoro

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kokoro-service")



# CORS


# Initialize Kokoro
kokoro = None
BASE_DIR = Path(__file__).parent.resolve()
MODEL_PATH = BASE_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = BASE_DIR / "voices-v1.0.bin"

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_bella"
    speed: float = 1.0
    lang: str = "en-us"

@asynccontextmanager
async def lifespan(app: FastAPI):
    global kokoro
    try:
        # Check if model files exist
        if not MODEL_PATH.exists() or not VOICES_PATH.exists():
            logger.warning(f"Model files not found at {BASE_DIR}! Please download kokoro-v1.0.onnx and voices-v1.0.bin")
        
        kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        logger.info("Kokoro TTS initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Kokoro: {e}")
    yield
    # Cleanup if needed

app = FastAPI(title="Kokoro TTS Service", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    if kokoro:
        return {"status": "healthy", "model_loaded": True}
    return {"status": "error", "model_loaded": False}

@app.get("/voices")
async def get_voices():
    # Hardcoded list of voices supported by Kokoro v1.0
    # In a real implementation, we might parse the bin file or use library methods if available
    voices = [
        "af_bella", "af_sarah", "am_adam", "am_michael",
        "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
        "af_nicole", "af_sky"
    ]
    return {"voices": voices}

@app.post("/synthesize")
async def synthesize(request: SynthesizeRequest):
    if not kokoro:
        raise HTTPException(status_code=503, detail="Kokoro model not initialized")
    
    try:
        # Generate audio
        samples, sample_rate = kokoro.create(
            request.text,
            voice=request.voice,
            speed=request.speed,
            lang=request.lang
        )
        
        # Convert to WAV
        buffer = io.BytesIO()
        sf.write(buffer, samples, sample_rate, format='WAV')
        buffer.seek(0)
        
        return Response(content=buffer.read(), media_type="audio/wav")
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)
