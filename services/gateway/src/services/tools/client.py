"""HTTP client for Tool service."""
from typing import List, Dict, Any, Optional
import httpx
import logging
from ...config.settings import settings

logger = logging.getLogger(__name__)


class ToolServiceClient:
    """HTTP client for communicating with Tool service."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or "http://localhost:8006"
        self.timeout = 60.0  # Longer timeout for tool execution
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Tool service."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            logger.warning(f"Tool service not available at {self.base_url}")
            raise RuntimeError("Tool service not available")
        except httpx.HTTPStatusError as e:
            logger.error(f"Tool service error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error calling Tool service: {e}", exc_info=True)
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools."""
        try:
            result = await self._request("GET", "/api/tools")
            return result.get("tools", [])
        except RuntimeError:
            return []
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool."""
        try:
            return await self._request("GET", f"/api/tools/{tool_name}/schema")
        except RuntimeError:
            return None
    
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
            conversation_id: Optional conversation ID
        
        Returns:
            Dictionary with execution result
        """
        return await self._request(
            "POST",
            "/api/tools/execute",
            json_data={
                "tool_name": tool_name,
                "parameters": parameters,
                "conversation_id": conversation_id
            }
        )
    
    async def is_available(self) -> bool:
        """Check if Tool service is available."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

