"""Piper TTS backend implementation."""
import logging
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from .base import TTSBackend, TTSBackendStatus

logger = logging.getLogger(__name__)


class PiperBackend(TTSBackend):
    """Piper TTS backend - Client for external service."""
    
    def __init__(self):
        super().__init__("piper")
        self.service_url = "http://localhost:8004"
        self._voice: Optional[str] = None
        self._options = {
            "speed": 1.0
        }
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def is_service_running(self) -> bool:
        """Check if service is running via health check."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.service_url}/health")
                return response.status_code == 200
        except Exception:
            return False
    
    async def initialize(self) -> bool:
        """Initialize connection to Piper service."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        # Check if service is running
        if not await self.is_service_running():
            self.error_message = "Piper service not running (Port 8004). Start the Piper service first."
            self.status = TTSBackendStatus.ERROR
            return False
        
        # Create HTTP client
        try:
            self._http_client = httpx.AsyncClient(
                base_url=self.service_url,
                timeout=60.0
            )
            self.status = TTSBackendStatus.READY
            self.error_message = None
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Piper HTTP client: {e}")
            self.error_message = f"Failed to initialize: {e}"
            self.status = TTSBackendStatus.ERROR
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Piper TTS via HTTP API."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Piper TTS backend not ready: {self._error_message}")
        
        if not self._http_client:
            raise RuntimeError("Piper HTTP client not initialized")
        
        self._is_generating = True
        
        try:
            # Use voice from parameter or stored voice
            selected_voice = voice or self._voice
            
            # Prepare request payload
            # Piper uses "input" field, not "text"
            payload = {
                "input": text
            }
            if selected_voice:
                payload["voice"] = selected_voice
            
            # Make HTTP request to Piper service
            # Piper uses /v1/audio/speech endpoint
            response = await self._http_client.post(
                "/v1/audio/speech",
                json=payload,
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise RuntimeError(f"Piper TTS API error: {response.status_code} - {error_text}")
            
            # Return audio data
            return response.content
        except httpx.TimeoutException as e:
            logger.error(f"Piper TTS API request timed out: {e}")
            raise RuntimeError(f"Piper TTS service request timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Piper TTS API connection failed: {e}")
            raise RuntimeError(f"Failed to connect to Piper TTS service at {self.service_url}: {str(e)}")
        except httpx.RequestError as e:
            logger.error(f"Piper TTS API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Piper TTS service: {str(e)}")
        except Exception as e:
            logger.error(f"Piper TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Piper voices from the service API (synchronous wrapper)."""
        try:
            import requests
            # Piper uses /v1/audio/voices endpoint
            response = requests.get(f"{self.service_url}/v1/audio/voices", timeout=5)
            if response.status_code == 200:
                data = response.json()
                voice_list = data.get("voices", [])
                voices = []
                for voice_id in voice_list:
                    voices.append({
                        "id": voice_id,
                        "name": voice_id.replace('_', ' ').title() if isinstance(voice_id, str) else str(voice_id),
                        "language": "en"  # Piper typically supports English
                    })
                return voices
        except Exception as e:
            logger.debug(f"Failed to fetch voices from API: {e}, using fallback")
        
        # Fallback: return empty list or default voice
        return [{"id": "default", "name": "Default Voice", "language": "en"}]
    
    def get_options(self) -> Dict[str, Any]:
        """Get Piper TTS options."""
        return {
            "voice": self._voice,
            "speed": {
                "value": self._options.get("speed", 1.0),
                "min": 0.5,
                "max": 2.0,
                "step": 0.1,
                "description": "Speech speed multiplier"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Piper TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            
            # Handle structured options (with value key) or direct values
            if "speed" in options:
                value = options["speed"]
                if isinstance(value, dict) and "value" in value:
                    value = value["value"]
                if isinstance(value, (int, float)):
                    self._options["speed"] = max(0.5, min(2.0, float(value)))
            
            return True
        except Exception as e:
            logger.error("Error setting Piper options: %s", str(e))
            return False

