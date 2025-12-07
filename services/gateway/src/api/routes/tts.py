"""Text-to-speech routes."""
import logging
from typing import Dict
import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response

from ..schemas import TTSRequest
from ...services.service_manager import service_manager

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
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        backends = service_manager.tts_service.get_available_backends()
        
        service_urls = {
            "chatterbox": "http://localhost:4123",
            "kokoro": "http://localhost:8880",
            "piper": "http://localhost:8004"
        }
        
        for backend in backends:
            backend_name = backend.get("name", "")
            if backend.get("status") == "not_initialized" and backend_name in service_urls:
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        resp = await client.get(f"{service_urls[backend_name]}/health")
                        if resp.status_code == 200:
                            backend["status"] = "ready"
                            backend["is_ready"] = True
                            backend["error_message"] = None
                except Exception:
                    pass
        
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


@router.post("/api/voice/tts/backends/{backend_name}/voices/refresh")
async def refresh_tts_voices(backend_name: str, response: Response):
    """Refresh/reload voices for a TTS backend (hot-reload)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
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
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        current_backend = service_manager.tts_service.get_current_backend_name()
        backends = service_manager.tts_service.get_available_backends()
        
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
