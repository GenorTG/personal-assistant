"""Speech-to-Text service."""
from typing import Optional, Tuple
from pathlib import Path
import os
import json
import urllib.request
import zipfile
import shutil
import logging
from ...config.settings import settings

logger = logging.getLogger(__name__)


class STTService:
    """Speech-to-Text service using faster-whisper or Vosk."""
    
    def __init__(self):
        self.provider = settings.stt_provider
        self.model = None
        self.vosk_model_path: Optional[Path] = None
        self._initialized = False
    
    def _initialize_model(self):
        """Initialize STT model (auto-downloads on first use)."""
        if self._initialized:
            return
        
        try:
            logger.info(f"Initializing STT model (provider: {self.provider})...")
            if self.provider == "faster-whisper":
                self._initialize_faster_whisper()
            elif self.provider == "vosk":
                self._initialize_vosk()
            else:
                raise ValueError(f"Unknown STT provider: {self.provider}")
            self._initialized = True
            logger.info("STT model initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize STT model: {e}")
            raise
    
    def _initialize_faster_whisper(self):
        """Initialize faster-whisper model (auto-downloads on first use)."""
        try:
            from faster_whisper import WhisperModel
            
            # faster-whisper automatically downloads models on first use
            # Models are cached in the default cache directory
            model_size = settings.stt_model_size
            logger.info(f"Initializing faster-whisper model: {model_size}")
            
            # Initialize model - this will auto-download if not cached
            self.model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8"  # Use int8 for faster inference
            )
            logger.info("faster-whisper model initialized successfully")
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed. Install with: pip install faster-whisper"
            )
        except Exception as e:
            logger.error(f"Failed to initialize faster-whisper: {e}")
            raise
    
    def _initialize_vosk(self):
        """Initialize Vosk model (auto-downloads if needed)."""
        try:
            import vosk
            
            # Ensure Vosk model is downloaded
            model_path = self._ensure_vosk_model()
            logger.info(f"Initializing Vosk model from: {model_path}")
            
            # Initialize Vosk model
            self.model = vosk.Model(str(model_path))
            self.vosk_model_path = model_path
            logger.info("Vosk model initialized successfully")
        except ImportError:
            raise RuntimeError(
                "vosk not installed. Install with: pip install vosk"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Vosk: {e}")
            raise
    
    def _ensure_vosk_model(self) -> Path:
        """Ensure Vosk model is downloaded (auto-download if needed)."""
        # Default to English model
        model_name = "vosk-model-en-us-0.22"
        model_dir = settings.models_dir / "vosk"
        model_path = model_dir / model_name
        
        # Check if model already exists
        if model_path.exists() and (model_path / "am").exists():
            logger.info(f"Vosk model found at: {model_path}")
            return model_path
        
        # Auto-download model
        logger.info(f"Downloading Vosk model: {model_name}")
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Vosk model download URL
        model_url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
        zip_path = model_dir / f"{model_name}.zip"
        
        try:
            # Download model
            logger.info(f"Downloading from: {model_url}")
            urllib.request.urlretrieve(model_url, zip_path)
            
            # Extract model
            logger.info("Extracting model...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(model_dir)
            
            # Remove zip file
            zip_path.unlink()
            
            # Verify extraction
            if not (model_path / "am").exists():
                raise RuntimeError(f"Model extraction failed: {model_path}")
            
            logger.info(f"Vosk model downloaded and extracted to: {model_path}")
            return model_path
        except Exception as e:
            # Clean up on error
            if zip_path.exists():
                zip_path.unlink()
            if model_path.exists():
                shutil.rmtree(model_path, ignore_errors=True)
            logger.error(f"Failed to download Vosk model: {e}")
            raise RuntimeError(f"Failed to download Vosk model: {e}")
    
    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'es')
        
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        if not self.model:
            self._initialize_model()
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        try:
            if self.provider == "faster-whisper":
                return await self._transcribe_faster_whisper(audio_path, language)
            elif self.provider == "vosk":
                return await self._transcribe_vosk(audio_path, language)
            else:
                raise ValueError(f"Unknown STT provider: {self.provider}")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    async def _transcribe_faster_whisper(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Transcribe using faster-whisper."""
        import asyncio
        
        # Run transcription in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            segments, info = self.model.transcribe(
                str(audio_path),
                language=language or settings.stt_language,
                beam_size=5
            )
            text = " ".join([segment.text for segment in segments]).strip()
            detected_language = info.language
            return text, detected_language
        
        text, detected_language = await loop.run_in_executor(None, _transcribe)
        return text, detected_language
    
    async def _transcribe_vosk(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Transcribe using Vosk."""
        import asyncio
        import wave
        import json
        
        # Vosk requires WAV format with specific parameters
        # For other formats, we'd need to convert first
        if audio_path.suffix.lower() != '.wav':
            raise ValueError(
                f"Vosk requires WAV format. Got: {audio_path.suffix}. "
                "Please convert audio to WAV format first."
            )
        
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            import vosk
            
            # Create recognizer
            rec = vosk.KaldiRecognizer(self.model, 16000)  # 16kHz sample rate
            rec.SetWords(True)
            
            # Read audio file
            wf = wave.open(str(audio_path), "rb")
            
            # Check sample rate
            if wf.getnchannels() != 1:
                raise ValueError("Vosk requires mono audio")
            if wf.getcomptype() != "NONE":
                raise ValueError("Vosk requires uncompressed WAV")
            
            text_parts = []
            
            # Process audio in chunks
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    if result.get("text"):
                        text_parts.append(result["text"])
            
            # Final result
            final_result = json.loads(rec.FinalResult())
            if final_result.get("text"):
                text_parts.append(final_result["text"])
            
            wf.close()
            
            text = " ".join(text_parts).strip()
            # Vosk doesn't provide language detection, use provided or default
            detected_language = language or settings.stt_language
            
            return text, detected_language
        
        text, detected_language = await loop.run_in_executor(None, _transcribe)
        return text, detected_language
    
    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        language: Optional[str] = None,
        sample_rate: int = 16000
    ) -> Tuple[str, Optional[str]]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Audio data as bytes
            language: Optional language code
            sample_rate: Audio sample rate (default 16000)
        
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        if not self.model:
            self._initialize_model()
        
        # Save bytes to temporary file and transcribe
        import tempfile
        import aiofiles
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        async with aiofiles.open(tmp_path, 'wb') as f:
            await f.write(audio_bytes)
        
        try:
            result = await self.transcribe(tmp_path, language)
            return result
        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()
