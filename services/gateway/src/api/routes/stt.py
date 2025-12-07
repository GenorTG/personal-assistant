"""Speech-to-text routes."""
import logging
from typing import Dict, Optional
from pathlib import Path
import tempfile
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

from ..schemas import STTResponse
from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stt"])


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
        file_ext = Path(audio.filename).suffix if audio.filename else ".wav"
        
        with tempfile.NamedTemporaryFile(
            suffix=file_ext,
            delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        async with aiofiles.open(tmp_path, 'wb') as f:
            content = await audio.read()
            await f.write(content)
        
        try:
            text, detected_language = await service_manager.stt_service.transcribe(
                tmp_path,
                language=language
            )
            
            return STTResponse(
                text=text,
                language=detected_language
            )
        finally:
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


@router.get("/api/voice/stt/settings")
async def get_stt_settings():
    """Get all STT settings from cached status."""
    try:
        if not service_manager.stt_service:
            service_manager.enable_stt()
        
        if not service_manager.status_manager:
            return {
                "status": "offline",
                "provider": "Whisper",
                "model_size": True,
                "available_languages": ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "hi"],
                "default_language": "en",
                "model_initialized": False
            }
        
        stt_service = service_manager.stt_service
        
        cached_status = service_manager.status_manager.get_service_status("stt") or {}
        is_healthy = cached_status.get("status") == "ready"
            
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
    service_manager.enable_stt()
    
    if service_manager.memory_store:
        await service_manager.memory_store.update_setting("stt_enabled", "true")
    
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="Failed to enable STT service"
        )
    
    try:
        stt_service = service_manager.stt_service
        
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


@router.post("/api/voice/stt/config")
async def configure_stt(config: Dict[str, str]):
    """Configure STT service (Whisper or OpenAI)."""
    provider = config.get("provider", "whisper")
    enabled = config.get("enabled", "true")
    
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
