"""Service Status Manager - Centralized health monitoring for all microservices."""
import asyncio
import httpx
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    READY = "ready"
    OFFLINE = "offline"
    ERROR = "error"


class ServiceStatusManager:
    """Manages health status for all microservices with background polling."""
    
    def __init__(self):
        self.status_cache: Dict[str, Dict[str, Any]] = {}
        self.polling_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.poll_interval = 10  # Industry standard: 10 seconds
        
        # Service registry with health endpoints
        self.services = {
            "stt": {
                "url": "http://localhost:8003",
                "health_path": "/health",
                "type": "stt"
            },
            "tts_piper": {
                "url": "http://localhost:8001",
                "health_path": "/health",
                "type": "tts"
            },
            "tts_chatterbox": {
                "url": "http://localhost:8005",
                "health_path": "/health",
                "type": "tts"
            },
            "tts_kokoro": {
                "url": "http://localhost:8006",
                "health_path": "/health",
                "type": "tts"
            },
            "llm": {
                "url": "http://localhost:8002",
                "health_path": "/health",
                "type": "llm"
            }
        }
        
        # Initialize cache with offline status
        for service_name in self.services:
            self.status_cache[service_name] = {
                "status": ServiceStatus.OFFLINE,
                "last_check": None,
                "response_time_ms": None,
                "error": None
            }
    
    async def start(self):
        """Start background polling task."""
        if self.is_running:
            logger.warning("Status manager already running")
            return
            
        self.is_running = True
        self.polling_task = asyncio.create_task(self._polling_loop())
        logger.info(f"Service status manager started (polling every {self.poll_interval}s)")
    
    async def stop(self):
        """Stop background polling task."""
        self.is_running = False
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        logger.info("Service status manager stopped")
    
    async def _polling_loop(self):
        """Background task that continuously polls all services."""
        while self.is_running:
            try:
                await self._poll_all_services()
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    async def _poll_all_services(self):
        """Poll all registered services concurrently."""
        tasks = [
            self._check_service(name, config)
            for name, config in self.services.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_service(self, name: str, config: Dict[str, str]):
        """Check health of a single service."""
        start_time = datetime.now()
        
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                url = f"{config['url']}{config['health_path']}"
                response = await client.get(url)
                
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if response.status_code == 200:
                    self.status_cache[name] = {
                        "status": ServiceStatus.READY,
                        "last_check": datetime.now().isoformat(),
                        "response_time_ms": round(response_time, 2),
                        "error": None,
                        "type": config["type"]
                    }
                else:
                    self.status_cache[name] = {
                        "status": ServiceStatus.ERROR,
                        "last_check": datetime.now().isoformat(),
                        "response_time_ms": round(response_time, 2),
                        "error": f"HTTP {response.status_code}",
                        "type": config["type"]
                    }
        except Exception as e:
            self.status_cache[name] = {
                "status": ServiceStatus.OFFLINE,
                "last_check": datetime.now().isoformat(),
                "response_time_ms": None,
                "error": str(e),
                "type": config["type"]
            }
    
    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get cached status for all services."""
        return self.status_cache.copy()
    
    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get cached status for a specific service."""
        return self.status_cache.get(service_name)
    
    def is_service_ready(self, service_name: str) -> bool:
        """Check if a service is ready (convenience method)."""
        status = self.status_cache.get(service_name, {})
        return status.get("status") == ServiceStatus.READY
