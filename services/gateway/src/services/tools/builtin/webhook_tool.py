"""Webhook calling tool."""
from typing import Dict, Any
import httpx
from .base_tool import BaseTool


class WebhookTool(BaseTool):
    """Tool for calling webhooks."""
    
    def __init__(self):
        super().__init__(
            name="call_webhook",
            description="Make an HTTP request to a webhook URL",
            schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "format": "uri",
                        "description": "Webhook URL"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE"],
                        "default": "POST",
                        "description": "HTTP method"
                    },
                    "body": {
                        "type": "object",
                        "description": "Request body (for POST/PUT)"
                    }
                },
                "required": ["url"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute webhook tool."""
        url = arguments["url"]
        method = arguments.get("method", "POST")
        body = arguments.get("body")
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                json=body if body else None,
                timeout=10.0
            )
            
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text
            }
