"""Tool management routes."""
import logging
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, Optional

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
        # Get tools in OpenAI format
        openai_tools = await service_manager.tool_manager.list_tools()
        
        # Transform to frontend-friendly format
        # OpenAI format: [{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}]
        # Frontend format: [{"name": "...", "description": "...", "parameters": {...}}]
        tools = []
        for tool_def in openai_tools:
            if isinstance(tool_def, dict):
                function_data = tool_def.get("function", {})
                if function_data:
                    tool_name = function_data.get("name", "")
                    if tool_name:
                        tools.append({
                            "name": tool_name,
                            "description": function_data.get("description", ""),
                            "parameters": function_data.get("parameters", {})
                        })
                    else:
                        logger.warning(f"Tool definition missing name: {tool_def}")
                else:
                    # Fallback: if already in flat format, use as-is
                    if "name" in tool_def:
                        tools.append(tool_def)
                    else:
                        logger.warning(f"Tool definition in unexpected format: {tool_def}")
        
        logger.info(f"Transformed {len(openai_tools)} OpenAI tools to {len(tools)} frontend tools")
        for tool in tools:
            logger.debug(f"  Tool: {tool.get('name')} - {tool.get('description', '')[:50]}...")
        
        return {
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        logger.error(f"Error listing tools: {e}", exc_info=True)
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


@router.post("/api/tools/execute")
async def execute_tool(request: Request):
    """Execute a tool with given parameters."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        body = await request.json()
        tool_name = body.get("tool_name")
        parameters = body.get("parameters", {})
        
        if not tool_name:
            raise HTTPException(
                status_code=400,
                detail="tool_name is required"
            )
        
        # Execute tool
        result = await service_manager.tool_manager.executor.execute_tool(
            tool_name=tool_name,
            parameters=parameters,
            conversation_id=None
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing tool: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to execute tool: {str(e)}") from e


@router.get("/api/tools/calendar/events")
async def list_calendar_events():
    """List all calendar events for debugging."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        # Get calendar tool and list events
        calendar_tool = service_manager.tool_manager.registry.get_tool("calendar")
        if not calendar_tool:
            raise HTTPException(
                status_code=404,
                detail="Calendar tool not found"
            )
        
        result = await calendar_tool.execute({"action": "list"})
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing calendar events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list calendar events: {str(e)}") from e


@router.get("/api/tools/todo/todos")
async def list_todos():
    """List all todos."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        todo_tool = service_manager.tool_manager.registry.get_tool("todo")
        if not todo_tool:
            raise HTTPException(
                status_code=404,
                detail="Todo tool not found"
            )
        
        result = await todo_tool.execute({"action": "list"})
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing todos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list todos: {str(e)}") from e


@router.get("/api/tools/debug")
async def get_tool_debug_info():
    """Get debug information about tool calling setup."""
    debug_info = {
        "tool_manager_initialized": service_manager.tool_manager is not None,
        "llm_manager_initialized": service_manager.llm_manager is not None,
        "model_loaded": False,
        "model_supports_tool_calling": False,
        "tool_manager_connected": False,
        "available_tools": [],
        "tool_count": 0
    }
    
    if service_manager.llm_manager:
        debug_info["model_loaded"] = service_manager.llm_manager.is_model_loaded()
        debug_info["model_supports_tool_calling"] = getattr(
            service_manager.llm_manager, 'supports_tool_calling', False
        )
        debug_info["tool_manager_connected"] = hasattr(
            service_manager.llm_manager, 'tool_manager'
        ) and service_manager.llm_manager.tool_manager is not None
    
    if service_manager.tool_manager:
        try:
            tools = await service_manager.tool_manager.list_tools()
            debug_info["available_tools"] = [t.get("name") for t in tools]
            debug_info["tool_count"] = len(tools)
        except Exception as e:
            debug_info["tool_list_error"] = str(e)
    
    return debug_info


@router.post("/api/tools/benchmark")
async def run_benchmark_test(model_name: Optional[str] = None):
    """Run benchmark test for function calling.
    
    Args:
        model_name: Optional model name/path. If not provided, uses currently loaded model.
        
    Returns:
        Dict with test results
    """
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Load model if specified
    if model_name:
        try:
            success = await service_manager.llm_manager.load_model(model_name)
            if not success:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to load model: {model_name}"
                )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error loading model: {str(e)}"
            )
    elif not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded and no model name provided"
        )
    
    # Check if tool calling is supported
    supports_tool_calling = getattr(
        service_manager.llm_manager, 'supports_tool_calling', False
    )
    
    # Initialize tool manager
    await service_manager.tool_manager.initialize()
    
    # Get benchmark tool
    tools = await service_manager.tool_manager.list_tools()
    benchmark_tool = None
    for tool in tools:
        if tool.get("function", {}).get("name") == "add_numbers":
            benchmark_tool = tool
            break
    
    if not benchmark_tool:
        raise HTTPException(
            status_code=500,
            detail="Benchmark tool 'add_numbers' not found"
        )
    
    # Run test
    test_message = "Calculate the sum of 3 and 5. Use the add_numbers tool."
    server_url = service_manager.llm_manager.server_manager.get_server_url()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": service_manager.llm_manager.current_model_name or "default",
                "messages": [
                    {"role": "user", "content": test_message}
                ],
                "tools": [benchmark_tool],
                "temperature": 0.7,
                "max_tokens": 512
            }
            
            response = await client.post(
                f"{server_url}/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # Check for tool calls
            choices = result.get("choices", [])
            if not choices:
                return {
                    "success": False,
                    "error": "No choices in response",
                    "result": result
                }
            
            message = choices[0].get("message", {})
            tool_calls = message.get("tool_calls", [])
            
            if tool_calls:
                # Execute tool call
                tool_results = await service_manager.tool_manager.execute_tools(tool_calls)
                
                return {
                    "success": True,
                    "tool_calls": len(tool_calls),
                    "tool_results": tool_results,
                    "message": "Benchmark test passed - model successfully made tool calls"
                }
            else:
                content = message.get("content", "")
                return {
                    "success": False,
                    "error": "No tool calls detected in response",
                    "response_content": content,
                    "result": result
                }
                
    except Exception as e:
        logger.error(f"Error running benchmark test: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Benchmark test failed: {str(e)}"
        ) from e