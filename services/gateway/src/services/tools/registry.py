"""Tool registry for managing available tools."""
from typing import Dict, Any, Optional, List
from .builtin.time_tool import TimeTool
from .builtin.webhook_tool import WebhookTool


class ToolRegistry:
    """Registry of available tools."""
    
    def __init__(self):
        self.tools: Dict[str, Any] = {}
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register built-in tools."""
        self.register_tool(TimeTool())
        self.register_tool(WebhookTool())
    
    def register_tool(self, tool: Any):
        """Register a tool."""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Any]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with their schemas."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "schema": tool.schema
            }
            for tool in self.tools.values()
        ]
