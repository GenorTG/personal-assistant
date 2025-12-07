"""
Modular API routes for the gateway service.

This package splits the monolithic routes.py into domain-specific modules:
- health: Health check endpoint
- system: System info, status, debug endpoints
- chat: Chat endpoint and regeneration
- conversations: Conversation CRUD operations
- tts: Text-to-speech routes
- stt: Speech-to-text routes  
- models: Model management (load, info, config, delete)
- downloads: Model download, search, discovery
- settings: AI settings, system prompts
- memory: Vector memory and context settings
- tools: Tool management
- files: File upload/download
- proxy: OpenAI-compatible proxy endpoints
"""
from fastapi import APIRouter

from .health import router as health_router
from .system import router as system_router
from .chat import router as chat_router
from .conversations import router as conversations_router
from .tts import router as tts_router
from .stt import router as stt_router
from .models import router as models_router
from .downloads import router as downloads_router
from .settings import router as settings_router
from .memory import router as memory_router
from .tools import router as tools_router
from .files import router as files_router
from .proxy import router as proxy_router

# Create a combined router that includes all sub-routers
router = APIRouter()

# Include all sub-routers
router.include_router(health_router)
router.include_router(system_router)
router.include_router(chat_router)
router.include_router(conversations_router)
router.include_router(tts_router)
router.include_router(stt_router)
router.include_router(models_router)
router.include_router(downloads_router)
router.include_router(settings_router)
router.include_router(memory_router)
router.include_router(tools_router)
router.include_router(files_router)
router.include_router(proxy_router)

__all__ = [
    "router",
    "health_router",
    "system_router", 
    "chat_router",
    "conversations_router",
    "tts_router",
    "stt_router",
    "models_router",
    "downloads_router",
    "settings_router",
    "memory_router",
    "tools_router",
    "files_router",
    "proxy_router",
]
