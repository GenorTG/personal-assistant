"""
API route handlers.

This is the main entry point for API routes. The actual endpoint implementations
are split into domain-specific modules under the routes/ directory:

- routes/health.py: Health check endpoint
- routes/system.py: System info, status, debug endpoints  
- routes/chat.py: Chat endpoint and regeneration
- routes/conversations.py: Conversation CRUD operations
- routes/tts.py: Text-to-speech routes
- routes/stt.py: Speech-to-text routes
- routes/models.py: Model management (load, info, config, delete)
- routes/downloads.py: Model download, search, discovery
- routes/settings.py: AI settings, system prompts
- routes/memory.py: Vector memory and context settings
- routes/tools.py: Tool management
- routes/files.py: File upload/download
- routes/proxy.py: OpenAI-compatible proxy endpoints

This refactoring reduces this file from ~3900 lines to ~50 lines,
improving maintainability, debugging, and imports.
"""

# Re-export the combined router from the routes package
from .routes import router

# Also export schemas for backwards compatibility
from .schemas import (
    ChatRequest, ChatResponse, ConversationHistory,
    STTResponse, TTSRequest,
    AISettings, AISettingsResponse, ModelInfo, ModelLoadOptions, CharacterCard, UserProfile,
    ModelMetadata, MemoryEstimate, MessageMetadata, ConversationRenameRequest
)

__all__ = [
    "router",
    "ChatRequest", 
    "ChatResponse", 
    "ConversationHistory",
    "STTResponse", 
    "TTSRequest",
    "AISettings", 
    "AISettingsResponse", 
    "ModelInfo", 
    "ModelLoadOptions", 
    "CharacterCard", 
    "UserProfile",
    "ModelMetadata", 
    "MemoryEstimate", 
    "MessageMetadata", 
    "ConversationRenameRequest"
]
