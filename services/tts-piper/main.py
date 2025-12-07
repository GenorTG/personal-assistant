import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional

from src.tts import PiperTTS
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tts_service = PiperTTS()

class TTSRequest(BaseModel):
    input: str
    voice: Optional[str] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize TTS and ensure model is available
    try:
        # Try to find or download model on startup
        if not tts_service.model_path or not tts_service.model_path.exists():
            logger.info("No Piper model found on startup, attempting to download...")
            tts_service.model_path = tts_service._download_default_model()
            if tts_service.model_path and tts_service.model_path.exists():
                logger.info(f"Piper model ready: {tts_service.model_path}")
            else:
                logger.warning("Piper model not available - will attempt download on first use")
    except Exception as e:
        logger.warning(f"Failed to initialize Piper model on startup: {e}")
    yield

app = FastAPI(title="Piper Service", lifespan=lifespan)

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
    return {"status": "healthy", "service": "piper"}

@app.post("/v1/audio/speech")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech."""
    try:
        # synthesize is synchronous, run in executor
        import asyncio
        loop = asyncio.get_event_loop()
        audio_path = await loop.run_in_executor(
            None,
            tts_service.synthesize,
            request.input,
            request.voice
        )
        # Read the generated wav file into memory
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        return Response(content=audio_data, media_type="audio/wav")
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/audio/voices")
async def list_voices():
    """List available voices."""
    return {"voices": tts_service.get_voices()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
