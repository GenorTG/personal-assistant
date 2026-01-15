"""Simple tool executor for direct execution."""
from typing import Dict, Any, Optional
import logging
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Simple tool executor - direct execution, no protocol layers."""

    def __init__(self, tool_registry: ToolRegistry):
        """Initialize executor with tool registry.
        
        Args:
            tool_registry: Tool registry instance
        """
        self.tool_registry = tool_registry

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a tool directly.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            conversation_id: Optional conversation ID for context (not used currently)
            
        Returns:
            {
                "result": Any,  # Tool execution result
                "error": Optional[str]  # Error message if failed
            }
        """
        tool = self.tool_registry.get_tool(tool_name)

        if not tool:
            logger.error(f"Tool '{tool_name}' not found")
            return {
                "error": f"Tool '{tool_name}' not found",
                "result": None
            }

        try:
            # Execute tool directly
            result = await tool.execute(parameters)
            
            # Ensure result has expected format
            if not isinstance(result, dict):
                result = {"result": result, "error": None}
            elif "result" not in result:
                result = {"result": result, "error": result.get("error")}

            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return {
                "error": str(e),
                "result": None
            }
