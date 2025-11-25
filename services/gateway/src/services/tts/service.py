"""Text-to-Speech service with multiple backend support."""
from typing import Optional
from pathlib import Path
import logging
import asyncio
import io
from .manager import TTSManager
from ...config.settings import settings

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-Speech service with multiple backend support."""
    
    def __init__(self):
        self.manager = TTSManager()
        self.voice = settings.tts_voice
        self._initialized = False
    
    async def _initialize_model(self):
        """Initialize TTS backend (lazy initialization)."""
        if self._initialized:
            return
        
        try:
            # Initialize the current backend
            if self.manager.current_backend:
                await self.manager.initialize_backend(self.manager.current_backend_name)
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize TTS backend: {e}")
            raise
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        output_format: str = "wav",
        backend_name: Optional[str] = None
    ) -> bytes:
        """
        Synthesize text to speech audio.
        
        Args:
            text: Text to synthesize
            voice: Optional voice identifier
            output_format: Output format ("wav" or "mp3")
            backend_name: Optional backend name (uses current if not specified)
        
        Returns:
            Audio data as bytes
        """
        if not self._initialized:
            await self._initialize_model()
        
        # Use voice from settings if not provided
        effective_voice = voice or self.voice
        
        return await self.manager.synthesize(
                    text=text,
            voice=effective_voice,
            backend_name=backend_name,
            output_format=output_format
        )
    
    async def switch_backend(self, backend_name: str) -> bool:
        """Switch to a different TTS backend.
        
        Args:
            backend_name: Name of the backend to switch to
        
        Returns:
            True if switch was successful
        """
        return await self.manager.switch_backend(backend_name)
    
    def get_available_backends(self):
        """Get list of all available backends with their status."""
        return self.manager.get_available_backends()
    
    async def get_backend_info(self, backend_name: Optional[str] = None):
        """Get detailed information about a backend."""
        return await self.manager.get_backend_info(backend_name)
    
    def set_backend_options(
        self,
        backend_name: Optional[str],
        options: dict
    ) -> bool:
        """Set options for a backend."""
        return self.manager.set_backend_options(backend_name, options)
    
    async def get_available_voices(self, backend_name: Optional[str] = None) -> list:
        """Get list of available voices for a backend."""
        backend = None
        if backend_name and backend_name in self.manager.backends:
            backend = self.manager.backends[backend_name]
        else:
            backend = self.manager.current_backend
        
        if not backend:
            return []
        
        # Handle async backends (like Chatterbox)
        if hasattr(backend, 'get_available_voices') and callable(backend.get_available_voices):
            import inspect
            if inspect.iscoroutinefunction(backend.get_available_voices):
                return await backend.get_available_voices()
            else:
                return backend.get_available_voices()
        
        return []
    
    def get_current_backend_name(self) -> Optional[str]:
        """Get the name of the current backend."""
        return self.manager.current_backend_name
