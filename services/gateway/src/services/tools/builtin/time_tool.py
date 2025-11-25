"""Time checking tool."""
from typing import Dict, Any
from datetime import datetime
from .base_tool import BaseTool


class TimeTool(BaseTool):
    """Tool for getting current time."""
    
    def __init__(self):
        super().__init__(
            name="get_current_time",
            description="Get the current date and time in ISO format",
            schema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> str:
        """Execute time tool."""
        return datetime.utcnow().isoformat()
