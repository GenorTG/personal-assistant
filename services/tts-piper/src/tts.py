import logging
import subprocess
import wave
import json
import urllib.request
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

from .config import settings

logger = logging.getLogger(__name__)

class PiperTTS:
    """Piper TTS Service."""
    
    def __init__(self):
        self.model_path: Optional[Path] = None
        if settings.tts_model_path:
            self.model_path = Path(settings.tts_model_path)
        else:
            # Auto-detect model in models directory
            self.model_path = self._find_model()
            
    def _find_model(self) -> Optional[Path]:
        """Find a Piper model file in the models directory."""
        if settings.models_dir.exists():
            # Look for .onnx files (Piper models are ONNX format)
            for model_file in settings.models_dir.glob("**/*.onnx"):
                # Check if it's a Piper model (usually has .onnx extension)
                if model_file.is_file():
                    logger.info(f"Found Piper model: {model_file}")
                    return model_file
            # Also check for .onnx files in subdirectories
            for model_file in settings.models_dir.rglob("*.onnx"):
                if model_file.is_file():
                    logger.info(f"Found Piper model: {model_file}")
                    return model_file
        
        # No model found - try to auto-download a default model
        logger.info("No Piper model found, attempting to download default model...")
        return self._download_default_model()
    
    def _download_default_model(self) -> Optional[Path]:
        """Download a default Piper model automatically."""
        # Ensure models directory exists
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Default model: en_US-amy-medium (small, good quality)
        model_name = "en_US-amy-medium"
        model_file = settings.models_dir / f"{model_name}.onnx"
        config_file = settings.models_dir / f"{model_name}.onnx.json"
        
        try:
            # Check if already downloaded
            if model_file.exists() and config_file.exists():
                logger.info(f"Default model already exists: {model_file}")
                return model_file
            
            logger.info(f"Downloading default Piper model: {model_name}...")
            
            # Piper models are available from HuggingFace
            # URL format: https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/{voice}/medium/{model_name}.onnx
            # For en_US-amy-medium: /en/en_US/amy/medium/en_US-amy-medium.onnx
            model_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/{model_name}.onnx"
            config_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/{model_name}.onnx.json"
            
            def show_progress(block_num, block_size, total_size):
                downloaded = block_num * block_size
                percent = min(downloaded * 100 / total_size, 100) if total_size > 0 else 0
                if block_num % 100 == 0:  # Log every 100 blocks to avoid spam
                    logger.info(f"Download progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)")
            
            # Download the model file
            logger.info(f"Downloading model from: {model_url}")
            logger.info("This may take a few minutes depending on your internet connection...")
            urllib.request.urlretrieve(model_url, model_file, reporthook=show_progress)
            
            # Download the config file
            logger.info(f"Downloading config from: {config_url}")
            urllib.request.urlretrieve(config_url, config_file)
            
            if model_file.exists() and model_file.stat().st_size > 0 and config_file.exists():
                logger.info(f"Successfully downloaded Piper model: {model_file}")
                logger.info(f"Successfully downloaded Piper config: {config_file}")
                return model_file
            else:
                logger.error("Downloaded files are incomplete or missing")
                if model_file.exists():
                    model_file.unlink()
                if config_file.exists():
                    config_file.unlink()
                return None
                
        except Exception as e:
            logger.error(f"Failed to download default Piper model: {e}")
            # Clean up partial downloads
            if model_file.exists():
                model_file.unlink()
            if config_file.exists():
                config_file.unlink()
            return None
            
    def synthesize(self, text: str, voice: Optional[str] = None, output_path: Optional[Path] = None) -> Path:
        """Synthesize text to audio.
        
        Args:
            text: Text to synthesize
            voice: Optional voice name (model name) - if provided, will try to find that model
            output_path: Optional output file path
        """
        # Try to find model if not set
        if not self.model_path or not self.model_path.exists():
            self.model_path = self._find_model()
        
        # If voice is specified, try to find that specific model
        if voice and voice != "default":
            voice_model = self._find_model_by_name(voice)
            if voice_model:
                self.model_path = voice_model
            else:
                logger.warning(f"Voice '{voice}' not found, using default model")
        
        if not self.model_path or not self.model_path.exists():
            raise RuntimeError(
                f"Piper model not configured or not found. "
                f"Please set TTS_MODEL_PATH in .env or place a .onnx model file in {settings.models_dir}"
            )
            
        # If no output path, create temp file
        if not output_path:
            import tempfile
            output_path = Path(tempfile.mktemp(suffix=".wav"))
            
        # Use subprocess to call piper
        # Piper command: piper --model <model.onnx> --output_file <output.wav>
        cmd = [
            "piper",
            "--model", str(self.model_path),
            "--output_file", str(output_path)
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate(input=text.encode("utf-8"))
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Piper failed: {error_msg}")
                raise RuntimeError(f"Piper failed: {error_msg}")
                
            return output_path
            
        except FileNotFoundError:
            raise RuntimeError("Piper executable not found. Please install piper-tts.")
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise
    
    def _find_model_by_name(self, voice_name: str) -> Optional[Path]:
        """Find a model by voice name."""
        if settings.models_dir.exists():
            # Try exact match first
            for model_file in settings.models_dir.rglob("*.onnx"):
                if model_file.stem == voice_name or model_file.name == voice_name:
                    return model_file
            # Try partial match
            for model_file in settings.models_dir.rglob("*.onnx"):
                if voice_name.lower() in model_file.stem.lower() or voice_name.lower() in model_file.name.lower():
                    return model_file
        return None

    def get_voices(self):
        """Return list of available voices (models)."""
        voices = []
        
        # If we have a model path set, use that
        if self.model_path and self.model_path.exists():
            # Use the model filename (without extension) as voice name
            voice_name = self.model_path.stem
            voices.append(voice_name)
        
        # Also scan models dir for other .onnx files
        if settings.models_dir.exists():
            for model_file in settings.models_dir.rglob("*.onnx"):
                if model_file.is_file():
                    voice_name = model_file.stem
                    if voice_name not in voices:
                        voices.append(voice_name)
        
        # If no voices found, return default
        if not voices:
            voices = ["default"]
            logger.warning(f"No Piper models found in {settings.models_dir}, returning default")
        
        return voices
