from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import shutil
import os
from pathlib import Path
import logging
import subprocess
from ..config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/voice/upload")
async def upload_voice_sample(
    file: UploadFile = File(...),
    name: str = None
):
    """
    Upload a voice sample for Chatterbox.
    Converts to 48kHz mono WAV.
    """
    if not name:
        name = Path(file.filename).stem

    # Sanitize name
    name = "".join(c for c in name if c.isalnum() or c in ('-', '_')).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid voice name")

    chatterbox_dir = settings.base_dir.parent.parent / "services" / "tts-chatterbox"
    voices_dir = chatterbox_dir / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    
    temp_dir = settings.data_dir / "temp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    temp_input_path = temp_dir / file.filename
    output_filename = f"{name}.wav"
    output_path = voices_dir / output_filename
    
    try:
        with open(temp_input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        ffmpeg_cmd = shutil.which("ffmpeg")
        if not ffmpeg_cmd:
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(str(temp_input_path))
                audio = audio.set_channels(1).set_frame_rate(48000)
                audio.export(str(output_path), format="wav")
            except ImportError:
                raise HTTPException(status_code=500, detail="ffmpeg not found and pydub not installed")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
        else:
            cmd = [ffmpeg_cmd, "-y", "-i", str(temp_input_path), "-ac", "1", "-ar", "48000", str(output_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=f"FFmpeg conversion failed: {result.stderr}")
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Voice '{name}' uploaded and converted successfully",
            "path": str(output_path),
            "voice_id": name
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_input_path.exists():
            try:
                os.remove(temp_input_path)
            except Exception:
                pass
