"""Service Status Manager - Centralized health monitoring for all microservices."""
# Standard library
import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional

# Third-party
import httpx

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    READY = "ready"
    OFFLINE = "offline"
    ERROR = "error"


class ServiceStatusManager:
    """Manages health status for all microservices with adaptive background polling."""
    
    def __init__(self, service_manager=None):
        self.status_cache: Dict[str, Dict[str, Any]] = {}
        self.polling_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.poll_interval = 30  # Start with 30 seconds (stable interval)
        self.stable_count = 0  # Track consecutive stable checks
        self.last_logged_state: Dict[str, str] = {}  # Track last logged state for each service
        self._service_manager_ref = service_manager  # Store reference to avoid import issues
        
        # Service registry with health endpoints
        # Note: STT, Piper, and Kokoro are now integrated natively into gateway
        # Only Chatterbox remains as an optional HTTP service
        self.services = {
            "stt": {
                "url": None,  # STT is integrated, check via service_manager
                "health_path": None,
                "type": "stt",
                "internal": True
            },
            "tts_piper": {
                "url": None,  # Piper is integrated, check via service_manager
                "health_path": None,
                "type": "tts",
                "internal": True
            },
            "tts_chatterbox": {
                "url": "http://localhost:4123",
                "health_path": "/health",
                "type": "tts"
            },
            "tts_kokoro": {
                "url": None,  # Kokoro is integrated, check via service_manager
                "health_path": None,
                "type": "tts",
                "internal": True
            },
            "llm": {
                "url": None,  # LLM is integrated, check via service_manager
                "health_path": None,
                "type": "llm",
                "internal": True
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
    
    async def _check_service(self, name: str, config: Dict[str, Any]):
        """Check health of a single service."""
        start_time = datetime.now()
        previous_status = self.status_cache.get(name, {}).get("status")
        
        # Handle internal services (like LLM) that are integrated into gateway
        if config.get("internal"):
            try:
                # Use stored reference to avoid import issues
                if not self._service_manager_ref:
                    # Fallback: import at runtime using relative import
                    try:
                        from ..service_manager import service_manager as sm
                        self._service_manager_ref = sm
                    except ImportError:
                        # Last resort: try absolute import
                        import sys
                        from pathlib import Path
                        gateway_src = Path(__file__).parent.parent
                        if str(gateway_src) not in sys.path:
                            sys.path.insert(0, str(gateway_src))
                        from services.service_manager import service_manager as sm
                        self._service_manager_ref = sm
                
                service_manager = self._service_manager_ref
                
                if name == "llm":
                    # Check LLM status via service_manager
                    if service_manager.llm_manager and service_manager.llm_manager.is_model_loaded():
                        new_status = ServiceStatus.READY
                        response_time = (datetime.now() - start_time).total_seconds() * 1000
                        self.status_cache[name] = {
                            "status": new_status,
                            "last_check": datetime.now().isoformat(),
                            "response_time_ms": round(response_time, 2),
                            "error": None,
                            "type": config["type"]
                        }
                    else:
                        new_status = ServiceStatus.OFFLINE
                        response_time = (datetime.now() - start_time).total_seconds() * 1000
                        self.status_cache[name] = {
                            "status": new_status,
                            "last_check": datetime.now().isoformat(),
                            "response_time_ms": round(response_time, 2),
                            "error": "Model not loaded",
                            "type": config["type"]
                        }
                elif name == "stt":
                    # Check STT status (native faster-whisper)
                    if service_manager.stt_service:
                        # Check if actually initialized
                        is_initialized = getattr(service_manager.stt_service, '_initialized', False)
                        if is_initialized:
                            new_status = ServiceStatus.READY
                            response_time = (datetime.now() - start_time).total_seconds() * 1000
                            self.status_cache[name] = {
                                "status": new_status,
                                "last_check": datetime.now().isoformat(),
                                "response_time_ms": round(response_time, 2),
                                "error": None,
                                "type": config["type"]
                            }
                        else:
                            new_status = ServiceStatus.OFFLINE
                            self.status_cache[name] = {
                                "status": new_status,
                                "last_check": datetime.now().isoformat(),
                                "response_time_ms": None,
                                "error": "STT service exists but model not initialized",
                                "type": config["type"]
                            }
                    else:
                        new_status = ServiceStatus.OFFLINE
                        self.status_cache[name] = {
                            "status": new_status,
                            "last_check": datetime.now().isoformat(),
                            "response_time_ms": None,
                            "error": "STT service not initialized",
                            "type": config["type"]
                        }
                elif name in ["tts_piper", "tts_kokoro"]:
                    # Check TTS backend status
                    if service_manager.tts_service and service_manager.tts_service.manager:
                        backend_name = "piper" if name == "tts_piper" else "kokoro"
                        try:
                            backend = service_manager.tts_service.manager.get_backend(backend_name)
                            if backend:
                                # Check if backend is ready (initialized and working)
                                is_ready = getattr(backend, 'is_ready', False)
                                error_message = getattr(backend, 'error_message', None)
                                
                                if is_ready and not error_message:
                                    new_status = ServiceStatus.READY
                                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                                    self.status_cache[name] = {
                                        "status": new_status,
                                        "last_check": datetime.now().isoformat(),
                                        "response_time_ms": round(response_time, 2),
                                        "error": None,
                                        "type": config["type"]
                                    }
                                else:
                                    # Backend exists but not ready
                                    new_status = ServiceStatus.OFFLINE if not error_message else ServiceStatus.ERROR
                                    error_msg = error_message or "Backend not initialized"
                                    self.status_cache[name] = {
                                        "status": new_status,
                                        "last_check": datetime.now().isoformat(),
                                        "response_time_ms": None,
                                        "error": error_msg,
                                        "type": config["type"]
                                    }
                            else:
                                new_status = ServiceStatus.OFFLINE
                                self.status_cache[name] = {
                                    "status": new_status,
                                    "last_check": datetime.now().isoformat(),
                                    "response_time_ms": None,
                                    "error": f"{backend_name} backend not found",
                                    "type": config["type"]
                                }
                        except Exception as e:
                            new_status = ServiceStatus.OFFLINE
                            self.status_cache[name] = {
                                "status": new_status,
                                "last_check": datetime.now().isoformat(),
                                "response_time_ms": None,
                                "error": f"Error checking {backend_name}: {str(e)}",
                                "type": config["type"]
                            }
                    else:
                        new_status = ServiceStatus.OFFLINE
                        self.status_cache[name] = {
                            "status": new_status,
                            "last_check": datetime.now().isoformat(),
                            "response_time_ms": None,
                            "error": "TTS service not initialized",
                            "type": config["type"]
                        }
                else:
                    # Unknown internal service
                    new_status = ServiceStatus.OFFLINE
                    self.status_cache[name] = {
                        "status": new_status,
                        "last_check": datetime.now().isoformat(),
                        "response_time_ms": None,
                        "error": "Unknown internal service",
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
        else:
            # External HTTP service check
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
        
        # Broadcast WebSocket event when status changes
        if previous_status != new_status:
            logger.info(f"Service {name} status changed: {previous_status} -> {new_status}")
            self.last_logged_state[name] = new_status
            
            # Broadcast status change via WebSocket
            try:
                from ..websocket_manager import get_websocket_manager
                ws_manager = get_websocket_manager()
                
                # Get all current statuses for the broadcast
                all_statuses = self.get_all_statuses()
                
                # Format status for frontend (match the format from get_services_status)
                formatted_status = {
                    "stt": all_statuses.get("stt", {}),
                    "tts": {
                        "piper": all_statuses.get("tts_piper", {}),
                        "kokoro": all_statuses.get("tts_kokoro", {}),
                        "chatterbox": all_statuses.get("tts_chatterbox", {})
                    },
                    "llm": all_statuses.get("llm", {}),
                    "last_poll": max(
                        (s.get("last_check") for s in all_statuses.values() if s.get("last_check")),
                        default=None
                    )
                }
                
                # Broadcast the event (await since we're in async context)
                await ws_manager.broadcast_service_status(formatted_status)
                
                # Also broadcast full debug info update for debug panel
                try:
                    from ...api.routes.system import _get_debug_info_internal
                    debug_info = await _get_debug_info_internal()
                    await ws_manager.broadcast_debug_info_updated(debug_info)
                except Exception as e:
                    logger.debug(f"Failed to broadcast debug info update: {e}")
            except Exception as e:
                logger.debug(f"Failed to broadcast service status change: {e}")
    
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
