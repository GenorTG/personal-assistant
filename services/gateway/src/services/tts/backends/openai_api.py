"""OpenAI-compatible TTS backend."""
from typing import Optional, List, Dict, Any
import httpx
import logging
from .base import TTSBackend, TTSBackendStatus

logger = logging.getLogger(__name__)


class OpenAITTSBackend(TTSBackend):
    """TTS backend for OpenAI-compatible APIs."""
    
    def __init__(self):
        super().__init__("openai")
        self.api_url: Optional[str] = None
        self.api_key: Optional[str] = None
        self.model = "tts-1"
        self.voice = "alloy"
        self.voices_list = [
            {"id": "alloy", "name": "Alloy"},
            {"id": "echo", "name": "Echo"},
            {"id": "fable", "name": "Fable"},
            {"id": "onyx", "name": "Onyx"},
            {"id": "nova", "name": "Nova"},
            {"id": "shimmer", "name": "Shimmer"}
        ]
    
    async def initialize(self) -> bool:
        """Initialize the OpenAI TTS backend."""
        if not self.api_url or not self.api_key:
            logger.error("OpenAI TTS: API URL and API key must be configured")
            self.status = TTSBackendStatus.ERROR
            self._error_message = "API URL and API key not configured"
            return False
        
        try:
            # Test connection with a minimal request
            self.status = TTSBackendStatus.INITIALIZING
            logger.info(f"OpenAI TTS: Testing connection to {self.api_url}")
            
            # Just mark as ready - we'll test on first synthesis
            self.status = TTSBackendStatus.READY
            self._error_message = None
            logger.info("OpenAI TTS: Backend ready")
            return True
            
        except Exception as e:
            logger.error(f"OpenAI TTS: Initialization failed: {e}")
            self.status = TTSBackendStatus.ERROR
            self._error_message = str(e)
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text to speech using OpenAI API.
        
        Args:
            text: Text to synthesize
            voice: Voice ID (optional, uses default if not specified)
            **kwargs: Additional API parameters
            
        Returns:
            Audio data as bytes (MP3 format from OpenAI)
        """
        if not self.is_ready:
            raise RuntimeError("OpenAI TTS backend not initialized")
        
        voice_id = voice or self.voice
        model = kwargs.get("model", self.model)
        
        try:
            self._is_generating = True
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "input": text,
                        "voice": voice_id,
                        "response_format": "mp3"
                    }
                )
                
                if response.status_code != 200:
                    error_msg = f"OpenAI API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
                
                return response.content
                
        except Exception as e:
            logger.error(f"OpenAI TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices."""
        return self.voices_list
    
    def get_options(self) -> Dict[str, Any]:
        """Get backend configuration options."""
        return {
            "api_url": self.api_url or "",
            "model": self.model,
            "voice": self.voice,
            "has_api_key": bool(self.api_key)
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set backend configuration options."""
        try:
            if "api_url" in options:
                self.api_url = options["api_url"]
            if "api_key" in options:
                self.api_key = options["api_key"]
            if "model" in options:
                self.model = options["model"]
            if "voice" in options:
                self.voice = options["voice"]
            return True
        except Exception as e:
            logger.error(f"Failed to set options: {e}")
            return False
    
    def configure(self, api_url: str, api_key: str):
        """Configure the OpenAI API endpoint.
        
        Args:
            api_url: Full URL to the TTS endpoint (e.g., https://api.openai.com/v1/audio/speech)
            api_key: API key for authentication
        """
        self.api_url = api_url
        self.api_key = api_key
