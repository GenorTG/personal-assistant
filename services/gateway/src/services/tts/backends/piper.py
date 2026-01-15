"""Piper TTS backend implementation."""
import logging
import asyncio
import io
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import soundfile as sf
import psutil
import shutil
import urllib.request
from .base import TTSBackend, TTSBackendStatus
from ....config.settings import settings

logger = logging.getLogger(__name__)


class PiperBackend(TTSBackend):
    """Piper TTS backend - Native implementation using piper-tts library."""
    
    def __init__(self):
        super().__init__("piper")
        self._voice: Optional[str] = None
        self._options = {
            "speed": 1.0
        }
        self._model_path: Optional[Path] = None
        self._piper_voice = None
        self._download_status: Dict[str, Dict[str, Any]] = {}

    def _model_search_dirs(self) -> List[Path]:
        """Directories to search for Piper .onnx voice models (highest priority first)."""
        return [
            settings.voice_models_dir / "piper",
            settings.models_dir,  # legacy location (used by this repo today)
        ]

    def _seed_default_voice_if_available(self) -> bool:
        """
        Seed a default Piper voice into voice_models_dir/piper from the repo's legacy location
        (this repo already ships en_US-amy-medium.* under services/data/models/).
        """
        try:
            target_dir = settings.voice_models_dir / "piper"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Default voice shipped in this repo
            src_onnx = settings.models_dir / "en_US-amy-medium.onnx"
            src_json = settings.models_dir / "en_US-amy-medium.onnx.json"
            if not src_onnx.exists():
                return False

            dst_onnx = target_dir / src_onnx.name
            if not dst_onnx.exists():
                shutil.copy2(src_onnx, dst_onnx)
            if src_json.exists():
                dst_json = target_dir / src_json.name
                if not dst_json.exists():
                    shutil.copy2(src_json, dst_json)
            return True
        except Exception as e:
            logger.warning(f"Could not seed Piper default voice: {e}")
            return False

    def get_download_status(self, voice_id: str) -> Dict[str, Any]:
        """Get download status for a Piper voice id."""
        status = self._download_status.get(voice_id)
        if status:
            return status

        target_dir = settings.voice_models_dir / "piper"
        onnx_path = target_dir / f"{voice_id}.onnx"
        json_path = target_dir / f"{voice_id}.onnx.json"
        return {
            "status": "ready" if onnx_path.exists() else "not_found",
            "model_id": voice_id,
            "downloaded": onnx_path.exists(),
            "files": {
                "onnx": str(onnx_path) if onnx_path.exists() else "",
                "config": str(json_path) if json_path.exists() else "",
            },
        }

    async def download_voice(
        self,
        voice_id: str,
        onnx_url: Optional[str] = None,
        config_url: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Download a Piper voice model into `services/data/voice_models/piper/`.

        - If `voice_id` is already bundled (e.g. en_US-amy-medium), we can seed it without URLs.
        - For other voices, the caller should provide URLs for the ONNX + (optional) JSON config.
        """
        target_dir = settings.voice_models_dir / "piper"
        target_dir.mkdir(parents=True, exist_ok=True)
        onnx_path = target_dir / f"{voice_id}.onnx"
        json_path = target_dir / f"{voice_id}.onnx.json"

        # If it's already present and not forcing, short-circuit
        if onnx_path.exists() and not force:
            self._download_status[voice_id] = {
                "status": "ready",
                "model_id": voice_id,
                "downloaded": True,
                "files": {
                    "onnx": str(onnx_path),
                    "config": str(json_path) if json_path.exists() else "",
                },
            }
            return self._download_status[voice_id]

        # Try to seed bundled default voice if it matches
        if voice_id == "en_US-amy-medium":
            self._seed_default_voice_if_available()
            if onnx_path.exists() and not force:
                self._download_status[voice_id] = {
                    "status": "ready",
                    "model_id": voice_id,
                    "downloaded": True,
                    "files": {"onnx": str(onnx_path), "config": str(json_path) if json_path.exists() else ""},
                }
                return self._download_status[voice_id]

        if not onnx_url:
            self._download_status[voice_id] = {
                "status": "error",
                "model_id": voice_id,
                "downloaded": False,
                "error": "onnx_url is required to download this Piper voice",
            }
            return self._download_status[voice_id]

        self._download_status[voice_id] = {
            "status": "downloading",
            "model_id": voice_id,
            "downloaded": False,
            "message": "Downloading Piper voice assets...",
        }

        loop = asyncio.get_event_loop()

        def _download():
            # Download ONNX
            if force and onnx_path.exists():
                onnx_path.unlink()
            urllib.request.urlretrieve(onnx_url, onnx_path)

            # Download config if provided
            if config_url:
                if force and json_path.exists():
                    json_path.unlink()
                urllib.request.urlretrieve(config_url, json_path)

        try:
            await loop.run_in_executor(None, _download)
            self._download_status[voice_id] = {
                "status": "ready",
                "model_id": voice_id,
                "downloaded": True,
                "files": {
                    "onnx": str(onnx_path),
                    "config": str(json_path) if json_path.exists() else "",
                },
            }
            return self._download_status[voice_id]
        except Exception as e:
            self._download_status[voice_id] = {
                "status": "error",
                "model_id": voice_id,
                "downloaded": False,
                "error": str(e),
            }
            return self._download_status[voice_id]
    
    def _find_model(self) -> Optional[Path]:
        """Find a Piper model file in the models directory."""
        for base in self._model_search_dirs():
            if not base.exists():
                continue
            for model_file in base.rglob("*.onnx"):
                if model_file.is_file():
                    logger.info(f"Found Piper model: {model_file}")
                    return model_file
        return None
    
    def _find_model_by_name(self, voice_name: str) -> Optional[Path]:
        """Find a model by voice name."""
        for base in self._model_search_dirs():
            if not base.exists():
                continue
            # Try exact match first
            for model_file in base.rglob("*.onnx"):
                if model_file.stem == voice_name or model_file.name == voice_name:
                    return model_file
            # Try partial match
            for model_file in base.rglob("*.onnx"):
                if voice_name.lower() in model_file.stem.lower() or voice_name.lower() in model_file.name.lower():
                    return model_file
        return None
    
    async def is_service_running(self) -> bool:
        """Piper is an in-process backend; "running" means initialized."""
        return self._piper_voice is not None
    
    async def initialize(self) -> bool:
        """Initialize Piper TTS backend."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        try:
            # Find model
            self._model_path = self._find_model()
            
            if not self._model_path or not self._model_path.exists():
                # Try to seed the repo-bundled default voice into voice_models_dir/piper
                self._seed_default_voice_if_available()
                self._model_path = self._find_model()

                # Try to find default model
                default_model = (settings.voice_models_dir / "piper" / "en_US-amy-medium.onnx")
                if default_model.exists():
                    self._model_path = default_model
                else:
                    self.error_message = f"Piper model not found. Please place a .onnx model file in {settings.models_dir}"
                    self.status = TTSBackendStatus.ERROR
                    return False

            # Load Piper model in-process (avoid calling a system `piper` binary which may be unrelated)
            model_path = self._model_path
            config_path = None
            if model_path:
                candidate = model_path.with_name(model_path.name + ".json")
                if candidate.exists():
                    config_path = candidate
                else:
                    candidate2 = model_path.with_suffix(model_path.suffix + ".json")
                    if candidate2.exists():
                        config_path = candidate2

            loop = asyncio.get_event_loop()

            def _load():
                from piper.voice import PiperVoice
                # NOTE: use_cuda=False by default; users can later add config/env for CUDA.
                return PiperVoice.load(model_path, config_path=config_path, use_cuda=False)

            self._piper_voice = await loop.run_in_executor(None, _load)

            self.status = TTSBackendStatus.READY
            self.error_message = None
            logger.info(f"Piper TTS initialized with model: {self._model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Piper: {e}")
            self.error_message = f"Failed to initialize: {e}"
            self.status = TTSBackendStatus.ERROR
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Piper TTS natively."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Piper TTS backend not ready: {self._error_message}")
        
        # Use voice from parameter or stored voice
        selected_voice = voice or self._voice
        
        # If voice is specified, try to find that specific model
        model_path = self._model_path
        if selected_voice and selected_voice != "default":
            voice_model = self._find_model_by_name(selected_voice)
            if voice_model:
                model_path = voice_model
            else:
                logger.warning(f"Voice '{selected_voice}' not found, using default model")
        
        if not model_path or not model_path.exists():
            raise RuntimeError(f"Piper model not found: {model_path}")
        
        self._is_generating = True
        
        try:
            loop = asyncio.get_event_loop()

            def _synthesize() -> bytes:
                from piper.config import SynthesisConfig
                import numpy as np

                if self._piper_voice is None:
                    raise RuntimeError("Piper voice not loaded")

                speed = float(self._options.get("speed", 1.0) or 1.0)
                # Piper uses length_scale (bigger -> slower). Map speed roughly inversely.
                length_scale = 1.0 / max(0.1, speed)
                syn = SynthesisConfig(length_scale=length_scale)

                chunks = list(self._piper_voice.synthesize(text, syn_config=syn))
                if not chunks:
                    raise RuntimeError("Piper returned no audio chunks")

                sample_rate = chunks[0].sample_rate
                audio = np.concatenate([c.audio_float_array for c in chunks], axis=0)

                buf = io.BytesIO()
                sf.write(buf, audio, sample_rate, format="WAV")
                return buf.getvalue()

            return await loop.run_in_executor(None, _synthesize)
        except Exception as e:
            logger.error(f"Piper TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Piper voices (models)."""
        voices: List[Dict[str, Any]] = []
        
        # If we have a model path set, use that
        if self._model_path and self._model_path.exists():
            voice_name = self._model_path.stem
            voices.append({
                "id": voice_name,
                "name": voice_name.replace('_', ' ').title(),
                "language": "en"
            })
        
        # Also scan models dir for other .onnx files
        if settings.models_dir.exists():
            for model_file in settings.models_dir.rglob("*.onnx"):
                if model_file.is_file():
                    voice_name = model_file.stem
                    # Check if already added
                    if not any(v.get("id") == voice_name for v in voices):
                        voices.append({
                            "id": voice_name,
                            "name": voice_name.replace('_', ' ').title(),
                            "language": "en"
                        })
        
        # If no voices found, return default
        if not voices:
            voices = [{"id": "default", "name": "Default Voice", "language": "en"}]
        
        return voices
    
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

    async def switch_model(self, model_id: str) -> bool:
        """Switch to a different Piper model (voice)."""
        try:
            # Unload current model
            self.unload_model()
            
            # Find the new model
            new_model_path = self._find_model_by_name(model_id)
            if not new_model_path or not new_model_path.exists():
                # Try to find in catalog
                from ...services.model_catalog import get_piper_voices
                voices = get_piper_voices()
                voice_info = next((v for v in voices if v.get("id") == model_id or v.get("name") == model_id), None)
                
                if voice_info:
                    # Model needs to be downloaded
                    logger.info(f"Model {model_id} not found locally, needs download")
                    return False
                else:
                    logger.error(f"Model {model_id} not found")
                    return False
            
            # Set new model path
            self._model_path = new_model_path
            self._voice = model_id
            
            # Reinitialize with new model
            success = await self.initialize()
            if success:
                logger.info(f"Switched to Piper model: {model_id}")
            return success
        except Exception as e:
            logger.error(f"Error switching Piper model: {e}")
            return False
    
    def unload_model(self) -> bool:
        """Unload Piper model from memory (clear state)."""
        try:
            self._piper_voice = None
            self._model_path = None
            self.status = TTSBackendStatus.NOT_INITIALIZED
            self._initialized = False
            logger.info("Piper model unloaded")
            return True
        except Exception as e:
            logger.error(f"Error unloading Piper model: {e}")
            return False
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get current Piper model status."""
        status = {
            "loaded": self.status == TTSBackendStatus.READY,
            "model_path": str(self._model_path) if self._model_path else None,
            "voice": self._voice,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status)
        }
        
        if self._model_path and self._model_path.exists():
            stat = self._model_path.stat()
            status["size_mb"] = round(stat.st_size / (1024 * 1024), 2)
            status["memory_mb"] = round(stat.st_size / (1024 * 1024) * 1.5, 2)  # Approximate memory usage
        else:
            status["size_mb"] = 0
            status["memory_mb"] = 0
        
        return status
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage for Piper backend."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            # Estimate model memory (rough estimate based on file size)
            model_memory_mb = 0
            if self._model_path and self._model_path.exists():
                stat = self._model_path.stat()
                model_memory_mb = (stat.st_size / (1024 * 1024)) * 1.5  # Approximate
            
            return {
                "total_memory_mb": round(memory_mb, 2),
                "model_memory_mb": round(model_memory_mb, 2),
                "base_memory_mb": round(memory_mb - model_memory_mb, 2) if model_memory_mb > 0 else round(memory_mb, 2)
            }
        except Exception as e:
            logger.error(f"Error getting Piper memory usage: {e}")
            return {
                "total_memory_mb": 0,
                "model_memory_mb": 0,
                "base_memory_mb": 0,
                "error": str(e)
            }