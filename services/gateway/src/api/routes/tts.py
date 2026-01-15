"""Text-to-speech routes."""
import logging
from typing import Dict, Optional
import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response, UploadFile, File, Form
from pathlib import Path

from ..schemas import TTSRequest, VoiceModelDownloadRequest, VoiceModelDownloadStatus
from ...services.service_manager import service_manager
from ...config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tts"])


@router.post("/api/voice/tts")
async def text_to_speech(request: TTSRequest, response: Response):
    """Convert text to speech."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
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
        audio_data = await service_manager.tts_service.synthesize(
            text=request.text,
            voice=request.voice,
            output_format="wav"
        )
        
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*"
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
    # Return graceful response if TTS service not initialized
    if not service_manager.tts_service:
        return [
            {
                "name": "piper",
                "status": "not_initialized",
                "is_ready": False,
                "is_current": False,
                "error_message": "TTS service not initialized"
            },
            {
                "name": "kokoro",
                "status": "not_initialized",
                "is_ready": False,
                "is_current": False,
                "error_message": "TTS service not initialized"
            },
            {
                "name": "chatterbox",
                "status": "not_initialized",
                "is_ready": False,
                "is_current": False,
                "error_message": "TTS service not initialized"
            }
        ]
    
    try:
        # Backends are integrated into the gateway process (no per-backend HTTP services),
        # except chatterbox which is optional and only started when explicitly selected.
        backends = service_manager.tts_service.get_available_backends()
        return {"backends": backends}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backends: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/piper/voices/download", response_model=VoiceModelDownloadStatus)
async def download_piper_voice(request: VoiceModelDownloadRequest):
    """Download a Piper voice (onnx + optional json config) for later use."""
    if not service_manager.tts_service:
        raise HTTPException(status_code=503, detail="TTS service not initialized")

    voice_id = request.model_id
    if not voice_id:
        raise HTTPException(status_code=400, detail="model_id is required (voice id)")

    backend = service_manager.tts_service.manager.backends.get("piper")
    if not backend:
        raise HTTPException(status_code=404, detail="Piper backend not available")

    result = await backend.download_voice(
        voice_id=voice_id,
        onnx_url=request.url,
        config_url=request.aux_url,
        force=request.force,
    )
    return VoiceModelDownloadStatus(**result)


@router.get("/api/voice/tts/backends/piper/voices/download/status", response_model=VoiceModelDownloadStatus)
async def get_piper_voice_download_status(voice_id: str):
    """Get Piper voice download status."""
    if not service_manager.tts_service:
        raise HTTPException(status_code=503, detail="TTS service not initialized")

    backend = service_manager.tts_service.manager.backends.get("piper")
    if not backend:
        raise HTTPException(status_code=404, detail="Piper backend not available")

    result = backend.get_download_status(voice_id)
    return VoiceModelDownloadStatus(**result)


@router.post("/api/voice/tts/backends/kokoro/model/download", response_model=VoiceModelDownloadStatus)
async def download_kokoro_model(request: VoiceModelDownloadRequest):
    """Download Kokoro model assets (onnx + voices.json)."""
    if not service_manager.tts_service:
        raise HTTPException(status_code=503, detail="TTS service not initialized")

    backend = service_manager.tts_service.manager.backends.get("kokoro")
    if not backend:
        raise HTTPException(status_code=404, detail="Kokoro backend not available")

    result = await backend.download_model(force=request.force)
    return VoiceModelDownloadStatus(**result)


@router.get("/api/voice/tts/backends/kokoro/model/download/status", response_model=VoiceModelDownloadStatus)
async def get_kokoro_model_download_status():
    """Get Kokoro model download status."""
    if not service_manager.tts_service:
        raise HTTPException(status_code=503, detail="TTS service not initialized")

    backend = service_manager.tts_service.manager.backends.get("kokoro")
    if not backend:
        raise HTTPException(status_code=404, detail="Kokoro backend not available")

    result = backend.get_download_status()
    return VoiceModelDownloadStatus(**result)


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
        return {
            "status": "error",
            "message": "TTS service not initialized",
            "initialized": False,
            "backend_info": None
        }
    
    try:
        success = await service_manager.tts_service.switch_backend(backend_name)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        await service_manager.memory_store.set_setting("tts_backend", backend_name)
        
        info = await service_manager.tts_service.get_backend_info(backend_name)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
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
    if not service_manager.tts_service:
        return {
            "status": "error",
            "message": "TTS service not initialized",
            "initialized": False
        }
    
    backend = service_manager.tts_service.manager.get_backend(backend_name)
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    
    if hasattr(backend, "start_service"):
        success = await backend.start_service()
        if success:
            await backend.initialize()
            return {"status": "success", "message": f"Started {backend_name} service"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start {backend_name} service")
    
    return {"status": "ignored", "message": "Service control not supported for this backend"}


@router.get("/api/voice/tts/backends/{backend_name}/voices")
async def get_tts_voices(backend_name: str, response: Response):
    """Get available voices for a TTS backend."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        return {
            "voices": [],
            "status": "not_initialized",
            "message": "TTS service not initialized"
        }
    
    try:
        voices = await service_manager.tts_service.get_available_voices(backend_name)
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS voices: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/{backend_name}/voices/refresh")
async def refresh_tts_voices(backend_name: str, response: Response):
    """Refresh/reload voices for a TTS backend (hot-reload)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        return {
            "message": "TTS service not initialized",
            "voices": [],
            "status": "error",
            "initialized": False
        }
    
    try:
        if backend_name == "chatterbox":
            async with httpx.AsyncClient(timeout=10.0) as client:
                reload_response = await client.post("http://localhost:4123/voices/reload")
                if reload_response.status_code == 200:
                    reload_data = reload_response.json()
                    voices = await service_manager.tts_service.get_available_voices(backend_name)
                    return {
                        "message": "Voices refreshed successfully",
                        "voices": voices,
                        "reload_stats": reload_data
                    }
                else:
                    raise HTTPException(
                        status_code=reload_response.status_code,
                        detail=f"Failed to reload voices: {reload_response.text}"
                    )
        else:
            voices = await service_manager.tts_service.get_available_voices(backend_name)
            return {
                "message": "Voices refreshed successfully",
                "voices": voices
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error refreshing TTS voices: {str(e)}"
        ) from e


@router.put("/api/voice/tts/backends/{backend_name}/options")
async def set_tts_backend_options(backend_name: str, options: dict, response: Response):
    """Set options for a TTS backend."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
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
        
        info = await service_manager.tts_service.get_backend_info(backend_name)
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
    # Return default response if TTS service not initialized (graceful degradation)
    if not service_manager.tts_service:
        return {
            "current_backend": None,
            "current_backend_info": None,
            "available_backends": [
                {"name": "piper", "status": "not_initialized", "is_current": False},
                {"name": "kokoro", "status": "not_initialized", "is_current": False},
                {"name": "chatterbox", "status": "not_initialized", "is_current": False}
            ]
        }
    
    try:
        current_backend = service_manager.tts_service.get_current_backend_name()
        backends = service_manager.tts_service.get_available_backends()
        
        current_info = None
        if service_manager.tts_service.manager.current_backend:
            try:
                current_info = await service_manager.tts_service.get_backend_info(current_backend)
            except Exception as e:
                logger.warning(f"Error getting backend info: {e}")
        
        return {
            "current_backend": current_backend,
            "current_backend_info": current_info,
            "available_backends": backends
        }
    except Exception as e:
        logger.error(f"Error getting TTS settings: {e}", exc_info=True)
        # Return default response on error instead of raising
        return {
            "current_backend": None,
            "current_backend_info": None,
            "available_backends": [
                {"name": "piper", "status": "error", "is_current": False, "error": str(e)},
                {"name": "kokoro", "status": "error", "is_current": False, "error": str(e)},
                {"name": "chatterbox", "status": "error", "is_current": False, "error": str(e)}
            ]
        }


@router.get("/api/voice/tts/backends/{backend_name}/health")
async def check_tts_backend_health(backend_name: str):
    """Check if a TTS backend service is running and accessible."""
    service_urls = {
        "piper": "http://localhost:8004",
        "whisper": "http://localhost:8003",
        "chatterbox": "http://localhost:4123",
        "kokoro": "http://localhost:8880"
    }
    
    if backend_name == "openai":
        if service_manager.tts_service:
            backend = service_manager.tts_service.manager.backends.get("openai")
            if backend and hasattr(backend, 'api_url') and backend.api_url:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
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
    
    if backend_name not in service_urls:
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


# Chatterbox service endpoints
@router.get("/api/voice/tts/backends/chatterbox/service")
async def get_chatterbox_service_status():
    """Get Chatterbox TTS API service status."""
    try:
        from ...services.external.chatterbox_service import chatterbox_service
        return chatterbox_service.get_status()
    except Exception as e:
        logger.error(f"Error getting Chatterbox service status: {e}", exc_info=True)
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
    from ...services.external.chatterbox_service import chatterbox_service
    
    status = chatterbox_service.get_status()
    if status.get("is_installing"):
        return {"status": "started", "message": "Installation already in progress"}
    
    background_tasks.add_task(chatterbox_service.install)
    
    return {"status": "started", "message": "Installation started in background"}


@router.post("/api/voice/tts/backends/chatterbox/service/start")
async def start_chatterbox_service():
    """Start Chatterbox TTS API server."""
    from ...services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.start()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/stop")
async def stop_chatterbox_service():
    """Stop Chatterbox TTS API server."""
    from ...services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.stop()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/restart")
async def restart_chatterbox_service():
    """Restart Chatterbox TTS API server."""
    from ...services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.restart()
    return result


@router.get("/api/voice/tts/backends/chatterbox/service/logs")
async def get_chatterbox_service_logs():
    """Get Chatterbox TTS API service logs."""
    from ...services.external.chatterbox_service import chatterbox_service
    return {"logs": chatterbox_service.get_logs()}


@router.post("/api/voice/tts/backends/openai/config")
async def configure_openai_tts(config: Dict[str, str]):
    """Configure OpenAI TTS backend."""
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    
    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="api_url and api_key are required")
    
    await service_manager.memory_store.set_setting("tts_openai_url", api_url)
    await service_manager.memory_store.set_setting("tts_openai_key", api_key, encrypted=True)
    
    backend = service_manager.tts_service.manager.backends.get("openai")
    if backend:
        backend.configure(api_url, api_key)
        await backend.initialize()
    
    return {"status": "success", "message": "OpenAI TTS configured"}


@router.get("/api/voice/tts/backends/{backend_name}/model/status")
async def get_tts_backend_model_status(backend_name: str):
    """Get model status for a TTS backend."""
    # Return default response if TTS service not initialized (graceful degradation)
    if not service_manager.tts_service:
        return {
            "loaded": False,
            "status": "not_initialized",
            "model_path": None,
            "message": "TTS service not initialized"
        }
    
    try:
        backend = service_manager.tts_service.manager.get_backend(backend_name)
        if not backend:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        if hasattr(backend, 'get_model_status'):
            status = backend.get_model_status()
            return status
        else:
            return {
                "loaded": backend.is_ready,
                "status": "unknown",
                "message": "Model status not available for this backend"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backend model status: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/{backend_name}/model/unload")
async def unload_tts_backend_model(backend_name: str):
    """Unload TTS model for a backend."""
    if not service_manager.tts_service:
        return {
            "status": "error",
            "message": "TTS service not initialized",
            "initialized": False
        }
    
    try:
        backend = service_manager.tts_service.manager.get_backend(backend_name)
        if not backend:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        if hasattr(backend, 'unload_model'):
            success = backend.unload_model()
            if success:
                return {
                    "status": "success",
                    "message": f"{backend_name} model unloaded from memory"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to unload {backend_name} model"
                }
        else:
            return {
                "status": "info",
                "message": f"Model unloading not supported for {backend_name} backend"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error unloading TTS backend model: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/{backend_name}/model/reload")
async def reload_tts_backend_model(backend_name: str):
    """Reload TTS model for a backend."""
    if not service_manager.tts_service:
        return {
            "status": "error",
            "message": "TTS service not initialized",
            "initialized": False
        }
    
    try:
        backend = service_manager.tts_service.manager.get_backend(backend_name)
        if not backend:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Unload first
        if hasattr(backend, 'unload_model'):
            backend.unload_model()
        
        # Reinitialize
        success = await backend.initialize()
        if success:
            return {
                "status": "success",
                "message": f"{backend_name} model reloaded"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to reload {backend_name} model: {backend.error_message if hasattr(backend, 'error_message') else 'Unknown error'}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reloading TTS backend model: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}/models/available")
async def get_tts_backend_available_models(backend_name: str):
    """Get available models for a TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        from ...services.model_catalog import get_piper_voices, get_kokoro_model
        
        if backend_name == "piper":
            models = get_piper_voices()
            return {"models": models}
        elif backend_name == "kokoro":
            model = get_kokoro_model()
            return {"models": [model]}
        else:
            # For other backends, return empty or check if they have a method
            backend = service_manager.tts_service.manager.get_backend(backend_name)
            if backend and hasattr(backend, 'get_available_models'):
                models = backend.get_available_models()
                return {"models": models}
            else:
                return {"models": []}
    except Exception as e:
        logger.error(f"Error getting available TTS models: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting available TTS models: {str(e)}"
        ) from e


@router.get("/api/voice/tts/memory")
async def get_tts_memory():
    """Get memory usage for all TTS backends."""
    # Return default response if TTS service not initialized (graceful degradation)
    if not service_manager.tts_service:
        return {
            "backends": {
                "piper": {
                    "total_memory_mb": 0,
                    "model_memory_mb": 0,
                    "base_memory_mb": 0
                },
                "kokoro": {
                    "total_memory_mb": 0,
                    "model_memory_mb": 0,
                    "base_memory_mb": 0
                },
                "chatterbox": {
                    "total_memory_mb": 0,
                    "model_memory_mb": 0,
                    "base_memory_mb": 0
                }
            },
            "total_memory_mb": 0,
            "total_model_memory_mb": 0
        }
    
    try:
        memory_usage = {}
        total_memory_mb = 0
        total_model_memory_mb = 0
        
        for backend_name, backend in service_manager.tts_service.manager.backends.items():
            if hasattr(backend, 'get_memory_usage'):
                memory = backend.get_memory_usage()
                memory_usage[backend_name] = memory
                total_memory_mb += memory.get("total_memory_mb", 0)
                total_model_memory_mb += memory.get("model_memory_mb", 0)
            else:
                memory_usage[backend_name] = {
                    "total_memory_mb": 0,
                    "model_memory_mb": 0,
                    "base_memory_mb": 0,
                    "message": "Memory tracking not available"
                }
        
        return {
            "backends": memory_usage,
            "total_memory_mb": round(total_memory_mb, 2),
            "total_model_memory_mb": round(total_model_memory_mb, 2)
        }
    except Exception as e:
        logger.error(f"Error getting TTS memory usage: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS memory usage: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/piper/model/switch")
async def switch_piper_model(request: Dict[str, str], response: Response):
    """Switch Piper TTS model (voice)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        return {
            "status": "error",
            "message": "TTS service not initialized"
        }
    
    model_id = request.get("model_id")
    if not model_id:
        raise HTTPException(
            status_code=400,
            detail="model_id is required"
        )
    
    try:
        backend = service_manager.tts_service.manager.get_backend("piper")
        if not backend:
            raise HTTPException(
                status_code=404,
                detail="Piper backend not found"
            )
        
        # Check if backend has switch_model method
        if hasattr(backend, 'switch_model'):
            success = await backend.switch_model(model_id)
            if success:
                return {
                    "status": "success",
                    "message": f"Switched to Piper model: {model_id}",
                    "model_id": model_id
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to switch to model: {model_id}"
                )
        else:
            raise HTTPException(
                status_code=501,
                detail="Model switching not implemented for Piper backend"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching Piper model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error switching Piper model: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/chatterbox/voices/upload")
async def upload_chatterbox_voice(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    response: Response = None
):
    """Upload a voice file for Chatterbox TTS."""
    if response:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    # Validate file type
    allowed_extensions = {'.wav', '.mp3', '.flac', '.m4a', '.ogg'}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Generate voice name if not provided
    if not name:
        name = Path(file.filename).stem if file.filename else "voice"
    
    # Sanitize name
    name = "".join(c for c in name if c.isalnum() or c in ('-', '_')).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid voice name")
    
    try:
        # Use the existing upload endpoint logic
        chatterbox_dir = settings.base_dir.parent.parent / "services" / "tts-chatterbox"
        voices_dir = chatterbox_dir / "voices"
        voices_dir.mkdir(parents=True, exist_ok=True)
        
        # Save file
        output_filename = f"{name}{file_ext}"
        output_path = voices_dir / output_filename
        
        # Read file content
        content = await file.read()
        
        # Validate file size (max 10MB)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 10MB limit"
            )
        
        # Write file
        with open(output_path, "wb") as f:
            f.write(content)
        
        # If Chatterbox service is running, trigger voice reload
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post("http://localhost:4123/voices/reload")
        except Exception as e:
            logger.warning(f"Could not reload Chatterbox voices: {e}")
        
        return {
            "status": "success",
            "message": f"Voice '{name}' uploaded successfully",
            "voice_id": name,
            "path": str(output_path),
            "filename": output_filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading voice: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading voice: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/chatterbox/voices/custom")
async def get_chatterbox_custom_voices(response: Response):
    """Get list of custom voices uploaded to Chatterbox."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        return {
            "voices": [],
            "status": "not_initialized",
            "message": "TTS service not initialized"
        }
    
    try:
        # Try to get voices from Chatterbox API
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                api_response = await client.get("http://localhost:4123/v1/voices")
                if api_response.status_code == 200:
                    data = api_response.json()
                    voices = data.get("voices", [])
                    return {
                        "voices": voices,
                        "status": "success",
                        "count": len(voices)
                    }
            except Exception as e:
                logger.debug(f"Could not fetch from Chatterbox API: {e}")
        
        # Fallback: scan voices directory directly
        chatterbox_dir = settings.base_dir.parent.parent / "services" / "tts-chatterbox"
        voices_dir = chatterbox_dir / "voices"
        
        custom_voices = []
        if voices_dir.exists():
            for voice_file in voices_dir.glob("*"):
                if voice_file.is_file() and voice_file.suffix.lower() in {'.wav', '.mp3', '.flac', '.m4a', '.ogg'}:
                    custom_voices.append({
                        "name": voice_file.stem,
                        "filename": voice_file.name,
                        "path": str(voice_file),
                        "file_size": voice_file.stat().st_size
                    })
        
        return {
            "voices": custom_voices,
            "status": "success",
            "count": len(custom_voices)
        }
    except Exception as e:
        logger.error(f"Error getting custom voices: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting custom voices: {str(e)}"
        ) from e


@router.delete("/api/voice/tts/backends/chatterbox/voices/{voice_name}")
async def delete_chatterbox_voice(voice_name: str, response: Response):
    """Delete a custom voice from Chatterbox."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    # Sanitize voice name
    voice_name = "".join(c for c in voice_name if c.isalnum() or c in ('-', '_')).strip()
    if not voice_name:
        raise HTTPException(status_code=400, detail="Invalid voice name")
    
    try:
        # Try to delete via Chatterbox API first
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                api_response = await client.delete(f"http://localhost:4123/v1/voices/{voice_name}")
                if api_response.status_code == 200:
                    return {
                        "status": "success",
                        "message": f"Voice '{voice_name}' deleted successfully"
                    }
            except Exception as e:
                logger.debug(f"Could not delete via Chatterbox API: {e}")
        
        # Fallback: delete file directly
        chatterbox_dir = settings.base_dir.parent.parent / "services" / "tts-chatterbox"
        voices_dir = chatterbox_dir / "voices"
        
        # Try different file extensions
        deleted = False
        for ext in ['.wav', '.mp3', '.flac', '.m4a', '.ogg']:
            voice_path = voices_dir / f"{voice_name}{ext}"
            if voice_path.exists():
                voice_path.unlink()
                deleted = True
                break
        
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Voice '{voice_name}' not found"
            )
        
        # Trigger voice reload
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post("http://localhost:4123/voices/reload")
        except Exception as e:
            logger.warning(f"Could not reload Chatterbox voices: {e}")
        
        return {
            "status": "success",
            "message": f"Voice '{voice_name}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting voice: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting voice: {str(e)}"
        ) from e