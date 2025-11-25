import logging
import subprocess
import wave
import json
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
            
    def synthesize(self, text: str, output_path: Optional[Path] = None) -> Path:
        """Synthesize text to audio."""
        if not self.model_path or not self.model_path.exists():
            raise RuntimeError("Piper model not configured or not found")
            
        # If no output path, create temp file
        if not output_path:
            import tempfile
            output_path = Path(tempfile.mktemp(suffix=".wav"))
            
        # Use subprocess to call piper
        # Assuming 'piper' is in PATH or we use the python module if available
        # But piper-tts usually provides a binary.
        # We'll try to run 'piper' command.
        
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
                logger.error(f"Piper failed: {stderr.decode()}")
                raise RuntimeError(f"Piper failed: {stderr.decode()}")
                
            return output_path
            
        except FileNotFoundError:
            raise RuntimeError("Piper executable not found. Please install piper-tts.")
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            raise

    def get_voices(self):
        """Return list of available voices (models)."""
        # Scan models dir for .onnx files?
        voices = []
        if settings.models_dir.exists():
            for f in settings.models_dir.glob("**/*.onnx"):
                if "piper" in str(f).lower():
                    voices.append(f.name)
        return voices
