"""Simple base tool interface for OpenAI function calling."""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """Base class for all tools using OpenAI function calling format.
    
    To create a new tool:
    1. Inherit from BaseTool
    2. Implement name, description, schema properties
    3. Implement execute method
    4. Register in ToolRegistry
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (must be unique)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM."""
        pass
    
    @property
    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """OpenAI function calling schema.
        
        Format:
        {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "..."
                }
            },
            "required": ["param_name"]
        }
        """
        pass
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool with given arguments.
        
        Args:
            arguments: Tool parameters from LLM
            
        Returns:
            {
                "result": Any,  # Tool result (will be JSON serialized)
                "error": Optional[str]  # Error message if failed
            }
        """
        pass


