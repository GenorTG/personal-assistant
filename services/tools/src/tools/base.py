"""Base tool interface."""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseTool(ABC):
    """Base class for all tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description."""
        pass
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Get tool schema in OpenAI function calling format.
        
        Returns:
            Dictionary with 'name', 'description', and 'parameters' fields
        """
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool.
        
        Args:
            **kwargs: Tool-specific parameters
        
        Returns:
            Dictionary with 'result' and optionally 'error' fields
        """
        pass
    
    def validate_parameters(self, **kwargs) -> bool:
        """Validate tool parameters.
        
        Args:
            **kwargs: Parameters to validate
        
        Returns:
            True if valid, False otherwise
        """
        return True  # Default: accept all parameters

