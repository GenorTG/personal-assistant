"""Memory and context routes."""
import logging
from fastapi import APIRouter, HTTPException, Request

from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memory"])


@router.get("/api/settings/vector-memory")
async def get_vector_memory_settings():
    """Get global vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        settings = await service_manager.memory_store.get_vector_memory_settings()
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vector memory settings: {str(e)}") from e


@router.put("/api/settings/vector-memory")
async def set_vector_memory_settings(request: Request):
    """Update global vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        await service_manager.memory_store.set_vector_memory_settings(body)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set vector memory settings: {str(e)}") from e


@router.get("/api/conversations/{conversation_id}/vector-memory")
async def get_conversation_vector_memory_settings(conversation_id: str):
    """Get per-conversation vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        settings = await service_manager.memory_store.get_conversation_vector_memory_settings(conversation_id)
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversation vector memory settings: {str(e)}") from e


@router.put("/api/conversations/{conversation_id}/vector-memory")
async def set_conversation_vector_memory_settings(conversation_id: str, request: Request):
    """Update per-conversation vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        await service_manager.memory_store.set_conversation_vector_memory_settings(conversation_id, body)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set conversation vector memory settings: {str(e)}") from e


@router.get("/api/settings/memory")
async def get_memory_settings():
    """Get memory/context retrieval settings (similarity threshold, top-k)."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        similarity_threshold = await service_manager.memory_store.get_setting("memory_similarity_threshold", "0.7")
        top_k = await service_manager.memory_store.get_setting("memory_top_k", "5")
        
        return {
            "similarity_threshold": float(similarity_threshold),
            "top_k": int(top_k)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get memory settings: {str(e)}") from e


@router.put("/api/settings/memory")
async def update_memory_settings(request: Request):
    """Update memory/context retrieval settings (similarity threshold, top-k)."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        
        if "similarity_threshold" in body:
            threshold = float(body["similarity_threshold"])
            if not 0 <= threshold <= 1:
                raise HTTPException(status_code=400, detail="similarity_threshold must be between 0 and 1")
            await service_manager.memory_store.set_setting("memory_similarity_threshold", str(threshold))
        
        if "top_k" in body:
            top_k = int(body["top_k"])
            if top_k < 1:
                raise HTTPException(status_code=400, detail="top_k must be at least 1")
            await service_manager.memory_store.set_setting("memory_top_k", str(top_k))
        
        return {
            "status": "success",
            "message": "Memory retrieval settings updated"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update memory settings: {str(e)}") from e
