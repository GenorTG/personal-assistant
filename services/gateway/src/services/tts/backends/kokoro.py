
import io
import subprocess
import sys
import platform
import logging
import asyncio
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import TTSBackend, TTSBackendStatus

logger = logging.getLogger(__name__)


class KokoroBackend(TTSBackend):
    """Kokoro TTS backend - Client for external service."""
    
    def __init__(self):
        super().__init__("kokoro")
        self.service_url = "http://localhost:8880"
        self._process = None
        self._service_dir = Path(__file__).parent.parent.parent.parent.parent.parent / "services" / "tts-kokoro"
        self._voice: Optional[str] = None
        self._options = {
            "speed": 1.0,
            "lang": "en-us"
        }
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def start_service(self) -> bool:
        """Start the external Kokoro service."""
        if await self.is_service_running():
            return True
            
        try:
            logger.info("Starting Kokoro service...")
            venv_python = self._service_dir / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
            if not venv_python.exists():
                venv_python = self._service_dir / ".venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "python.exe"
            
            if not venv_python.exists():
                logger.error(f"Kokoro venv python not found at {venv_python}")
                return False

            # Start process detached
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NEW_CONSOLE
                self._process = subprocess.Popen(
                    [str(venv_python), "main.py"],
                    cwd=str(self._service_dir),
                    creationflags=creationflags
                )
            else:
                self._process = subprocess.Popen(
                    [str(venv_python), "main.py"],
                    cwd=str(self._service_dir),
                    start_new_session=True
                )
            
            # Wait for startup
            for _ in range(10):
                await asyncio.sleep(1)
                if await self.is_service_running():
                    logger.info("Kokoro service started successfully")
                    return True
            
            logger.error("Kokoro service failed to start (timeout)")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start Kokoro service: {e}")
            return False

    async def stop_service(self) -> bool:
        """Stop the external Kokoro service."""
        # This is tricky because we might not have the handle if it was started externally
        # For now, we can't easily stop it unless we track the PID or use a kill command
        # But we can at least try if we have the process handle
        if self._process:
            self._process.terminate()
            self._process = None
            return True
        return False

    async def is_service_running(self) -> bool:
        """Check if service is running via health check."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.service_url}/health")
                return response.status_code == 200
        except Exception as e:
            # logger.debug(f"Kokoro health check failed: {e}")
            return False

    async def initialize(self) -> bool:
        """Initialize connection to Kokoro service."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        # Check if service is running
        if not await self.is_service_running():
            self.error_message = "Kokoro service not running (Port 8880). Start the Kokoro service first."
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
            logger.error(f"Failed to initialize Kokoro HTTP client: {e}")
            self.error_message = f"Failed to initialize: {e}"
        self.status = TTSBackendStatus.ERROR
        return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Kokoro TTS via HTTP API."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Kokoro TTS backend not ready: {self._error_message}")
        
        # Ensure HTTP client is initialized
        if not self._http_client:
            # Try to reinitialize
            try:
                self._http_client = httpx.AsyncClient(
                    base_url=self.service_url,
                    timeout=60.0
                )
            except Exception as e:
                raise RuntimeError(f"Kokoro HTTP client not initialized: {e}")
        
        self._is_generating = True
        
        try:
            # Use voice from parameter or stored voice
            # ALWAYS resolve to actual voice ID from available voices
            selected_voice = voice or self._voice or "af_bella"
            
            # Resolve display name to actual voice ID
            try:
                # Get available voices
                available_voices = self.get_available_voices()
                    
                # First try exact match on ID
                voice_found = False
                for v in available_voices:
                    if v.get("id") == selected_voice:
                        voice_found = True
                        selected_voice = v.get("id")
                        break
                
                # If not found, try to match by display name
                if not voice_found:
                    # Convert display name format to ID format
                    # "Af Bella" -> "af_bella"
                    normalized = selected_voice.lower().replace(" ", "_")
                    for v in available_voices:
                        voice_id = v.get("id", "")
                        voice_name = v.get("name", "")
                        if (voice_id == normalized or 
                            voice_id == selected_voice or
                            voice_name.lower() == selected_voice.lower()):
                            selected_voice = voice_id
                            voice_found = True
                            break
                
                # If still not found, use default
                if not voice_found:
                    logger.warning(f"Voice '{selected_voice}' not found, using af_bella")
                    selected_voice = "af_bella"
            except Exception as e:
                logger.warning(f"Failed to resolve Kokoro voice: {e}, using af_bella")
                selected_voice = "af_bella"
            
            # Prepare request payload
            payload = {
                "text": text,
                "voice": selected_voice,
                "speed": self._options.get("speed", 1.0),
                "lang": self._options.get("lang", "en-us")
            }
            
            logger.debug(f"Kokoro TTS request: POST {self.service_url}/synthesize with voice={selected_voice}")
                                    
            # Make HTTP request to Kokoro service
            response = await self._http_client.post(
                "/synthesize",
                json=payload,
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Kokoro TTS API error: {response.status_code} - {error_text}")
                raise RuntimeError(f"Kokoro TTS API error: {response.status_code} - {error_text}")
            
            # Return audio data
            return response.content
        except httpx.TimeoutException as e:
            logger.error(f"Kokoro TTS API request timed out: {e}")
            raise RuntimeError(f"Kokoro TTS service request timed out: {str(e)}")
        except httpx.ConnectError as e:
            logger.error(f"Kokoro TTS API connection failed: {e}")
            raise RuntimeError(f"Failed to connect to Kokoro TTS service at {self.service_url}: {str(e)}")
        except httpx.RequestError as e:
            logger.error(f"Kokoro TTS API request failed: {e}")
            raise RuntimeError(f"Failed to connect to Kokoro TTS service: {str(e)}")
        except Exception as e:
            logger.error(f"Kokoro TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Kokoro voices from the service API (synchronous wrapper)."""
        # This is a synchronous method, but we need to fetch from HTTP API
        # Use a simple synchronous HTTP request
        try:
            import requests
            response = requests.get(f"{self.service_url}/voices", timeout=5)
            if response.status_code == 200:
                data = response.json()
                voice_list = data.get("voices", [])
                voices = []
                for voice_id in voice_list:
                    voices.append({
                        "id": voice_id,
                        "name": voice_id.replace('_', ' ').title(),
                        "language": self._parse_voice_language(voice_id),
                        "accent": self._parse_voice_accent(voice_id)
                    })
                return voices
        except Exception as e:
            logger.debug(f"Failed to fetch voices from API: {e}, using fallback list")
        
        # Fallback: return hardcoded list of known voices
        real_voices = [
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
            "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
            "am_onyx", "am_puck", "am_santa",
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            "ef_dora", "em_alex", "em_santa",
            "ff_siwis",
            "hf_alpha", "hf_beta",
            "hm_omega", "hm_psi",
            "if_sara", "im_nicola",
            "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
            "jm_kumo",
            "pf_dora", "pm_alex", "pm_santa",
            "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi"
        ]
        
        voices = []
        for voice_id in real_voices:
            voices.append({
                "id": voice_id,
                "name": voice_id.replace('_', ' ').title(),
                "language": self._parse_voice_language(voice_id),
                "accent": self._parse_voice_accent(voice_id)
            })
        return voices
    
    def _parse_voice_language(self, voice_id: str) -> str:
        """Parse language from voice ID."""
        # Voice IDs follow pattern: {language_prefix}_{name}
        # Language prefixes: af, am, bf, bm, ef, em, ff, hf, hm, if, im, jf, jm, pf, pm, zf
        # af/am = English (American), bf/bm = English (British), ef/em = English (other),
        # ff = French, hf/hm = Hindi, if/im = Italian, jf/jm = Japanese, pf/pm = Portuguese, zf = Chinese
        prefix = voice_id.split('_')[0] if '_' in voice_id else voice_id
        
        lang_map = {
            'af': 'en', 'am': 'en',  # American English
            'bf': 'en', 'bm': 'en',  # British English
            'ef': 'en', 'em': 'en',  # English (other)
            'ff': 'fr',  # French
            'hf': 'hi', 'hm': 'hi',  # Hindi
            'if': 'it', 'im': 'it',  # Italian
            'jf': 'ja', 'jm': 'ja',  # Japanese
            'pf': 'pt', 'pm': 'pt',  # Portuguese
            'zf': 'zh',  # Chinese
        }
        return lang_map.get(prefix, 'en')
    
    def _parse_voice_accent(self, voice_id: str) -> str:
        """Parse accent/gender from voice ID."""
        # f = female, m = male
        prefix = voice_id.split('_')[0] if '_' in voice_id else voice_id
        
        if len(prefix) >= 2:
            gender = 'female' if prefix[1] == 'f' else 'male'
            region = {
                'af': 'us', 'am': 'us',  # American
                'bf': 'gb', 'bm': 'gb',  # British
                'ef': 'en', 'em': 'en',  # English
                'ff': 'fr',  # French
                'hf': 'in', 'hm': 'in',  # Hindi
                'if': 'it', 'im': 'it',  # Italian
                'jf': 'jp', 'jm': 'jp',  # Japanese
                'pf': 'pt', 'pm': 'pt',  # Portuguese
                'zf': 'cn',  # Chinese
            }.get(prefix, 'neutral')
            return f"{gender}_{region}"
        return "neutral"
    
    def get_options(self) -> Dict[str, Any]:
        """Get Kokoro TTS options."""
        return {
            "voice": self._voice,
            "speed": {
                "value": self._options.get("speed", 1.0),
                "min": 0.5,
                "max": 2.0,
                "step": 0.1,
                "description": "Speech speed multiplier"
            },
            "lang": {
                "value": self._options.get("lang", "en-us"),
                "description": "Language code (e.g., en-us, en-gb)"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Kokoro TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            
            # Handle structured options (with value key) or direct values
            for key in ["speed", "lang"]:
                if key in options:
                    value = options[key]
                    # If it's a dict with 'value' key, extract the value
                    if isinstance(value, dict) and "value" in value:
                        value = value["value"]
                    
                    if key == "speed" and isinstance(value, (int, float)):
                        self._options["speed"] = max(0.5, min(2.0, float(value)))
                    elif key == "lang" and isinstance(value, str):
                        self._options["lang"] = value
            
            return True
        except Exception as e:
            logger.error("Error setting Kokoro options: %s", str(e))
            return False


