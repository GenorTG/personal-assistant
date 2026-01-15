import logging
import httpx
from typing import Optional, Dict, Any

from ..config.settings import settings

logger = logging.getLogger(__name__)

class ServiceManager:
    """Manages connections to microservices."""
    
    def __init__(self):
        # Service URLs (for optional external services if needed)
        self.llm_service_url = "http://127.0.0.1:8001"  # OpenAI-compatible LLM server (started automatically when model loads)
        # STT and TTS are now integrated natively, no HTTP URLs needed
        
        # Use LLM service's LLMManager directly (merged from LLM service)
        from .llm.manager import LLMManager
        self.llm_manager = LLMManager()
        self.llm_service_manager = None  # No longer needed - using direct manager
        self.chat_manager = None
        self.memory_store = None
        self.tool_manager = None # Renamed from tool_registry
        self.stt_service = None # Remote STT
        self.tts_service = None # Remote TTS
        self.status_manager = None # Service status monitoring
        
    async def initialize(self):
        """Initialize services."""
        from .chat.manager import ChatManager
        from .memory.store import MemoryStore
        from .tools.manager import ToolManager # Use ToolManager
        from .status_manager import ServiceStatusManager
        
        # Initialize Memory Store (file-based storage - no separate service needed)
        self.memory_store = MemoryStore()
        await self.memory_store.initialize()
        logger.info("Memory store initialized (file-based)")
        
        # Load settings from file stores into LLM manager
        if self.llm_manager:
            await self.llm_manager.load_settings_from_file_stores(self.memory_store)
        
        # LLM Service Manager no longer needed - using direct manager
        self.llm_service_manager = None
        
        # Initialize Tool Manager directly (merged from tools service)
        from .tools.manager import ToolManager
        self.tool_manager = ToolManager(memory_store=self.memory_store)
        await self.tool_manager.initialize()
        logger.info("Tool manager initialized (direct import, no HTTP)")
        
        # Connect tool registry to LLM manager for function calling
        # The LLM manager needs access to tool_manager to list tools when generating responses
        if self.llm_manager and self.tool_manager:
            # Store tool_manager reference in LLM manager for async tool listing
            self.llm_manager.tool_manager = self.tool_manager
            logger.info("Tool manager connected to LLM manager")
        
        # Initialize Chat Manager
        self.chat_manager = ChatManager(self, self.memory_store, self.tool_manager) # Pass tool_manager
        
        # Initialize WebSocket Manager
        from .websocket_manager import get_websocket_manager
        self.websocket_manager = get_websocket_manager()
        logger.info("WebSocket manager initialized")
        
        # Initialize TTS Service
        try:
            from .tts.service import TTSService
            self.tts_service = TTSService()
            logger.info("TTS Service initialized successfully")
        except ImportError as e:
            logger.warning(f"Failed to import TTS service: {e}")
            import traceback
            logger.debug(f"TTS import error traceback: {traceback.format_exc()}")
            self.tts_service = None
        except Exception as e:
            logger.warning(f"Failed to initialize TTS service: {e}")
            import traceback
            logger.debug(f"TTS initialization error traceback: {traceback.format_exc()}")
            self.tts_service = None
        
        # STT Service - Use native implementation (faster-whisper)
        # Preload model on startup for fast inference
        from .stt.service import STTService
        self.stt_service = STTService()
        # Preload STT model to keep it in memory
        try:
            self.stt_service._initialize_model()
            logger.info("STT Service initialized and model preloaded (native faster-whisper)")
        except Exception as e:
            logger.warning(f"Failed to preload STT model: {e}. Will load on first use.")
            # Don't fail startup if model preload fails - will load on first use
        
        # Initialize and start Service Status Manager
        # Pass self as service_manager reference to avoid import issues
        self.status_manager = ServiceStatusManager(service_manager=self)
        
        # Run initializations in parallel to speed up startup
        import asyncio
        
        async def init_tts():
            if self.tts_service:
                # Load saved backend selection, but never block startup on large model downloads.
                # We default to built-in/local backends, and only download models when prompted
                # (i.e., when the user switches to that backend or uses it).
                saved_backend = await self.memory_store.get_setting("tts_backend", "pyttsx3")

                preferred_backends = {"piper", "kokoro", "pyttsx3"}
                selected_backend = saved_backend if saved_backend in preferred_backends else "pyttsx3"

                # Never auto-select chatterbox on startup (external service)
                if selected_backend not in preferred_backends:
                    selected_backend = "pyttsx3"

                await self.tts_service.switch_backend(selected_backend)

                if selected_backend != saved_backend:
                    await self.memory_store.set_setting("tts_backend", selected_backend)

                # Try a fast init, but do NOT block startup if it takes too long.
                try:
                    backend_obj = self.tts_service.manager.current_backend
                    if backend_obj:
                        import asyncio as _asyncio
                        await _asyncio.wait_for(backend_obj.initialize(), timeout=2.0)
                except Exception:
                    pass
                
                logger.info(f"TTS Service initialized with backend: {selected_backend or saved_backend} (models preloaded)")
            else:
                logger.info("TTS Service not available, skipping initialization")
            
        async def init_status():
            await self.status_manager.start()
            logger.info("Service status manager started")
            
        # Execute parallel initialization
        await asyncio.gather(
            init_tts(),
            init_status()
        )
        
        logger.info("Gateway Services Initialized")

    async def shutdown(self) -> None:
        """Gracefully shut down background tasks/services."""
        try:
            # Stop LLM server process first
            if self.llm_manager and hasattr(self.llm_manager, 'server_manager'):
                try:
                    logger.info("Stopping LLM server process...")
                    await self.llm_manager.server_manager.stop_server()
                    logger.info("✓ LLM server stopped")
                except Exception as e:
                    logger.error(f"Error stopping LLM server: {e}", exc_info=True)
            
            # Stop status manager
            if self.status_manager:
                try:
                    await self.status_manager.stop()
                except Exception:
                    logger.debug("Failed stopping status manager", exc_info=True)
            
            # Cleanup any zombie processes
            if self.llm_manager and hasattr(self.llm_manager, 'server_manager'):
                try:
                    await self.llm_manager.server_manager._cleanup_all_llm_processes()
                except Exception as e:
                    logger.debug(f"Error during process cleanup: {e}", exc_info=True)
        finally:
            return None
    
    def get_service_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage for all integrated services."""
        import psutil
        
        memory_info = {
            "gateway": {},
            "stt": {},
            "tts": {},
            "llm": {},
            "total": {}
        }
        
        try:
            process = psutil.Process()
            gateway_memory = process.memory_info().rss / (1024 * 1024)  # MB
            
            # STT memory
            stt_memory = {"total_memory_mb": 0, "model_memory_mb": 0}
            if self.stt_service:
                stt_memory = self.stt_service.get_memory_usage()
            
            # TTS memory (aggregate all backends)
            tts_total_memory = 0
            tts_model_memory = 0
            tts_backends = {}
            if self.tts_service and self.tts_service.manager:
                for backend_name, backend in self.tts_service.manager.backends.items():
                    if hasattr(backend, 'get_memory_usage'):
                        backend_memory = backend.get_memory_usage()
                        tts_backends[backend_name] = backend_memory
                        tts_total_memory += backend_memory.get("total_memory_mb", 0)
                        tts_model_memory += backend_memory.get("model_memory_mb", 0)
            
            # LLM memory (if model loaded)
            llm_memory = {"total_memory_mb": 0, "model_memory_mb": 0}
            if self.llm_manager and self.llm_manager.is_model_loaded():
                # LLM memory is tracked separately via OpenAI-compatible server
                # For now, estimate based on gateway memory increase
                llm_memory = {
                    "total_memory_mb": 0,  # Tracked separately
                    "model_memory_mb": 0,  # Tracked separately
                    "note": "LLM memory tracked via OpenAI-compatible server process"
                }
            
            # GPU memory if available
            gpu_memory = {}
            try:
                import torch
                if torch.cuda.is_available():
                    gpu_allocated = torch.cuda.memory_allocated() / (1024 * 1024)  # MB
                    gpu_reserved = torch.cuda.memory_reserved() / (1024 * 1024)  # MB
                    gpu_memory = {
                        "allocated_mb": round(gpu_allocated, 2),
                        "reserved_mb": round(gpu_reserved, 2),
                        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
                    }
            except ImportError:
                pass
            
            memory_info.update({
                "gateway": {
                    "total_memory_mb": round(gateway_memory, 2)
                },
                "stt": stt_memory,
                "tts": {
                    "total_memory_mb": round(tts_total_memory, 2),
                    "model_memory_mb": round(tts_model_memory, 2),
                    "backends": tts_backends
                },
                "llm": llm_memory,
                "total": {
                    "total_memory_mb": round(gateway_memory, 2),
                    "model_memory_mb": round(stt_memory.get("model_memory_mb", 0) + tts_model_memory, 2),
                    "gpu": gpu_memory
                }
            })
        except Exception as e:
            logger.error(f"Error getting service memory usage: {e}")
            memory_info["error"] = str(e)
        
        return memory_info

    def enable_stt(self):
        """Enable STT service on demand (already initialized natively)."""
        if not self.stt_service:
            from .stt.service import STTService
            self.stt_service = STTService()
            logger.info("STT Service enabled (native faster-whisper)")

    # Interface for ChatManager to call LLM
    async def generate_response(self, messages, settings=None, **kwargs):
        """Call LLM Service."""
        async with httpx.AsyncClient() as client:
            payload = {
                "messages": messages,
                **kwargs
            }
            if settings:
                payload.update(settings)
                
            response = await client.post(f"{self.llm_service_url}/v1/chat/completions", json=payload, timeout=120.0)
            if response.status_code != 200:
                raise RuntimeError(f"LLM Service Error: {response.text}")
                
            data = response.json()
            return {
                "response": data["choices"][0]["message"]["content"],
                "tool_calls": data["choices"][0]["message"].get("tool_calls")
            }

service_manager = ServiceManager()
