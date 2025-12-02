"""Tool manager for executing tools via Tool Service."""
from typing import List, Dict, Any, Optional
from .client import ToolServiceClient
from .parser import ToolCallParser


class ToolManager:
    """Manages tool execution via Tool Service."""
    
    def __init__(self, tool_service_client: Optional[ToolServiceClient] = None):
        self.client = tool_service_client or ToolServiceClient()
        self.parser = ToolCallParser()
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        if self._tools_cache is None:
            self._tools_cache = await self.client.list_tools()
        return self._tools_cache
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool."""
        return await self.client.get_tool_schema(tool_name)
    
    async def execute_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute a list of tool calls via Tool Service.
        
        Args:
            tool_calls: List of tool call dictionaries with 'name' and 'arguments'
            conversation_id: Optional conversation ID for context
        
        Returns:
            List of tool execution results
        """
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})
            tool_call_id = tool_call.get("id")
            
            try:
                # Execute via Tool Service
                result = await self.client.execute_tool(
                    tool_name=tool_name,
                    parameters=arguments,
                    conversation_id=conversation_id
                )
                
                # Format result for compatibility
                if result.get("error"):
                    results.append({
                        "id": tool_call_id,
                        "name": tool_name,
                        "success": False,
                        "result": None,
                        "error": result.get("error")
                    })
                else:
                    results.append({
                        "id": tool_call_id,
                        "name": tool_name,
                        "success": True,
                        "result": result.get("result"),
                        "error": None
                    })
            except RuntimeError as e:
                # Tool service unavailable
                results.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": f"Tool service unavailable: {str(e)}"
                })
            except Exception as e:
                results.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": str(e)
                })
        
        return results
