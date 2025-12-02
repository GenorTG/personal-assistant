"""Tool registry for managing available tools."""
from typing import Dict, List, Any, Optional
import logging
from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing and discovering tools."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize and register all built-in tools."""
        if self._initialized:
            return
        
        logger.info("Registering built-in tools...")
        
        # Register built-in tools
        from .builtin.web_search import WebSearchTool
        from .builtin.code_exec import CodeExecutionTool
        from .builtin.file_access import FileAccessTool
        from .builtin.memory import MemoryTools
        from .builtin.calendar import CalendarTool
        
        tools_to_register = [
            WebSearchTool(),
            CodeExecutionTool(),
            FileAccessTool(),
            MemoryTools(),
            CalendarTool()
        ]
        
        for tool in tools_to_register:
            self.register_tool(tool)
            logger.info(f"Registered tool: {tool.name}")
        
        self._initialized = True
        logger.info(f"Tool registry initialized with {len(self.tools)} tools")
    
    def register_tool(self, tool: BaseTool):
        """Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
        """
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.
        
        Args:
            name: Tool name
        
        Returns:
            Tool instance or None if not found
        """
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with their schemas.
        
        Returns:
            List of tool schemas in OpenAI function calling format
        """
        return [
            tool.get_schema()
            for tool in self.tools.values()
        ]
    
    def get_tool_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool.
        
        Args:
            name: Tool name
        
        Returns:
            Tool schema or None if not found
        """
        tool = self.get_tool(name)
        if tool:
            return tool.get_schema()
        return None

