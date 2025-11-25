"""Tool manager for executing tools."""
from typing import List, Dict, Any
from .registry import ToolRegistry
from .parser import ToolCallParser


class ToolManager:
    """Manages tool execution."""
    
    def __init__(self):
        self.registry = ToolRegistry()
        self.parser = ToolCallParser()
    
    async def execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute a list of tool calls."""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})
            
            # Get tool from registry
            tool = self.registry.get_tool(tool_name)
            if not tool:
                results.append({
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": f"Tool '{tool_name}' not found"
                })
                continue
            
            # Validate arguments
            if not tool.validate_arguments(arguments):
                results.append({
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": "Invalid arguments"
                })
                continue
            
            # Execute tool
            try:
                result = await tool.execute(arguments)
                results.append({
                    "name": tool_name,
                    "success": True,
                    "result": result,
                    "error": None
                })
            except Exception as e:
                results.append({
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": str(e)
                })
        
        return results
