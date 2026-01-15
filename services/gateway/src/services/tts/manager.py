"""TTS backend manager."""
from typing import Optional, Dict, Any, List
import logging
import asyncio
from .backends import (
    TTSBackend,
    ChatterboxBackend,
    KokoroBackend,
    CoquiBackend,
    Pyttsx3Backend,
    PiperBackend
)
from .backends.openai_api import OpenAITTSBackend
from ...config.settings import settings

logger = logging.getLogger(__name__)


class TTSManager:
    """Manages multiple TTS backends and switching between them."""
    
    def __init__(self):
        self.backends: Dict[str, TTSBackend] = {}
        self.current_backend_name: Optional[str] = None
        self._initialize_backends()
    
    def _initialize_backends(self):
        """Initialize all available TTS backends."""
        # Register available backends (with error handling for each)
        self.backends = {}
        
        # Try to initialize each backend, skip if it fails
        backend_classes = {
            "chatterbox": ChatterboxBackend,
            "kokoro": KokoroBackend,
            "piper": PiperBackend,
            "coqui": CoquiBackend,
            "pyttsx3": Pyttsx3Backend,
            "openai": OpenAITTSBackend
        }
        
        for name, backend_class in backend_classes.items():
            try:
                self.backends[name] = backend_class()
                logger.debug(f"TTS backend '{name}' initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize TTS backend '{name}': {e}")
                # Continue with other backends even if one fails
        
        # Set default backend from settings
        default_provider = settings.tts_provider.lower()
        if default_provider in self.backends:
            self.current_backend_name = default_provider
        else:
            # Fallback to first available
            self.current_backend_name = list(self.backends.keys())[0]
            logger.warning(
                f"TTS provider '{settings.tts_provider}' not found. "
                f"Using '{self.current_backend_name}' instead."
            )
    
    @property
    def current_backend(self) -> Optional[TTSBackend]:
        """Get the current active backend."""
        if self.current_backend_name:
            return self.backends.get(self.current_backend_name)
        return None
    
    async def switch_backend(self, backend_name: str) -> bool:
        """Switch to a different TTS backend.
        
        Args:
            backend_name: Name of the backend to switch to
        
        Returns:
            True if switch was successful (even if initialization failed), False if backend not found
        """
        if backend_name not in self.backends:
            logger.error(f"TTS backend '{backend_name}' not found")
            return False
        
        # Always switch the backend, even if initialization fails
        # This allows users to see error messages and try to fix issues
        backend = self.backends[backend_name]
        
        # Try to initialize the new backend
        success = await backend.initialize()
        
        # Switch regardless of initialization result
        self.current_backend_name = backend_name
        
        if success:
            logger.info(f"Switched to TTS backend: {backend_name} (initialized successfully)")
        else:
            logger.warning(
                f"Switched to TTS backend: {backend_name} "
                f"(initialization failed: {backend.error_message})"
            )
        
        return True
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        backend_name: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using the current or specified backend.
        
        Args:
            text: Text to synthesize
            voice: Optional voice identifier
            backend_name: Optional backend name (uses current if not specified)
            **kwargs: Backend-specific options
        
        Returns:
            Audio data as bytes
        """
        backend = None
        if backend_name and backend_name in self.backends:
            backend = self.backends[backend_name]
        else:
            backend = self.current_backend
        
        if not backend:
            raise RuntimeError("No TTS backend available")
        
        # Ensure backend is initialized
        if not backend.is_ready:
            await backend.initialize()
        
        if not backend.is_ready:
            raise RuntimeError(
                f"TTS backend '{backend.name}' not ready: {backend.error_message}"
            )
        
        return await backend.synthesize(text, voice=voice, **kwargs)
    
    def get_available_backends(self) -> List[Dict[str, Any]]:
        """Get list of all available backends with their status.
        
        Returns:
            List of backend information dictionaries
        """
        backends_info = []
        for name, backend in self.backends.items():
            try:
                info = backend.get_status()
                info["is_current"] = (name == self.current_backend_name)
                backends_info.append(info)
            except Exception as e:
                logger.error(f"Error getting status for backend '{name}': {e}", exc_info=True)
                # Return error status for this backend
                backends_info.append({
                    "name": name,
                    "status": "error",
                    "is_ready": False,
                    "is_current": (name == self.current_backend_name),
                    "error_message": str(e)
                })
        return backends_info
    
    def get_backend(self, backend_name: Optional[str] = None) -> Optional[TTSBackend]:
        """Get a backend instance.
        
        Args:
            backend_name: Backend name (uses current if not specified)
        
        Returns:
            Backend instance or None if not found
        """
        if backend_name:
            return self.backends.get(backend_name)
        return self.current_backend
    
    async def get_backend_info(self, backend_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get detailed information about a backend.
        
        Args:
            backend_name: Backend name (uses current if not specified)
        
        Returns:
            Backend information dictionary or None if not found
        """
        backend = self.get_backend(backend_name)
        if not backend:
            return None
        
        try:
            info = backend.get_status()
            
            # Handle async get_available_voices
            try:
                if asyncio.iscoroutinefunction(backend.get_available_voices):
                    info["voices"] = await backend.get_available_voices()
                else:
                    info["voices"] = backend.get_available_voices()
            except Exception as e:
                logger.warning(f"Error getting voices for backend '{backend_name}': {e}")
                info["voices"] = []
            
            try:
                info["options"] = backend.get_options()
            except Exception as e:
                logger.warning(f"Error getting options for backend '{backend_name}': {e}")
                info["options"] = {}
            
            return info
        except Exception as e:
            logger.error(f"Error getting backend info for '{backend_name}': {e}", exc_info=True)
            return {
                "name": backend_name or "unknown",
                "status": "error",
                "is_ready": False,
                "error_message": str(e),
                "voices": [],
                "options": {}
            }
    
    async def initialize_backend(self, backend_name: str) -> bool:
        """Initialize a specific backend.
        
        Args:
            backend_name: Name of the backend to initialize
        
        Returns:
            True if initialization successful
        """
        if backend_name not in self.backends:
            return False
        
        backend = self.backends[backend_name]
        return await backend.initialize()
    
    def set_backend_options(
        self,
        backend_name: Optional[str],
        options: Dict[str, Any]
    ) -> bool:
        """Set options for a backend.
        
        Args:
            backend_name: Backend name (uses current if not specified)
            options: Dictionary of options to set
        
        Returns:
            True if options were set successfully
        """
        if backend_name:
            backend = self.backends.get(backend_name)
        else:
            backend = self.current_backend
        
        if not backend:
            return False
        
        return backend.set_options(options)


