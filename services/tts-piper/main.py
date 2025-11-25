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
    # Initialize TTS
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
        audio_path = await tts_service.synthesize(request.input, request.voice)
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
