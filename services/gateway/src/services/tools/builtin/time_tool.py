"""Time checking tool."""
from typing import Dict, Any
from datetime import datetime
from ..base_tool import BaseTool


class TimeTool(BaseTool):
    """Tool for getting current time."""
    
    @property
    def name(self) -> str:
        return "get_current_time"
    
    @property
    def description(self) -> str:
        return "Get the current date and time in ISO format"
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute time tool."""
        return {
            "result": datetime.utcnow().isoformat(),
            "error": None
        }
