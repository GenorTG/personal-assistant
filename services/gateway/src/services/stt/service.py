"""Speech-to-Text service."""
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import os
import json
import urllib.request
import zipfile
import shutil
import logging
import psutil
from ...config.settings import settings

logger = logging.getLogger(__name__)


class STTService:
    """Speech-to-Text service using faster-whisper or Vosk."""
    
    def __init__(self):
        self.provider = settings.stt_provider
        self.model = None
        self.vosk_model_path: Optional[Path] = None
        self._initialized = False
        self._current_model_size: Optional[str] = None
        self._baseline_memory_mb: Optional[float] = None
        self._download_status: Dict[str, Dict[str, Any]] = {}

    def get_download_status(self, model_size: str) -> Dict[str, Any]:
        """Get status for a requested model download."""
        return self._download_status.get(
            model_size,
            {
                "status": "not_found",
                "model_id": model_size,
                "downloaded": False,
            },
        )

    def download_model_size(self, model_size: str) -> None:
        """
        Trigger an on-demand download of a faster-whisper model by initializing it once.
        This does NOT switch the currently loaded model; it only warms the cache.
        """
        # Mark queued immediately
        self._download_status[model_size] = {
            "status": "queued",
            "model_id": model_size,
            "downloaded": False,
            "message": "Queued download",
        }

        import threading

        def _run():
            try:
                self._download_status[model_size] = {
                    "status": "downloading",
                    "model_id": model_size,
                    "downloaded": False,
                    "message": "Downloading model (initializing once to populate cache)...",
                }
                from faster_whisper import WhisperModel

                # Use CPU+int8 for the download warmup to reduce GPU impact
                _ = WhisperModel(model_size, device="cpu", compute_type="int8")
                # If constructor returns, the model is available in cache
                self._download_status[model_size] = {
                    "status": "ready",
                    "model_id": model_size,
                    "downloaded": True,
                    "message": "Model downloaded and cached",
                }
            except Exception as e:
                self._download_status[model_size] = {
                    "status": "error",
                    "model_id": model_size,
                    "downloaded": False,
                    "error": str(e),
                }

        threading.Thread(target=_run, daemon=True).start()
    
    def _initialize_model(self):
        """Initialize STT model (auto-downloads on first use)."""
        if self._initialized:
            return
        
        try:
            logger.info(f"Initializing STT model (provider: {self.provider})...")
            if self.provider == "faster-whisper":
                self._initialize_faster_whisper()
                self._initialized = True
                logger.info("STT model initialized successfully")
            elif self.provider == "vosk":
                self._initialize_vosk()
                self._initialized = True
                logger.info("STT model initialized successfully")
            else:
                raise ValueError(f"Unknown STT provider: {self.provider}")
        except Exception as e:
            logger.error(f"Failed to initialize STT model: {e}", exc_info=True)
            self._initialized = False
            raise
    
    def _initialize_faster_whisper(self):
        """Initialize faster-whisper model (auto-downloads on first use)."""
        try:
            from faster_whisper import WhisperModel
            
            # faster-whisper automatically downloads models on first use
            # Models are cached in the default cache directory
            model_size = settings.stt_model_size
            logger.info(f"Initializing faster-whisper model: {model_size}")
            
            # Auto-detect device and compute type
            device, compute_type = self._detect_device_and_compute_type()
            logger.info(f"Using device: {device}, compute_type: {compute_type}")
            
            # Initialize model - this will auto-download if not cached
            # Model is kept in memory for fast subsequent calls
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type
            )
            self._current_model_size = model_size
            logger.info(f"faster-whisper model initialized successfully on {device}")
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed. Install with: pip install faster-whisper"
            )
        except Exception as e:
            logger.error(f"Failed to initialize faster-whisper: {e}")
            raise
    
    def _detect_device_and_compute_type(self) -> tuple[str, str]:
        """Detect best device and compute type for faster-whisper."""
        try:
            import torch
            if torch.cuda.is_available():
                # CUDA available - use GPU
                device = "cuda"
                # Try float16 for speed, fallback to int8 if not supported
                compute_type = "float16"
                logger.info(f"CUDA detected: {torch.cuda.get_device_name(0)}")
                return device, compute_type
        except ImportError:
            pass
        
        # Fallback to CPU
        device = "cpu"
        compute_type = "int8"  # int8 is faster on CPU
        return device, compute_type
    
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
            self._current_model_size = "vosk-en-us-0.22"
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
        
        Model is preloaded and kept in memory for fast inference.
        
        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en', 'es')
        
        Returns:
            Tuple of (transcribed_text, detected_language)
        """
        # Ensure model is initialized (should be preloaded on startup)
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
    
    def unload_model(self) -> bool:
        """Unload current model from memory."""
        try:
            if self.model:
                # Clear model reference
                self.model = None
                self._initialized = False
                self._current_model_size = None
                logger.info("STT model unloaded from memory")
                return True
            return False
        except Exception as e:
            logger.error(f"Error unloading STT model: {e}")
            return False
    
    def switch_model_size(self, model_size: str) -> bool:
        """Switch Whisper model size (only for faster-whisper)."""
        if self.provider != "faster-whisper":
            logger.warning("Model switching only supported for faster-whisper")
            return False
        
        try:
            # Unload current model
            self.unload_model()
            
            # Update settings
            from ...config.settings import settings
            settings.stt_model_size = model_size
            
            # Reinitialize with new size
            self._initialize_faster_whisper()
            logger.info(f"Switched STT model to: {model_size}")
            return True
        except Exception as e:
            logger.error(f"Error switching STT model size: {e}")
            return False
    
    def get_model_status(self) -> Dict[str, Any]:
        """Get current model status and information."""
        status = {
            "loaded": self._initialized and self.model is not None,
            "provider": self.provider,
            "model_size": self._current_model_size,
            "initialized": self._initialized
        }
        
        if self.provider == "faster-whisper" and self._current_model_size:
            # Model size estimates (approximate)
            size_estimates = {
                "tiny": {"size_mb": 39, "memory_mb": 150},
                "base": {"size_mb": 74, "memory_mb": 250},
                "small": {"size_mb": 244, "memory_mb": 500},
                "medium": {"size_mb": 769, "memory_mb": 1200},
                "large": {"size_mb": 1550, "memory_mb": 2500},
                "large-v2": {"size_mb": 1550, "memory_mb": 2500},
                "large-v3": {"size_mb": 1550, "memory_mb": 2500},
            }
            if self._current_model_size in size_estimates:
                status.update(size_estimates[self._current_model_size])
        elif self.provider == "vosk":
            status.update({
                "size_mb": 50,  # Approximate
                "memory_mb": 100  # Approximate
            })
        
        return status
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage for STT service."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            # Estimate model memory (rough estimate)
            model_memory_mb = 0
            if self._initialized and self.model:
                if self.provider == "faster-whisper" and self._current_model_size:
                    size_estimates = {
                        "tiny": 150,
                        "base": 250,
                        "small": 500,
                        "medium": 1200,
                        "large": 2500,
                        "large-v2": 2500,
                        "large-v3": 2500,
                    }
                    model_memory_mb = size_estimates.get(self._current_model_size, 0)
                elif self.provider == "vosk":
                    model_memory_mb = 100
            
            return {
                "total_memory_mb": round(memory_mb, 2),
                "model_memory_mb": round(model_memory_mb, 2),
                "base_memory_mb": round(memory_mb - model_memory_mb, 2) if model_memory_mb > 0 else round(memory_mb, 2)
            }
        except Exception as e:
            logger.error(f"Error getting STT memory usage: {e}")
            return {
                "total_memory_mb": 0,
                "model_memory_mb": 0,
                "base_memory_mb": 0,
                "error": str(e)
            }
