"""Tool management routes."""
import logging
from fastapi import APIRouter, HTTPException

from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tools"])


@router.get("/api/tools")
async def list_tools():
    """List all available tools with their schemas."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        tools = await service_manager.tool_manager.list_tools()
        return {
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}") from e


@router.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get information about a specific tool."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        tool_schema = await service_manager.tool_manager.get_tool_schema(tool_name)
        if not tool_schema:
            raise HTTPException(
                status_code=404,
                detail=f"Tool '{tool_name}' not found"
            )
        
        return tool_schema
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tool info: {str(e)}") from e
