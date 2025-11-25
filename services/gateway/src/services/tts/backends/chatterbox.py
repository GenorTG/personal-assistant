"""Chatterbox TTS backend implementation."""
import logging
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from .base import TTSBackend, TTSBackendStatus
from ...external.chatterbox_service import chatterbox_service

logger = logging.getLogger(__name__)


class ChatterboxBackend(TTSBackend):
    """Chatterbox TTS backend - higher quality, more resource intensive."""
    
    def __init__(self):
        super().__init__("chatterbox")
        self.api_url = "http://localhost:4123/v1"
        self._voice: Optional[str] = None
        self._options = {
            "speed": 1.0,  # Note: API ignores this but we keep it for UI consistency
            "cfg_weight": 0.5,  # CFG weight (pace control) - range 0.0-2.0
            "temperature": 0.8,  # Sampling temperature
            "exaggeration": 0.5,  # Emotion intensity
            "seed": None  # Random seed for reproducible generation (None = random)
        }
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def initialize(self) -> bool:
        """Initialize Chatterbox TTS API connection."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        try:
            # Check if service is installed
            if not chatterbox_service._check_installation():
                self._error_message = (
                    "Chatterbox TTS API not installed. "
                    "Install it via the backend API or run: python install_dependencies.py"
                )
                self.status = TTSBackendStatus.ERROR
                return False
            
            # Check if service is running by verifying port is accessible
            # This prevents starting duplicate instances
            if not chatterbox_service.is_running:
                logger.info("Chatterbox TTS API not running, starting server...")
                start_result = await chatterbox_service.start()
                if start_result["status"] != "success":
                    self._error_message = start_result.get("message", "Failed to start Chatterbox TTS API")
                    self.status = TTSBackendStatus.ERROR
                    return False
            else:
                logger.info("Chatterbox TTS API is already running (detected on port)")
            
            # Create HTTP client
            # API routes are at root level (no /v1 prefix in the actual routes)
            # But we keep api_url for consistency with service manager
            base_url = "http://localhost:4123"
            self._http_client = httpx.AsyncClient(
                base_url=base_url,
                timeout=30.0
            )
            
            # Test connection with retries (service may be downloading models)
            max_retries = 10
            retry_delay = 3
            health_check_passed = False
            
            for attempt in range(max_retries):
                try:
                    response = await self._http_client.get("/health", timeout=10.0)
                    if response.status_code == 200:
                        health_check_passed = True
                        break
                    else:
                        logger.info("Health check returned %d, retrying... (attempt %d/%d)", response.status_code, attempt + 1, max_retries)
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.info("Health check failed (attempt %d/%d): %s. Waiting %ds before retry...", attempt + 1, max_retries, str(e), retry_delay)
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 1.5, 10)  # Exponential backoff, max 10s
                    else:
                        logger.warning("Chatterbox TTS API health check failed after %d attempts: %s", max_retries, str(e))
                        # Don't fail initialization - the service might still be loading models
                        # We'll mark as ready but health check will happen on first use
                        health_check_passed = False
            
            if not health_check_passed:
                logger.warning("Chatterbox TTS API health check did not pass, but service is running. Model may still be loading.")
                # Don't fail - the service is running, just not fully initialized yet
            
            self.status = TTSBackendStatus.READY
            logger.info("Chatterbox TTS backend initialized successfully")
            return True
        except Exception as e:
            self.status = TTSBackendStatus.ERROR
            self._error_message = f"Failed to initialize Chatterbox TTS: {str(e)}"
            logger.error(f"Chatterbox TTS initialization error: {e}")
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Chatterbox TTS API."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Chatterbox TTS backend not ready: {self._error_message}")
        
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")
        
        self._is_generating = True
        
        try:
            # Check if service is running (by port check) before starting
            # This prevents duplicate instances
            if not chatterbox_service.is_running:
                logger.info("Chatterbox service not running, starting...")
                await chatterbox_service.start()
            
            # Prepare request payload
            # Ensure text is properly handled (httpx will handle UTF-8 encoding)
            # Remove any problematic characters that might cause encoding issues
            text_clean = text.encode('utf-8', errors='replace').decode('utf-8')
            
            payload = {
                "input": text_clean,
                "voice": voice or self._voice or "default"
            }
            
            # Add Chatterbox-specific options (only if not default values)
            if "exaggeration" in self._options and self._options["exaggeration"] != 0.5:
                payload["exaggeration"] = self._options["exaggeration"]
            if "cfg_weight" in self._options and self._options["cfg_weight"] != 0.5:
                payload["cfg_weight"] = self._options["cfg_weight"]
            if "temperature" in self._options and self._options["temperature"] != 0.8:
                payload["temperature"] = self._options["temperature"]
            # Add seed if provided
            if "seed" in self._options and self._options["seed"] is not None:
                payload["seed"] = self._options["seed"]
            
            # Make API request
            # Use /v1/audio/speech (alias) or /audio/speech (primary) - both work via route aliases
            response = await self._http_client.post(
                "/v1/audio/speech",
                json=payload,
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise RuntimeError(f"Chatterbox TTS API error: {response.status_code} - {error_text}")
            
            # Return audio data
            return response.content
        except httpx.RequestError as e:
            logger.error(f"Chatterbox TTS API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Chatterbox TTS API: {str(e)}")
        except Exception as e:
            logger.error(f"Chatterbox TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Chatterbox voices from API."""
        # Always try to fetch from API if service is running
        if self.is_ready and self._http_client and chatterbox_service.is_running:
            try:
                voices = await self._fetch_voices_from_api()
                if voices:
                    return voices
            except Exception as e:
                logger.warning(f"Failed to fetch voices from API: {e}")
        
        # Return only default voice if API fetch fails
        return [
            {"id": "default", "name": "Default Voice", "gender": "neutral", "language": "en"},
        ]
    
    async def _fetch_voices_from_api(self) -> List[Dict[str, Any]]:
        """Fetch voices from Chatterbox TTS API (async helper)."""
        try:
            if not self._http_client:
                # Try to initialize if not ready
                if not self.is_ready:
                    await self.initialize()
                if not self._http_client:
                    return []
            
            # Use /voices endpoint (not /v1/voices - that's for speech generation)
            response = await self._http_client.get("/voices", timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                voices_list = data.get("voices", [])
                voices = []
                for voice in voices_list:
                    # Map Chatterbox voice format to our format
                    voice_id = voice.get("name", voice.get("id", "unknown"))
                    voices.append({
                        "id": voice_id,
                        "name": voice.get("name", voice_id),
                        "gender": voice.get("gender", "unknown"),
                        "language": voice.get("language", "en")
                    })
                logger.info(f"Fetched {len(voices)} voices from Chatterbox API")
                return voices
        except Exception as e:
            logger.warning(f"Failed to fetch voices from API: {e}")
        return []
    
    def get_options(self) -> Dict[str, Any]:
        """Get Chatterbox TTS options."""
        return {
            "voice": self._voice,
            "speed": {
                "value": self._options.get("speed", 1.0),
                "min": 0.5,
                "max": 2.0,
                "step": 0.1,
                "description": "Speech speed (note: API currently ignores this)"
            },
            "cfg_weight": {
                "value": self._options.get("cfg_weight", 0.5),
                "min": 0.0,
                "max": 2.0,
                "step": 0.05,
                "description": "CFG weight (pace control)"
            },
            "temperature": {
                "value": self._options.get("temperature", 0.8),
                "min": 0.05,
                "max": 5.0,
                "step": 0.05,
                "description": "Sampling temperature (higher = more random)"
            },
            "exaggeration": {
                "value": self._options.get("exaggeration", 0.5),
                "min": 0.25,
                "max": 2.0,
                "step": 0.05,
                "description": "Emotion intensity"
            },
            "seed": {
                "value": self._options.get("seed"),
                "description": "Random seed for reproducible generation (None = random, integer = fixed seed)"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Chatterbox TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            
            # Handle structured options (with value key) or direct values
            for key in ["speed", "cfg_weight", "temperature", "exaggeration", "seed"]:
                if key in options:
                    value = options[key]
                    # If it's a dict with 'value' key, extract the value
                    if isinstance(value, dict) and "value" in value:
                        value = value["value"]
                    
                    if key == "speed" and isinstance(value, (int, float)):
                        self._options["speed"] = max(0.5, min(2.0, float(value)))
                    elif key == "cfg_weight" and isinstance(value, (int, float)):
                        self._options["cfg_weight"] = max(0.0, min(2.0, float(value)))
                    elif key == "temperature" and isinstance(value, (int, float)):
                        self._options["temperature"] = max(0.05, min(5.0, float(value)))
                    elif key == "exaggeration" and isinstance(value, (int, float)):
                        self._options["exaggeration"] = max(0.25, min(2.0, float(value)))
                    elif key == "seed":
                        # Seed can be None (random) or an integer
                        if value is None:
                            self._options["seed"] = None
                        elif isinstance(value, int):
                            self._options["seed"] = value
                        elif isinstance(value, str) and value.lower() in ("none", "null", ""):
                            self._options["seed"] = None
                        elif isinstance(value, (int, float)):
                            self._options["seed"] = int(value)
            
            return True
        except Exception as e:
            logger.error("Error setting Chatterbox options: %s", e)
            return False


