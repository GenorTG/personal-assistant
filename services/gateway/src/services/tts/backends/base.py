"""Base TTS backend interface."""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from enum import Enum


class TTSBackendStatus(Enum):
    """TTS backend status."""
    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    GENERATING = "generating"


class TTSBackend(ABC):
    """Base class for TTS backends."""
    
    def __init__(self, name: str):
        self.name = name
        self.status = TTSBackendStatus.NOT_INITIALIZED
        self._is_generating = False
        self._error_message: Optional[str] = None
    
    @property
    def is_ready(self) -> bool:
        """Check if backend is ready to use."""
        return self.status == TTSBackendStatus.READY
    
    @property
    def is_generating(self) -> bool:
        """Check if backend is currently generating audio."""
        return self._is_generating
    
    @property
    def error_message(self) -> Optional[str]:
        """Get error message if backend is in error state."""
        return self._error_message
    
    @error_message.setter
    def error_message(self, value: Optional[str]):
        """Set error message."""
        self._error_message = value
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the TTS backend.
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text to speech audio.
        
        Args:
            text: Text to synthesize
            voice: Optional voice identifier
            **kwargs: Backend-specific options
        
        Returns:
            Audio data as bytes (WAV format)
        """
        pass
    
    @abstractmethod
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices.
        
        Returns:
            List of voice dictionaries with 'id' and 'name' keys
        """
        pass
    
    @abstractmethod
    def get_options(self) -> Dict[str, Any]:
        """Get backend-specific configuration options.
        
        Returns:
            Dictionary of option names and their current values
        """
        pass
    
    @abstractmethod
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set backend-specific configuration options.
        
        Args:
            options: Dictionary of option names and values to set
        
        Returns:
            True if options were set successfully
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get current backend status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "name": self.name,
            "status": self.status.value,
            "is_ready": self.is_ready,
            "is_generating": self.is_generating,
            "error_message": self.error_message
        }


