"""API routes for Tool service."""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


# Request/Response models
class ExecuteToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    conversation_id: str = None


class ExecuteToolResponse(BaseModel):
    result: Any
    error: str = None
    tool_name: str


# Tool endpoints
@router.get("/tools")
async def list_tools(request: Request):
    """List all available tools."""
    tool_registry = request.app.state.tool_registry
    
    try:
        tools = tool_registry.list_tools()
        return {
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/{tool_name}/schema")
async def get_tool_schema(request: Request, tool_name: str):
    """Get schema for a specific tool."""
    tool_registry = request.app.state.tool_registry
    
    try:
        schema = tool_registry.get_tool_schema(tool_name)
        if schema is None:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/execute")
async def execute_tool(request: Request, body: ExecuteToolRequest):
    """Execute a tool."""
    from ..tools.executor import ToolExecutor
    
    tool_registry = request.app.state.tool_registry
    executor = ToolExecutor(tool_registry)
    
    try:
        result = await executor.execute_tool(
            tool_name=body.tool_name,
            parameters=body.parameters,
            conversation_id=body.conversation_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Calendar/Reminder endpoints (delegated to calendar tool)
@router.post("/reminders")
async def create_reminder(request: Request, reminder: Dict[str, Any]):
    """Create a reminder."""
    from ..tools.executor import ToolExecutor
    
    tool_registry = request.app.state.tool_registry
    executor = ToolExecutor(tool_registry)
    
    try:
        result = await executor.execute_tool(
            tool_name="calendar",
            parameters={
                "operation": "create",
                "title": reminder.get("title"),
                "description": reminder.get("description"),
                "due_at": reminder.get("due_at")
            }
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reminders")
async def list_reminders(request: Request):
    """List all reminders."""
    from ..tools.executor import ToolExecutor
    
    tool_registry = request.app.state.tool_registry
    executor = ToolExecutor(tool_registry)
    
    try:
        result = await executor.execute_tool(
            tool_name="calendar",
            parameters={"operation": "list"}
        )
        return result.get("result", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

