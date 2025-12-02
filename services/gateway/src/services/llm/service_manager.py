"""LLM Service Manager - Simple wrapper for the LLM service."""
import logging
import httpx
from ...config.settings import settings

logger = logging.getLogger(__name__)


class LLMServiceManager:
    """Manages LLM service connection."""
    
    def __init__(self):
        self._service_url = settings.llm_service_url
    
    def get_service_url(self) -> str:
        """Get the URL for the LLM service."""
        return self._service_url
    
    async def is_service_running(self) -> bool:
        """Check if the LLM service is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._service_url}/v1/models")
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"LLM service health check failed: {e}")
            return False
    
    async def get_service_status(self) -> dict:
        """Get status of the LLM service."""
        is_running = await self.is_service_running()
        
        return {
            "running": is_running,
            "url": self._service_url
        }
