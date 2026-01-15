"""Health check proxy routes."""
import logging
from fastapi import APIRouter, HTTPException, Response
import httpx

from ....services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy", "health"])


@router.get("/v1/models")
async def proxy_list_models():
    """Get list of available models."""
    try:
        if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
            return Response(
                content='{"object": "list", "data": []}'.encode('utf-8'),
                status_code=200,
                media_type="application/json"
            )

        llm_manager = service_manager.llm_manager
        model_name = llm_manager.current_model_name or "unknown"

        # Return OpenAI-compatible format
        models_data = {
            "object": "list",
            "data": [{
                "id": model_name,
                "object": "model",
                "created": 0,
                "owned_by": "local"
            }]
        }

        return Response(
            content=str(models_data).replace("'", '"').encode('utf-8'),
            status_code=200,
            media_type="application/json"
        )
    except Exception as e:
        logger.error(f"Error getting models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting models: {str(e)}") from e


@router.get("/api/llm/status")
async def get_llm_status():
    """Get LLM service status."""
    try:
        if not service_manager.llm_manager:
            return {
                "status": "not_initialized",
                "model_loaded": False,
                "model_name": None
            }

        llm_manager = service_manager.llm_manager
        return {
            "status": "running" if llm_manager.is_model_loaded() else "stopped",
            "model_loaded": llm_manager.is_model_loaded(),
            "model_name": llm_manager.current_model_name,
            "supports_tool_calling": getattr(llm_manager, 'supports_tool_calling', False)
        }
    except Exception as e:
        logger.error(f"Error getting LLM service status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/v1/models/{model_id}")
async def proxy_get_model(model_id: str):
    """Get model information."""
    try:
        if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
            raise HTTPException(
                status_code=404,
                detail="Model not found"
            )

        llm_manager = service_manager.llm_manager
        current_model = llm_manager.current_model_name

        if model_id != current_model:
            raise HTTPException(
                status_code=404,
                detail="Model not found"
            )

        # Return OpenAI-compatible format
        model_data = {
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": "local"
        }

        return Response(
            content=str(model_data).replace("'", '"').encode('utf-8'),
            status_code=200,
            media_type="application/json"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting model: {str(e)}") from e


