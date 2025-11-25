"""OpenAI-compatible STT backend."""
from typing import Optional
import httpx
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OpenAISTTBackend:
    """STT backend for OpenAI-compatible APIs (Whisper-compatible)."""
    
    def __init__(self):
        self.name = "openai"
        self.api_url: Optional[str] = None
        self.api_key: Optional[str] = None
        self.model = "whisper-1"
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize the OpenAI STT backend."""
        if not self.api_url or not self.api_key:
            logger.error("OpenAI STT: API URL and API key must be configured")
            return False
        
        try:
            logger.info(f"OpenAI STT: Configured with endpoint {self.api_url}")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"OpenAI STT: Initialization failed: {e}")
            return False
    
    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> tuple[str, Optional[str]]:
        """Transcribe audio using OpenAI API.
        
        Args:
            audio_path: Path to audio file
            language: Optional language code
            
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        if not self._initialized:
            raise RuntimeError("OpenAI STT backend not initialized")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(audio_path, 'rb') as audio_file:
                    files = {
                        'file': (audio_path.name, audio_file, 'audio/wav')
                    }
                    data = {
                        'model': self.model
                    }
                    if language:
                        data['language'] = language
                    
                    response = await client.post(
                        self.api_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}"
                        },
                        files=files,
                        data=data
                    )
                    
                    if response.status_code != 200:
                        error_msg = f"OpenAI API error: {response.status_code} - {response.text}"
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    
                    result = response.json()
                    text = result.get("text", "")
                    detected_lang = result.get("language") or language
                    
                    return text, detected_lang
                    
        except Exception as e:
            logger.error(f"OpenAI STT transcription failed: {e}")
            raise
    
    def configure(self, api_url: str, api_key: str, model: str = "whisper-1"):
        """Configure the OpenAI API endpoint.
        
        Args:
            api_url: Full URL to the transcription endpoint
            api_key: API key for authentication
            model: Model name (default: whisper-1)
        """
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
