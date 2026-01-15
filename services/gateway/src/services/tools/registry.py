"""Simple tool registry for OpenAI function calling."""
from typing import Dict, List, Any, Optional
import logging
from .base_tool import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Simple registry for managing tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize and register all built-in tools."""
        if self._initialized:
            return

        logger.info("Registering built-in tools...")

        # Register built-in tools
        from .builtin.time_tool import TimeTool
        from .builtin.webhook_tool import WebhookTool
        from .builtin.google_search_tool import GoogleSearchTool
        from .builtin.calendar_tool import CalendarTool
        from .builtin.benchmark_tool import BenchmarkTool
        from .builtin.todo_tool import TodoTool

        tools_to_register = [
            TimeTool(),
            WebhookTool(),
            GoogleSearchTool(),
            CalendarTool(),
            BenchmarkTool(),
            TodoTool()
        ]

        for tool in tools_to_register:
            self.register_tool(tool)
            logger.info(f"Registered tool: {tool.name}")

        self._initialized = True
        logger.info(f"Tool registry initialized with {len(self.tools)} tools")
    
    def register_tool(self, tool: BaseTool):
        """Register a tool.
        
        Args:
            tool: Tool instance to register
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Tool must inherit from BaseTool, got {type(tool)}")
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None if not found
        """
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools in OpenAI function calling format.
        
        Returns:
            List of tool definitions in OpenAI format with 'title' fields for chatml-function-calling:
            [
                {
                    "type": "function",
                    "function": {
                        "name": "tool_name",
                        "description": "...",
                        "parameters": {
                            "type": "object",
                            "title": "tool_name",  # CRITICAL for chatml-function-calling
                            "properties": {
                                "param": {
                                    "title": "Param",  # CRITICAL for chatml-function-calling
                                    "type": "integer"
                                }
                            },
                            "required": ["param"]
                        }
                    }
                }
            ]
        """
        tools_list = []
        for tool in self.tools.values():
            # Format schema with title fields for chatml-function-calling compatibility
            schema = tool.schema.copy()
            
            # Ensure schema has 'title' field at root level
            if "title" not in schema:
                schema["title"] = tool.name
            
            # Ensure all properties have 'title' fields
            if "properties" in schema:
                for prop_name, prop_def in schema["properties"].items():
                    if not isinstance(prop_def, dict):
                        continue
                    if "title" not in prop_def:
                        # Capitalize first letter for title
                        prop_def["title"] = prop_name.capitalize()
            
            tools_list.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": schema
                }
            })
        return tools_list
    
    def get_tool_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool in OpenAI format with title fields.
        
        Args:
            name: Tool name
            
        Returns:
            OpenAI function schema with title fields or None if not found
        """
        tool = self.get_tool(name)
        if tool:
            # Format schema with title fields for chatml-function-calling compatibility
            schema = tool.schema.copy()
            
            # Ensure schema has 'title' field at root level
            if "title" not in schema:
                schema["title"] = tool.name
            
            # Ensure all properties have 'title' fields
            if "properties" in schema:
                for prop_name, prop_def in schema["properties"].items():
                    if not isinstance(prop_def, dict):
                        continue
                    if "title" not in prop_def:
                        # Capitalize first letter for title
                        prop_def["title"] = prop_name.capitalize()
            
            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": schema
                }
            }
        return None
