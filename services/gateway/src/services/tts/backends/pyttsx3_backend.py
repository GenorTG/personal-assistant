"""pyttsx3 TTS backend implementation (system TTS fallback)."""
import logging
import asyncio
from typing import Optional, List, Dict, Any
from .base import TTSBackend, TTSBackendStatus

logger = logging.getLogger(__name__)


class Pyttsx3Backend(TTSBackend):
    """pyttsx3 backend - uses system TTS, no download needed."""
    
    def __init__(self):
        super().__init__("pyttsx3")
        self.model = None
        self._voice: Optional[str] = None
        self._options = {
            "rate": 150,
            "volume": 0.9
        }
    
    async def initialize(self) -> bool:
        """Initialize pyttsx3 engine."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        try:
            loop = asyncio.get_event_loop()
            
            def _init():
                try:
                    import pyttsx3
                    self.model = pyttsx3.init()
                    
                    # Set voice if specified
                    if self._voice:
                        voices = self.model.getProperty('voices')
                        for voice in voices:
                            if self._voice.lower() in voice.name.lower():
                                self.model.setProperty('voice', voice.id)
                                break
                    
                    # Set options
                    self.model.setProperty('rate', self._options.get("rate", 150))
                    self.model.setProperty('volume', self._options.get("volume", 0.9))
                    
                    return True
                except ImportError:
                    logger.warning("pyttsx3 not installed. Install with: pip install pyttsx3")
                    return False
                except Exception as e:
                    logger.error(f"Failed to initialize pyttsx3: {e}")
                    return False
            
            success = await loop.run_in_executor(None, _init)
            
            if success:
                self.status = TTSBackendStatus.READY
                logger.info("pyttsx3 backend initialized successfully")
                return True
            else:
                self.status = TTSBackendStatus.ERROR
                self._error_message = "pyttsx3 initialization failed"
                return False
        except Exception as e:
            self.status = TTSBackendStatus.ERROR
            self._error_message = str(e)
            logger.error(f"pyttsx3 initialization error: {e}")
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using pyttsx3."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"pyttsx3 backend not ready: {self._error_message}")
        
        self._is_generating = True
        
        try:
            loop = asyncio.get_event_loop()
            import tempfile
            import os
            
            def _synthesize():
                try:
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                        output_path = tmp.name
                    
                    # Set voice if provided
                    if voice or self._voice:
                        target_voice = voice or self._voice
                        voices = self.model.getProperty('voices')
                        for v in voices:
                            if target_voice.lower() in v.name.lower():
                                self.model.setProperty('voice', v.id)
                                break
                    
                    self.model.save_to_file(text, output_path)
                    self.model.runAndWait()
                    
                    with open(output_path, 'rb') as f:
                        audio_data = f.read()
                    
                    os.unlink(output_path)
                    return audio_data
                except Exception as e:
                    logger.error(f"pyttsx3 synthesis failed: {e}")
                    raise
            
            audio_data = await loop.run_in_executor(None, _synthesize)
            return audio_data
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available pyttsx3 voices."""
        if not self.is_ready:
            return []
        
        try:
            voices = self.model.getProperty('voices')
            return [{"id": v.id, "name": v.name} for v in voices]
        except Exception as e:
            logger.error(f"Error getting pyttsx3 voices: {e}")
            return []
    
    def get_options(self) -> Dict[str, Any]:
        """Get pyttsx3 options."""
        rate = self.model.getProperty('rate') if self.model else self._options.get("rate", 150)
        volume = self.model.getProperty('volume') if self.model else self._options.get("volume", 0.9)
        
        return {
            "voice": self._voice,
            "rate": {
                "value": rate,
                "min": 50,
                "max": 300,
                "step": 10,
                "description": "Speech rate in words per minute"
            },
            "volume": {
                "value": volume,
                "min": 0.0,
                "max": 1.0,
                "step": 0.1,
                "description": "Volume level"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set pyttsx3 options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
                if self.model:
                    voices = self.model.getProperty('voices')
                    for voice in voices:
                        if self._voice.lower() in voice.name.lower():
                            self.model.setProperty('voice', voice.id)
                            break
            
            # Handle structured options (with value key) or direct values
            if "rate" in options:
                rate = options["rate"]
                # If it's a dict with 'value' key, extract the value
                if isinstance(rate, dict) and "value" in rate:
                    rate = rate["value"]
                rate = int(rate)
                
                if self.model:
                    self.model.setProperty('rate', max(50, min(300, rate)))
                    self._options["rate"] = self.model.getProperty('rate')
                else:
                    # Store for when model is initialized
                    self._options["rate"] = max(50, min(300, rate))
            
            if "volume" in options:
                volume = options["volume"]
                # If it's a dict with 'value' key, extract the value
                if isinstance(volume, dict) and "value" in volume:
                    volume = volume["value"]
                volume = float(volume)
                
                if self.model:
                    self.model.setProperty('volume', max(0.0, min(1.0, volume)))
                    self._options["volume"] = self.model.getProperty('volume')
                else:
                    # Store for when model is initialized
                    self._options["volume"] = max(0.0, min(1.0, volume))
            
            return True
        except Exception as e:
            logger.error(f"Error setting pyttsx3 options: {e}")
            return False


