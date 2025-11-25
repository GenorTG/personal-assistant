"""Base tool class."""
from abc import ABC, abstractmethod
from typing import Dict, Any
import jsonschema


class BaseTool(ABC):
    """Base class for all tools."""
    
    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self.schema = schema
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """Validate arguments against tool schema."""
        try:
            jsonschema.validate(instance=arguments, schema=self.schema)
            return True
        except jsonschema.ValidationError:
            return False
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool with given arguments."""
        pass
