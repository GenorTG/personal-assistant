"""Tool execution orchestrator."""
from typing import Dict, Any, Optional
import logging
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Orchestrates tool execution."""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a tool.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            conversation_id: Optional conversation ID for context
        
        Returns:
            Dictionary with execution result
        """
        tool = self.tool_registry.get_tool(tool_name)
        
        if not tool:
            return {
                "error": f"Tool '{tool_name}' not found",
                "result": None
            }
        
        # Validate parameters
        if not tool.validate_parameters(**parameters):
            return {
                "error": f"Invalid parameters for tool '{tool_name}'",
                "result": None
            }
        
        try:
            # Execute tool
            result = await tool.execute(**parameters)
            
            # Log execution
            logger.info(f"Tool '{tool_name}' executed successfully")
            
            return {
                "result": result.get("result"),
                "error": result.get("error"),
                "tool_name": tool_name
            }
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return {
                "error": str(e),
                "result": None,
                "tool_name": tool_name
            }

