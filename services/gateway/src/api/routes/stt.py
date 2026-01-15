"""Speech-to-text routes."""
import logging
from typing import Dict, Optional
from pathlib import Path
import tempfile
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File

from ..schemas import STTResponse, VoiceModelDownloadStatus
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
    
    tmp_path = None
    try:
        # Determine file extension from filename or content type
        file_ext = None
        if audio.filename:
            file_ext = Path(audio.filename).suffix.lower()
        
        # If no extension from filename, try to infer from content type
        if not file_ext or file_ext == '':
            content_type = audio.content_type or ''
            if 'webm' in content_type or 'opus' in content_type:
                file_ext = '.webm'
            elif 'wav' in content_type:
                file_ext = '.wav'
            elif 'mp3' in content_type:
                file_ext = '.mp3'
            elif 'ogg' in content_type:
                file_ext = '.ogg'
            else:
                file_ext = '.webm'  # Default to webm for browser recordings
        
        # Ensure extension starts with dot
        if not file_ext.startswith('.'):
            file_ext = '.' + file_ext
        
        logger.info(f"Processing STT audio: filename={audio.filename}, content_type={audio.content_type}, ext={file_ext}")
        
        with tempfile.NamedTemporaryFile(
            suffix=file_ext,
            delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        async with aiofiles.open(tmp_path, 'wb') as f:
            content = await audio.read()
            if len(content) == 0:
                raise HTTPException(status_code=400, detail="Empty audio file received")
            await f.write(content)
        
        logger.info(f"Saved audio file: {tmp_path}, size: {len(content)} bytes")
        
        try:
            text, detected_language = await service_manager.stt_service.transcribe(
                tmp_path,
                language=language
            )
            
            logger.info(f"Transcription successful: text length={len(text) if text else 0}, language={detected_language}")
            
            return STTResponse(
                text=text or "",
                language=detected_language
            )
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {tmp_path}: {e}")
    
    except HTTPException:
        raise
    except FileNotFoundError as e:
        logger.error(f"Audio file error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Audio file error: {str(e)}") from e
    except ValueError as e:
        logger.error(f"Value error in STT: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"STT error: {e}", exc_info=True)
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


@router.get("/api/voice/stt/model/status")
async def get_stt_model_status():
    """Get current STT model status."""
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="STT service not initialized"
        )
    
    try:
        status = service_manager.stt_service.get_model_status()
        return status
    except Exception as e:
        logger.error(f"Error getting STT model status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting STT model status: {str(e)}"
        ) from e


@router.post("/api/voice/stt/model/unload")
async def unload_stt_model():
    """Unload STT model from memory."""
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="STT service not initialized"
        )
    
    try:
        success = service_manager.stt_service.unload_model()
        if success:
            return {
                "status": "success",
                "message": "STT model unloaded from memory"
            }
        else:
            return {
                "status": "info",
                "message": "No model was loaded"
            }
    except Exception as e:
        logger.error(f"Error unloading STT model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error unloading STT model: {str(e)}"
        ) from e


@router.post("/api/voice/stt/model/switch")
async def switch_stt_model(request: Dict[str, str]):
    """Switch Whisper model size."""
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="STT service not initialized"
        )
    
    model_size = request.get("model_size")
    if not model_size:
        raise HTTPException(
            status_code=400,
            detail="model_size is required"
        )
    
    valid_sizes = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    if model_size not in valid_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model size. Must be one of: {', '.join(valid_sizes)}"
        )
    
    try:
        # Get current status before switch
        current_status = service_manager.stt_service.get_model_status()
        
        success = service_manager.stt_service.switch_model_size(model_size)
        if success:
            # Update settings
            await service_manager.memory_store.set_setting("stt_model_size", model_size)
            
            # Get status after switch to check if model is loading/downloading
            new_status = service_manager.stt_service.get_model_status()
            
            return {
                "status": "success",
                "message": f"Switching to Whisper model: {model_size}. Model will auto-download if not cached.",
                "model_size": model_size,
                "initialized": new_status.get("initialized", False),
                "loaded": new_status.get("loaded", False),
                "note": "If this is the first time using this model size, it will download automatically. Check model status endpoint for progress."
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Model switching only supported for faster-whisper provider"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching STT model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error switching STT model: {str(e)}"
        ) from e


@router.post("/api/voice/stt/models/{model_size}/download", response_model=VoiceModelDownloadStatus)
async def download_stt_model(model_size: str):
    """Trigger download of a faster-whisper model size into local cache."""
    if not service_manager.stt_service:
        raise HTTPException(status_code=503, detail="STT service not initialized")

    valid_sizes = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    if model_size not in valid_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model size. Must be one of: {', '.join(valid_sizes)}"
        )

    # Kick off background download and return queued state
    service_manager.stt_service.download_model_size(model_size)
    return VoiceModelDownloadStatus(**service_manager.stt_service.get_download_status(model_size))


@router.get("/api/voice/stt/models/{model_size}/download/status", response_model=VoiceModelDownloadStatus)
async def get_stt_model_download_status(model_size: str):
    """Get status for a faster-whisper model download."""
    if not service_manager.stt_service:
        raise HTTPException(status_code=503, detail="STT service not initialized")
    return VoiceModelDownloadStatus(**service_manager.stt_service.get_download_status(model_size))


@router.get("/api/voice/stt/models/available")
async def get_available_stt_models():
    """Get list of available Whisper models with download info."""
    from ...services.model_catalog import get_whisper_models
    
    try:
        models = get_whisper_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error getting available STT models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting available STT models: {str(e)}"
        ) from e


@router.get("/api/voice/stt/memory")
async def get_stt_memory():
    """Get memory usage for STT service."""
    # Return default response if STT service not initialized (graceful degradation)
    if not service_manager.stt_service:
        return {
            "total_memory_mb": 0,
            "model_memory_mb": 0,
            "base_memory_mb": 0
        }
    
    try:
        memory = service_manager.stt_service.get_memory_usage()
        return memory
    except Exception as e:
        logger.error(f"Error getting STT memory usage: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting STT memory usage: {str(e)}"
        ) from e