"""Kokoro TTS backend implementation."""
import logging
import asyncio
import io
import subprocess
import sys
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any
import numpy as np
import soundfile as sf
import psutil
import shutil
import urllib.request
from .base import TTSBackend, TTSBackendStatus
from ....config.settings import settings

logger = logging.getLogger(__name__)


class KokoroBackend(TTSBackend):
    """Kokoro TTS backend - Native implementation using kokoro-onnx library."""

    # kokoro_onnx expects a voices JSON + an ONNX model file (not voices-v1.0.bin)
    MODEL_FILENAME = "kokoro-v0_19.onnx"
    VOICES_FILENAME = "voices.json"
    MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
    VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json"
    
    def __init__(self):
        super().__init__("kokoro")
        self._process = None
        # Repo-bundled Kokoro assets live at: <project root>/services/tts-kokoro/
        self._service_dir = settings.base_dir / "services" / "tts-kokoro"
        self._voice: Optional[str] = None
        self._options = {
            "speed": 1.0,
            "lang": "en-us"
        }
        self._kokoro: Optional[Any] = None
        self._model_path: Optional[Path] = None
        self._voices_path: Optional[Path] = None
        self._download_status: Dict[str, Any] = {
            "status": "not_found",
            "model_id": "kokoro",
            "downloaded": False,
        }
    
    def _find_model_files(self) -> tuple[Optional[Path], Optional[Path]]:
        """Find Kokoro model and voices files."""
        # Preferred: gateway-managed voice model directory
        preferred_dir = settings.voice_models_dir / "kokoro"
        model_path = preferred_dir / self.MODEL_FILENAME
        voices_path = preferred_dir / self.VOICES_FILENAME
        if model_path.exists() and voices_path.exists():
            return model_path, voices_path

        # Fallback: repo-bundled service directory (this repo ships these files)
        model_path = self._service_dir / self.MODEL_FILENAME
        voices_path = self._service_dir / self.VOICES_FILENAME
        if model_path.exists() and voices_path.exists():
            return model_path, voices_path
        
        # Check models directory
        if settings.models_dir.exists():
            for model_file in settings.models_dir.rglob(self.MODEL_FILENAME):
                voices_file = model_file.parent / self.VOICES_FILENAME
                if voices_file.exists():
                    return model_file, voices_file
        
        return None, None

    def _ensure_seed_assets(self) -> bool:
        """
        Ensure Kokoro assets exist in the gateway-managed voice model directory.
        If repo-bundled assets are missing, auto-download from the official kokoro-onnx release.
        """
        try:
            target_dir = settings.voice_models_dir / "kokoro"
            target_dir.mkdir(parents=True, exist_ok=True)

            src_model = self._service_dir / self.MODEL_FILENAME
            src_voices = self._service_dir / self.VOICES_FILENAME

            dst_model = target_dir / self.MODEL_FILENAME
            dst_voices = target_dir / self.VOICES_FILENAME

            # Prefer copying bundled assets if present
            if src_model.exists() and not dst_model.exists():
                shutil.copy2(src_model, dst_model)
            if src_voices.exists() and not dst_voices.exists():
                shutil.copy2(src_voices, dst_voices)

            # Otherwise, download missing files
            if not dst_model.exists():
                logger.info("Downloading Kokoro model to %s", dst_model)
                urllib.request.urlretrieve(self.MODEL_URL, dst_model)
            if not dst_voices.exists():
                logger.info("Downloading Kokoro voices to %s", dst_voices)
                urllib.request.urlretrieve(self.VOICES_URL, dst_voices)

            return dst_model.exists() and dst_voices.exists()
        except Exception as e:
            logger.warning(f"Could not seed Kokoro assets: {e}")
            return False

    def get_download_status(self) -> Dict[str, Any]:
        """Get current Kokoro model download status."""
        # Refresh based on file presence
        model_path, voices_path = self._find_model_files()
        if model_path and voices_path and model_path.exists() and voices_path.exists():
            self._download_status = {
                "status": "ready",
                "model_id": "kokoro",
                "downloaded": True,
                "files": {"model": str(model_path), "voices": str(voices_path)},
            }
        return self._download_status

    async def download_model(self, force: bool = False) -> Dict[str, Any]:
        """Download Kokoro model assets (onnx + voices.json) into voice_models_dir."""
        self._download_status = {
            "status": "downloading",
            "model_id": "kokoro",
            "downloaded": False,
            "message": "Downloading Kokoro model assets...",
        }

        target_dir = settings.voice_models_dir / "kokoro"
        target_dir.mkdir(parents=True, exist_ok=True)
        dst_model = target_dir / self.MODEL_FILENAME
        dst_voices = target_dir / self.VOICES_FILENAME

        loop = asyncio.get_event_loop()

        def _download():
            if force:
                if dst_model.exists():
                    dst_model.unlink()
                if dst_voices.exists():
                    dst_voices.unlink()
            # Use shared helper to copy bundled assets or fetch from URL
            self._ensure_seed_assets()

        try:
            await loop.run_in_executor(None, _download)
            return self.get_download_status()
        except Exception as e:
            self._download_status = {
                "status": "error",
                "model_id": "kokoro",
                "downloaded": False,
                "error": str(e),
            }
            return self._download_status

    async def is_service_running(self) -> bool:
        """Check if Kokoro is initialized (for compatibility)."""
        return self._kokoro is not None

    async def initialize(self) -> bool:
        """Initialize Kokoro TTS backend."""
        if self.status == TTSBackendStatus.READY:
            return True
        
        self.status = TTSBackendStatus.INITIALIZING
        
        try:
            from kokoro_onnx import Kokoro
            
            # Find model files
            model_path, voices_path = self._find_model_files()
            
            if not model_path or not voices_path:
                # Try to seed from repo-bundled assets into voice_models_dir
                self._ensure_seed_assets()
                model_path, voices_path = self._find_model_files()
                if not model_path or not voices_path:
                    self.error_message = (
                        "Kokoro model files not found. Please ensure kokoro-v1.0.onnx and voices-v1.0.bin are available."
                    )
                    self.status = TTSBackendStatus.ERROR
                    return False
        
            self._model_path = model_path
            self._voices_path = voices_path
            
            # Initialize Kokoro
            # Run in executor since it might be CPU-intensive
            loop = asyncio.get_event_loop()
            
            def _init():
                return Kokoro(str(model_path), str(voices_path))
            
            self._kokoro = await loop.run_in_executor(None, _init)
            
            self.status = TTSBackendStatus.READY
            self.error_message = None
            logger.info(f"Kokoro TTS initialized with model: {model_path}")
            return True
        except ImportError as e:
            logger.error(f"kokoro-onnx not installed: {e}")
            self.error_message = "kokoro-onnx library not installed"
            self.status = TTSBackendStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Kokoro: {e}")
            self.error_message = f"Failed to initialize: {e}"
            self.status = TTSBackendStatus.ERROR
            return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Kokoro TTS natively."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Kokoro TTS backend not ready: {self._error_message}")
        
        if not self._kokoro:
            raise RuntimeError("Kokoro not initialized")
        
        # Use voice from parameter or stored voice or default
        selected_voice = voice or self._voice or "af_bella"

        # Resolve display name to actual voice ID
        try:
            available_voices = self.get_available_voices()
            voice_found = False
            for v in available_voices:
                if v.get("id") == selected_voice:
                    voice_found = True
                    selected_voice = v.get("id")
                    break
            
            # If not found, try to match by display name
            if not voice_found:
                normalized = selected_voice.lower().replace(" ", "_")
                for v in available_voices:
                    voice_id = v.get("id", "")
                    voice_name = v.get("name", "")
                    if (
                        voice_id == normalized
                        or voice_id == selected_voice
                        or voice_name.lower() == selected_voice.lower()
                    ):
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
            
        self._is_generating = True
        
        try:
            # Use Kokoro library directly
            loop = asyncio.get_event_loop()
            
            def _synthesize():
                samples, sample_rate = self._kokoro.create(
                    text,
                    voice=selected_voice,
                    speed=self._options.get("speed", 1.0),
                    lang=self._options.get("lang", "en-us")
                )
                
                # Convert to WAV bytes
                buffer = io.BytesIO()
                sf.write(buffer, samples, sample_rate, format='WAV')
                buffer.seek(0)
                return buffer.read()
            
            audio_data = await loop.run_in_executor(None, _synthesize)
            return audio_data
        except Exception as e:
            logger.error(f"Kokoro TTS synthesis failed: {e}")
            raise
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Kokoro voices."""
        # Hardcoded list of voices supported by Kokoro v1.0
        voices = [
            {"id": "af_bella", "name": "Af Bella", "language": "en-us"},
            {"id": "af_sarah", "name": "Af Sarah", "language": "en-us"},
            {"id": "am_adam", "name": "Am Adam", "language": "en-us"},
            {"id": "am_michael", "name": "Am Michael", "language": "en-us"},
            {"id": "bf_emma", "name": "Bf Emma", "language": "en-us"},
            {"id": "bf_isabella", "name": "Bf Isabella", "language": "en-us"},
            {"id": "bm_george", "name": "Bm George", "language": "en-us"},
            {"id": "bm_lewis", "name": "Bm Lewis", "language": "en-us"},
            {"id": "af_nicole", "name": "Af Nicole", "language": "en-us"},
            {"id": "af_sky", "name": "Af Sky", "language": "en-us"}
        ]
        return voices
    
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
                "description": "Language code"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Kokoro TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            
            if "speed" in options:
                value = options["speed"]
                if isinstance(value, dict) and "value" in value:
                    value = value["value"]
                if isinstance(value, (int, float)):
                    self._options["speed"] = max(0.5, min(2.0, float(value)))
            
            if "lang" in options:
                value = options["lang"]
                if isinstance(value, dict) and "value" in value:
                    value = value["value"]
                self._options["lang"] = str(value)
            
            return True
        except Exception as e:
            logger.error("Error setting Kokoro options: %s", str(e))
            return False

    def unload_model(self) -> bool:
        """Unload Kokoro model from memory."""
        try:
            self._kokoro = None
            self._model_path = None
            self._voices_path = None
            self.status = TTSBackendStatus.NOT_INITIALIZED
            self._initialized = False
            logger.info("Kokoro model unloaded")
            return True
        except Exception as e:
            logger.error(f"Error unloading Kokoro model: {e}")
            return False
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get current Kokoro model status."""
        status = {
            "loaded": self.status == TTSBackendStatus.READY and self._kokoro is not None,
            "model_path": str(self._model_path) if self._model_path else None,
            "voices_path": str(self._voices_path) if self._voices_path else None,
            "voice": self._voice,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status)
        }
        
        total_size_mb = 0
        if self._model_path and self._model_path.exists():
            stat = self._model_path.stat()
            total_size_mb += stat.st_size / (1024 * 1024)
        if self._voices_path and self._voices_path.exists():
            stat = self._voices_path.stat()
            total_size_mb += stat.st_size / (1024 * 1024)
        
        status["size_mb"] = round(total_size_mb, 2)
        status["memory_mb"] = round(total_size_mb * 2, 2)  # Approximate memory usage (2x file size)
        
        return status
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage for Kokoro backend."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            # Estimate model memory (rough estimate based on file sizes)
            model_memory_mb = 0
            if self._model_path and self._model_path.exists() and self._voices_path and self._voices_path.exists():
                model_stat = self._model_path.stat()
                voices_stat = self._voices_path.stat()
                total_size = (model_stat.st_size + voices_stat.st_size) / (1024 * 1024)
                model_memory_mb = total_size * 2  # Approximate (2x file size in memory)
            
            return {
                "total_memory_mb": round(memory_mb, 2),
                "model_memory_mb": round(model_memory_mb, 2),
                "base_memory_mb": round(memory_mb - model_memory_mb, 2) if model_memory_mb > 0 else round(memory_mb, 2)
            }
        except Exception as e:
            logger.error(f"Error getting Kokoro memory usage: {e}")
            return {
                "total_memory_mb": 0,
                "model_memory_mb": 0,
                "base_memory_mb": 0,
                "error": str(e)
            }