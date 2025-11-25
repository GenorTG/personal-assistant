import logging
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import shutil
import os
from pathlib import Path

from src.stt import STTService
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

stt_service = STTService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize STT
    # STT loads model on first use or we can pre-load here
    yield

app = FastAPI(title="Whisper Service", lifespan=lifespan)

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
    return {"status": "healthy", "service": "whisper"}

@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(None)
):
    """Transcribe audio file."""
    try:
        # Save temp file
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / file.filename
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Transcribe
        text, detected_lang = await stt_service.transcribe(str(temp_path), language=language)
        
        # Cleanup
        os.remove(temp_path)
        
        return {
            "text": text,
            "language": detected_lang
        }
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
