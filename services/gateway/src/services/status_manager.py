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
    """Manages health status for all microservices with adaptive background polling."""
    
    def __init__(self):
        self.status_cache: Dict[str, Dict[str, Any]] = {}
        self.polling_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.poll_interval = 30  # Start with 30 seconds (stable interval)
        self.stable_count = 0  # Track consecutive stable checks
        self.last_logged_state: Dict[str, str] = {}  # Track last logged state for each service
        
        # Service registry with health endpoints
        self.services = {
            "stt": {
                "url": "http://localhost:8003",
                "health_path": "/health",
                "type": "stt"
            },
            "tts_piper": {
                "url": "http://localhost:8004",
                "health_path": "/health",
                "type": "tts"
            },
            "tts_chatterbox": {
                "url": "http://localhost:4123",
                "health_path": "/health",
                "type": "tts"
            },
            "tts_kokoro": {
                "url": "http://localhost:8880",
                "health_path": "/health",
                "type": "tts"
            },
            "llm": {
                "url": "http://localhost:8001",
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
        logger.info(f"Service status manager started (adaptive polling: {self.poll_interval}s initial, adjusts based on stability)")
    
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
        """Background task that continuously polls all services with adaptive intervals."""
        while self.is_running:
            try:
                await self._poll_all_services()
                
                # Adaptive polling: check if all services are stable
                all_stable = all(
                    status.get("status") == ServiceStatus.READY 
                    for status in self.status_cache.values()
                )
                
                if all_stable:
                    self.stable_count += 1
                    # After 3 consecutive stable checks, increase interval to 30s
                    if self.stable_count >= 3 and self.poll_interval != 30:
                        self.poll_interval = 30
                        logger.debug(f"All services stable, increasing poll interval to {self.poll_interval}s")
                else:
                    self.stable_count = 0
                    # If any service is unstable, reduce interval to 10s
                    if self.poll_interval != 10:
                        self.poll_interval = 10
                        logger.debug(f"Services unstable, reducing poll interval to {self.poll_interval}s")
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                self.stable_count = 0
                self.poll_interval = 10  # Reduce interval on error
            
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
        previous_status = self.status_cache.get(name, {}).get("status")
        
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                url = f"{config['url']}{config['health_path']}"
                response = await client.get(url)
                
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if response.status_code == 200:
                    new_status = ServiceStatus.READY
                    self.status_cache[name] = {
                        "status": new_status,
                        "last_check": datetime.now().isoformat(),
                        "response_time_ms": round(response_time, 2),
                        "error": None,
                        "type": config["type"]
                    }
                else:
                    new_status = ServiceStatus.ERROR
                    self.status_cache[name] = {
                        "status": new_status,
                        "last_check": datetime.now().isoformat(),
                        "response_time_ms": round(response_time, 2),
                        "error": f"HTTP {response.status_code}",
                        "type": config["type"]
                    }
        except Exception as e:
            new_status = ServiceStatus.OFFLINE
            self.status_cache[name] = {
                "status": new_status,
                "last_check": datetime.now().isoformat(),
                "response_time_ms": None,
                "error": str(e),
                "type": config["type"]
            }
        
        # Only log state changes (not every check)
        if previous_status != new_status:
            logger.info(f"Service {name} status changed: {previous_status} -> {new_status}")
            self.last_logged_state[name] = new_status
    
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
