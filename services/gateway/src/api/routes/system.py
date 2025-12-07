"""System information and status routes."""
import os
import logging
from fastapi import APIRouter, HTTPException

from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/api/services/status")
async def get_services_status():
    """Get real-time status for all services from cached polling data."""
    if not service_manager.status_manager:
        raise HTTPException(
            status_code=503,
            detail="Status manager not initialized"
        )
    
    all_statuses = service_manager.status_manager.get_all_statuses()
    
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
    import multiprocessing
    
    cpu_count = os.cpu_count() or multiprocessing.cpu_count()
    
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
        else:
            gpu_info = {"available": False, "reason": "CUDA not available"}
    except ImportError:
        gpu_info = {"available": False, "reason": "PyTorch not installed"}
    except Exception as e:
        gpu_info = {"available": False, "reason": str(e)}
    
    return {
        "cpu_count": cpu_count,
        "cpu_threads_available": cpu_count,
        "platform": os.name,
        "system": os.uname().system if hasattr(os, 'uname') else "unknown",
        "gpu": gpu_info
    }


@router.get("/api/system/status")
async def get_system_status():
    """Get real-time system status including per-service RAM/VRAM usage."""
    from ...services.system_monitor import system_monitor
    return system_monitor.get_status()


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
    
    debug_info["services"] = {
        "llm_manager": service_manager.llm_manager is not None,
        "chat_manager": service_manager.chat_manager is not None,
        "memory_store": service_manager.memory_store is not None,
        "tool_manager": service_manager.tool_manager is not None,
        "stt_service": service_manager.stt_service is not None,
        "tts_service": service_manager.tts_service is not None
    }
    
    if service_manager.llm_manager:
        sampler_settings = service_manager.llm_manager.get_settings()
        debug_info["model"] = {
            "loaded": service_manager.llm_manager.is_model_loaded(),
            "current_model": service_manager.llm_manager.get_current_model_path(),
            "gpu_layers": getattr(service_manager.llm_manager.loader, '_gpu_layers', 0) if hasattr(service_manager.llm_manager, 'loader') else 0,
            "last_request_time": getattr(service_manager.llm_manager, '_last_request_time', None),
            "last_request_info": getattr(service_manager.llm_manager, '_last_request_info', None),
            "sampler_settings": sampler_settings
        }
    
    if service_manager.memory_store:
        debug_info["memory"] = {
            "conversation_count": await service_manager.memory_store.get_conversation_count(),
            "message_count": await service_manager.memory_store.get_message_count(),
            "db_size_bytes": await service_manager.memory_store.get_db_size(),
            "last_entry": await service_manager.memory_store.get_last_entry_timestamp(),
            "vector_store": await service_manager.memory_store.get_vector_store_stats()
        }
    
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


@router.post("/api/reset")
async def reset_app_state(keep_models: bool = True):
    """Reset all app state (conversations, settings, vector store)."""
    from ...services.memory.file_store import FileConversationStore
    from ...services.memory.settings_store import FileSettingsStore
    from ...services.memory.vector_store import VectorStore
    from ...config.settings import settings
    
    try:
        results = {
            "conversations_deleted": 0,
            "settings_cleared": False,
            "vector_store_cleared": False
        }
        
        file_store = FileConversationStore(settings.memory_dir)
        results["conversations_deleted"] = await file_store.clear_all()
        
        settings_store = FileSettingsStore(settings.memory_dir)
        results["settings_cleared"] = await settings_store.clear_all()
        
        try:
            vector_store = VectorStore()
            if vector_store.collection and vector_store.store_type == "chromadb":
                all_results = vector_store.collection.get()
                if all_results and "ids" in all_results and all_results["ids"]:
                    vector_store.collection.delete(ids=all_results["ids"])
                    logger.info(f"Deleted {len(all_results['ids'])} entries from vector store")
            results["vector_store_cleared"] = True
        except Exception as e:
            logger.warning(f"Could not clear vector store: {e}")
            results["vector_store_cleared"] = False
        
        logger.info(f"App state reset completed: {results}")
        return {
            "status": "success",
            "message": "App state reset successfully",
            **results
        }
    except Exception as e:
        logger.error(f"Error resetting app state: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset app state: {str(e)}"
        ) from e
