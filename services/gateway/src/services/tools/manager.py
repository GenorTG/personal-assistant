"""Simple tool manager for OpenAI function calling."""
from typing import List, Dict, Any, Optional
import logging

from .registry import ToolRegistry
from .executor import ToolExecutor

logger = logging.getLogger(__name__)


class ToolManager:
    """Simple tool manager - single entry point for tool operations."""
    
    def __init__(self, memory_store=None):
        """Initialize tool manager.
        
        Args:
            memory_store: Optional memory store for tools that need it
        """
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)
        self.memory_store = memory_store
        self._initialized = False
    
    async def initialize(self):
        """Initialize tool registry and executor."""
        if self._initialized:
            return
        
        # Initialize registry (registers built-in tools)
        await self.registry.initialize()
        
        # Update MemoryTools to use memory_store directly if available
        if self.memory_store:
            memory_tool = self.registry.get_tool("memory")
            if memory_tool and hasattr(memory_tool, 'memory_store'):
                memory_tool.memory_store = self.memory_store
                logger.info("Connected memory tool to memory store")
        
        self._initialized = True
        logger.info("Tool manager initialized")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools in OpenAI function calling format.
        
        Returns:
            List of tool definitions in OpenAI format
        """
        if not self._initialized:
            await self.initialize()
        
        return self.registry.list_tools()
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool in OpenAI format.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            OpenAI function schema or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        return self.registry.get_tool_schema(tool_name)
    
    async def execute_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Execute a list of tool calls.
        
        Args:
            tool_calls: List of tool call dictionaries from OpenAI format:
                [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "tool_name",
                            "arguments": "{\"param\": \"value\"}"  # JSON string
                        }
                    }
                ]
            conversation_id: Optional conversation ID for context
            
        Returns:
            List of tool execution results:
            [
                {
                    "id": "call_123",
                    "name": "tool_name",
                    "success": True,
                    "result": {...},
                    "error": None
                }
            ]
        """
        if not self._initialized:
            await self.initialize()
        
        results = []
        
        for tool_call in tool_calls:
            # Parse OpenAI format tool call
            tool_call_id = tool_call.get("id")
            function_data = tool_call.get("function", {})
            tool_name = function_data.get("name")
            arguments_str = function_data.get("arguments", "{}")
            
            # Parse arguments (OpenAI sends as JSON string)
            import json
            arguments = {}
            try:
                if isinstance(arguments_str, str):
                    arguments = json.loads(arguments_str)
                else:
                    arguments = arguments_str
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse arguments for tool '{tool_name}': {e}")
                results.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": f"Invalid JSON arguments: {str(e)}",
                    "arguments": {}  # Empty dict if parsing failed
                })
                continue
            
            # Execute tool
            try:
                execution_result = await self.executor.execute_tool(
                    tool_name=tool_name,
                    parameters=arguments,
                    conversation_id=conversation_id
                )
                
                # Format result with arguments included
                results.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "success": execution_result.get("error") is None,
                    "result": execution_result.get("result"),
                    "error": execution_result.get("error"),
                    "arguments": arguments  # Include original arguments for tool result messages
                })
                
            except Exception as e:
                logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
                results.append({
                    "id": tool_call_id,
                    "name": tool_name,
                    "success": False,
                    "result": None,
                    "error": str(e),
                    "arguments": arguments  # Include arguments (always available here)
                })
        
        return results
