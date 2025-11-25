"""Coqui TTS backend implementation."""
import logging
import asyncio
from typing import Optional, List, Dict, Any
from .base import TTSBackend, TTSBackendStatus

logger = logging.getLogger(__name__)


class CoquiBackend(TTSBackend):
    """Coqui TTS backend implementation."""
    
    def __init__(self):
        super().__init__("coqui")
        self.tts_instance = None
        self._voice: Optional[str] = None
        self._model_name = "tts_models/en/ljspeech/tacotron2-DDC"
        self._options = {
            "model_name": "tts_models/en/ljspeech/tacotron2-DDC",
            "seed": None  # Random seed for reproducible generation (None = random)
        }
    
    async def initialize(self) -> bool:
        """Initialize Coqui TTS model."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        try:
            loop = asyncio.get_event_loop()
            
            def _init():
                try:
                    from TTS.api import TTS
                    model_name = self._options.get("model_name", self._model_name)
                    
                    # Try to initialize with the model
                    # TTS will automatically download models if needed
                    try:
                        self.tts_instance = TTS(
                            model_name=model_name,
                            progress_bar=False,
                            gpu=False  # Start with CPU, can be changed later
                        )
                        return True
                    except Exception as model_error:
                        # If model download/loading fails, try a simpler model
                        if "model" in str(model_error).lower() or "not found" in str(model_error).lower():
                            logger.warning(f"Failed to load model {model_name}, trying default model...")
                            try:
                                # Try with a simpler, more common model
                                self.tts_instance = TTS(
                                    model_name="tts_models/en/ljspeech/tacotron2-DDC",
                                    progress_bar=False,
                                    gpu=False
                                )
                                # Update the stored model name
                                self._model_name = "tts_models/en/ljspeech/tacotron2-DDC"
                                self._options["model_name"] = self._model_name
                                return True
                            except Exception as fallback_error:
                                logger.error(f"Failed to initialize Coqui TTS with fallback model: {fallback_error}")
                                self._error_message = f"Failed to initialize Coqui TTS: Model download/loading failed. Error: {str(fallback_error)}. Try running 'tts --list_models' to see available models."
                                return False
                        else:
                            raise  # Re-raise if it's not a model-related error
                except ImportError:
                    logger.warning("TTS (coqui-tts) not installed. Install with: pip install TTS")
                    self._error_message = "TTS (coqui-tts) package not installed. Install with: pip install TTS"
                    return False
                except Exception as e:
                    logger.error(f"Failed to initialize Coqui TTS: {e}")
                    self._error_message = f"Failed to initialize Coqui TTS: {str(e)}"
                    return False
            
            success = await loop.run_in_executor(None, _init)
            
            if success:
                self.status = TTSBackendStatus.READY
                logger.info("Coqui TTS backend initialized successfully")
                return True
            else:
                self.status = TTSBackendStatus.ERROR
                # Error message should already be set in _init(), but set a default if not
                if not self._error_message:
                    self._error_message = "Coqui TTS model initialization failed"
                return False
        except Exception as e:
            self.status = TTSBackendStatus.ERROR
            self._error_message = str(e)
            logger.error(f"Coqui TTS initialization error: {e}")
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Coqui TTS."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Coqui TTS backend not ready: {self._error_message}")
        
        self._is_generating = True
        
        try:
            loop = asyncio.get_event_loop()
            import tempfile
            import os
            
            def _synthesize():
                try:
                    # Set random seed if provided (for reproducible generation)
                    seed = self._options.get("seed")
                    if seed is not None:
                        import torch
                        import numpy as np
                        torch.manual_seed(seed)
                        np.random.seed(seed)
                        if torch.cuda.is_available():
                            torch.cuda.manual_seed_all(seed)
                    
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                        output_path = tmp.name
                    
                    self.tts_instance.tts_to_file(
                        text=text,
                        file_path=output_path,
                        speaker=voice or self._voice
                    )
                    
                    with open(output_path, 'rb') as f:
                        audio_data = f.read()
                    
                    os.unlink(output_path)
                    return audio_data
                except Exception as e:
                    logger.error(f"Coqui TTS synthesis failed: {e}")
                    raise
            
            audio_data = await loop.run_in_executor(None, _synthesize)
            return audio_data
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Coqui TTS voices."""
        if not self.is_ready:
            # Return default voices even if not initialized (for UI)
            return [
                {"id": "default", "name": "Default Voice", "model": self._model_name},
            ]
        
        try:
            voices = []
            if hasattr(self.tts_instance, 'speakers') and self.tts_instance.speakers:
                for speaker in self.tts_instance.speakers:
                    voices.append({
                        "id": speaker,
                        "name": speaker.replace('_', ' ').title(),
                        "model": self._model_name
                    })
            else:
                voices = [{"id": "default", "name": "Default Voice", "model": self._model_name}]
            return voices
        except Exception as e:
            logger.error(f"Error getting Coqui voices: {e}")
            return [{"id": "default", "name": "Default Voice", "model": self._model_name}]
    
    def get_available_models(self) -> List[str]:
        """Get available Coqui TTS models."""
        return [
            "tts_models/en/ljspeech/tacotron2-DDC",
            "tts_models/en/ljspeech/glow-tts",
            "tts_models/en/ljspeech/speedy-speech",
            "tts_models/en/vctk/vits",
            "tts_models/en/ek1/tacotron2",
            "tts_models/multilingual/multi-dataset/your_tts",
            "tts_models/en/ljspeech/tacotron2-DCA",
            "tts_models/en/ljspeech/neural_hmm",
        ]
    
    def get_options(self) -> Dict[str, Any]:
        """Get Coqui TTS options."""
        return {
            "voice": self._voice,
            "model_name": {
                "value": self._options.get("model_name", self._model_name),
                "options": self.get_available_models(),
                "description": "TTS model to use (changing requires reinitialization)"
            },
            "gpu": {
                "value": self._options.get("gpu", False),
                "type": "boolean",
                "description": "Use GPU acceleration if available"
            },
            "seed": {
                "value": self._options.get("seed"),
                "description": "Random seed for reproducible generation (None = random, integer = fixed seed)"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Coqui TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            
            # Handle structured options (with value key) or direct values
            if "model_name" in options:
                model_name = options["model_name"]
                # If it's a dict with 'value' key, extract the value
                if isinstance(model_name, dict) and "value" in model_name:
                    model_name = model_name["value"]
                
                if model_name != self._options.get("model_name"):
                    # Model changed, need to reinitialize
                    self._options["model_name"] = model_name
                    self._model_name = model_name
                    self.status = TTSBackendStatus.NOT_INITIALIZED
                    self.tts_instance = None
            
            if "gpu" in options:
                gpu_value = options["gpu"]
                # If it's a dict with 'value' key, extract the value
                if isinstance(gpu_value, dict) and "value" in gpu_value:
                    gpu_value = gpu_value["value"]
                self._options["gpu"] = bool(gpu_value)
            
            if "seed" in options:
                seed_value = options["seed"]
                # If it's a dict with 'value' key, extract the value
                if isinstance(seed_value, dict) and "value" in seed_value:
                    seed_value = seed_value["value"]
                
                # Seed can be None (random) or an integer
                if seed_value is None:
                    self._options["seed"] = None
                elif isinstance(seed_value, int):
                    self._options["seed"] = seed_value
                elif isinstance(seed_value, str) and seed_value.lower() in ("none", "null", ""):
                    self._options["seed"] = None
                elif isinstance(seed_value, (int, float)):
                    self._options["seed"] = int(seed_value)
            
            return True
        except Exception as e:
            logger.error("Error setting Coqui options: %s", str(e))
            return False


