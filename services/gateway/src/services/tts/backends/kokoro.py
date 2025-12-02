
import io
import subprocess
import sys
import platform
import logging
import asyncio
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
        self._service_dir = Path(__file__).parent.parent.parent.parent.parent.parent / "kokoro-tts-service"
        self._voice: Optional[str] = None
        self._voice_1: Optional[str] = None
        self._voice_2: Optional[str] = None
        self._model_files = {
            "model": self._service_dir / "src" / "kokoro_tts" / "kokoro.onnx",
            "voices": self._service_dir / "src" / "kokoro_tts" / "voices.json"
        }
        self._options = {
            "speed": 1.0,
            "lang": "en-us"
        }
    
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
        
        if await self.is_service_running():
            self.status = TTSBackendStatus.READY
            self.error_message = None  # Clear any previous error
            return True
            
        # Auto-start if not running?
        # Maybe not by default, let the user choose via UI
        self.error_message = "Kokoro service not running (Port 8880)"
        self.status = TTSBackendStatus.ERROR
        return False
    
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Synthesize text using Kokoro TTS."""
        if not self.is_ready:
            await self.initialize()
        
        if not self.is_ready:
            raise RuntimeError(f"Kokoro TTS backend not ready: {self._error_message}")
        
        self._is_generating = True
        
        try:
            loop = asyncio.get_event_loop()
            import tempfile
            import os
            
            def _synthesize():
                try:
                    import kokoro_tts
                    import sys
                    
                    # Use model files from our model directory
                    model_file = self._model_files["model"]
                    voices_file = self._model_files["voices"]
                    
                    # Verify files exist (they should have been downloaded during initialization)
                    if not model_file.exists() or not voices_file.exists():
                        error_msg = (
                            "Kokoro TTS model files are missing. "
                            "Required files: kokoro-v1.0.onnx and voices-v1.0.bin. "
                            "Files should be in: " + str(self._model_dir)
                        )
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)
                    
                    # Kokoro TTS convert_text_to_audio expects input_file (file path), not text directly
                    # Create temp files for input text and output audio
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as input_tmp:
                        input_path = input_tmp.name
                        input_tmp.write(text)
                    
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_tmp:
                        output_path = output_tmp.name
                    
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
                        
                        # Check if voice mixing is enabled (both voice_1 and voice_2 are set)
                        voice_1 = self._voice_1
                        voice_2 = self._voice_2
                        use_voice_mixing = voice_1 is not None and voice_2 is not None
                        
                        if use_voice_mixing:
                            # Voice mixing mode: generate with both voices and blend
                            voice_1_weight = self._options.get("voice_1_weight", 0.5)
                            voice_2_weight = self._options.get("voice_2_weight", 0.5)
                            
                            # Normalize weights to sum to 1.0
                            total_weight = voice_1_weight + voice_2_weight
                            if total_weight > 0:
                                voice_1_weight = voice_1_weight / total_weight
                                voice_2_weight = voice_2_weight / total_weight
                            else:
                                voice_1_weight = 0.5
                                voice_2_weight = 0.5
                            
                            # Generate audio with voice_1
                            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_tmp_1:
                                output_path_1 = output_tmp_1.name
                            
                            # Generate audio with voice_2
                            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_path_2:
                                output_path_2 = output_path_2.name
                            
                            try:
                                # Generate with voice_1
                                kokoro_tts.convert_text_to_audio(
                                    input_file=input_path,
                                    output_file=output_path_1,
                                    voice=voice_1,
                                    speed=self._options.get("speed", 1.0),
                                    lang='en-us',
                                    model_path=str(model_file),
                                    voices_path=str(voices_file)
                                )
                                
                                # Generate with voice_2
                                kokoro_tts.convert_text_to_audio(
                                    input_file=input_path,
                                    output_file=output_path_2,
                                    voice=voice_2,
                                    speed=self._options.get("speed", 1.0),
                                    lang='en-us',
                                    model_path=str(model_file),
                                    voices_path=str(voices_file)
                                )
                                
                                # Mix the two audio files
                                try:
                                    import numpy as np
                                    import wave
                                    import struct
                                    
                                    # Read both WAV files
                                    def read_wav(filepath):
                                        with wave.open(filepath, 'rb') as wav:
                                            frames = wav.readframes(-1)
                                            sample_rate = wav.getframerate()
                                            channels = wav.getnchannels()
                                            sample_width = wav.getsampwidth()
                                            # Convert to numpy array
                                            if sample_width == 1:
                                                dtype = np.uint8
                                                audio = np.frombuffer(frames, dtype=dtype).astype(np.float32) / 128.0 - 1.0
                                            elif sample_width == 2:
                                                dtype = np.int16
                                                audio = np.frombuffer(frames, dtype=dtype).astype(np.float32) / 32768.0
                                            else:
                                                raise RuntimeError(f"Unsupported sample width: {sample_width}")
                                            return audio, sample_rate, channels, sample_width
                                    
                                    audio_1, sr_1, ch_1, sw_1 = read_wav(output_path_1)
                                    audio_2, sr_2, ch_2, sw_2 = read_wav(output_path_2)
                                    
                                    # Ensure same length (pad shorter one with zeros)
                                    max_len = max(len(audio_1), len(audio_2))
                                    if len(audio_1) < max_len:
                                        audio_1 = np.pad(audio_1, (0, max_len - len(audio_1)), mode='constant')
                                    if len(audio_2) < max_len:
                                        audio_2 = np.pad(audio_2, (0, max_len - len(audio_2)), mode='constant')
                                    
                                    # Mix with weights
                                    mixed_audio = (audio_1 * voice_1_weight + audio_2 * voice_2_weight)
                                    
                                    # Clamp to valid range
                                    mixed_audio = np.clip(mixed_audio, -1.0, 1.0)
                                    
                                    # Convert back to int16 and write to output file
                                    mixed_audio_int16 = (mixed_audio * 32767).astype(np.int16)
                                    
                                    with wave.open(output_path, 'wb') as wav_out:
                                        wav_out.setnchannels(ch_1)
                                        wav_out.setsampwidth(sw_1)
                                        wav_out.setframerate(sr_1)
                                        wav_out.writeframes(mixed_audio_int16.tobytes())
                                    
                                except ImportError:
                                    # Fallback: if numpy/wave not available, just use voice_1
                                    logger.warning("numpy/wave not available for voice mixing, using voice_1 only")
                                    import shutil
                                    shutil.copy(output_path_1, output_path)
                                except Exception as e:
                                    logger.error(f"Failed to mix voices: {e}")
                                    # Fallback: use voice_1
                                    import shutil
                                    shutil.copy(output_path_1, output_path)
                                
                                # Clean up temp files
                                if os.path.exists(output_path_1):
                                    os.unlink(output_path_1)
                                if os.path.exists(output_path_2):
                                    os.unlink(output_path_2)
                            except SystemExit as e:
                                raise RuntimeError(
                                    f"Kokoro TTS failed (exit code {e.code}). "
                                    "Model files may be missing or invalid."
                                ) from e
                        else:
                            # Single voice mode (backward compatible)
                            try:
                                kokoro_tts.convert_text_to_audio(
                                    input_file=input_path,
                                    output_file=output_path,
                                    voice=voice or self._voice,
                                    speed=self._options.get("speed", 1.0),
                                    lang='en-us',  # Default language
                                    model_path=str(model_file),
                                    voices_path=str(voices_file)
                                )
                            except SystemExit as e:
                                # Kokoro TTS called sys.exit - convert to RuntimeError to prevent server crash
                                raise RuntimeError(
                                    f"Kokoro TTS failed (exit code {e.code}). "
                                    "Model files may be missing or invalid. "
                                    "Ensure kokoro-v1.0.onnx and voices-v1.0.bin are available. "
                                    "Download from: https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/"
                                ) from e
                        
                        # Read audio from output file
                        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                            raise RuntimeError("Kokoro TTS did not generate audio file")
                        
                        with open(output_path, 'rb') as f:
                            audio_data = f.read()
                        
                        return audio_data
                    finally:
                        # Clean up temp files
                        if os.path.exists(input_path):
                            os.unlink(input_path)
                        if os.path.exists(output_path):
                            os.unlink(output_path)
                except SystemExit as e:
                    # Catch SystemExit and convert to RuntimeError to prevent server crash
                    error_msg = f"Kokoro TTS exited with code {e.code}. Model files may be missing."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e
                except Exception as e:
                    logger.error(f"Kokoro TTS synthesis failed: {e}")
                    raise
            
            audio_data = await loop.run_in_executor(None, _synthesize)
            return audio_data
        finally:
            self._is_generating = False
    
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get available Kokoro voices by querying the actual engine."""
        if not self.is_ready:
            # Try to get voices even if not fully initialized
            pass
        
        try:
            import kokoro_tts
            import subprocess
            import re
            
            # Try to get voices from kokoro_tts module
            voices = []
            
            # Method 1: Try to call kokoro-tts command to list voices
            # The error message shows voices are listed when running the command
            try:
                # Check if we can get voices from the module directly
                if hasattr(kokoro_tts, 'get_available_voices'):
                    voice_list = kokoro_tts.get_available_voices()
                    for voice_id in voice_list:
                        voices.append({
                            "id": voice_id,
                            "name": voice_id.replace('_', ' ').title(),
                            "language": self._parse_voice_language(voice_id),
                            "accent": self._parse_voice_accent(voice_id)
                        })
                    if voices:
                        return voices
            except Exception:
                pass
            
            # Method 2: Try to run kokoro-tts with invalid input to get voice list from error message
            # This is a fallback - the error message contains the voice list
            try:
                # Use the model files we have
                model_file = self._model_files["model"]
                voices_file = self._model_files["voices"]
                
                if model_file.exists() and voices_file.exists():
                    # Try to get voices by running kokoro-tts with help or invalid voice
                    # We'll parse the error output which contains the voice list
                    import sys as sys_module
                    result = subprocess.run(
                        [sys_module.executable, "-m", "kokoro_tts", "--help"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False
                    )
                    
                    # The actual voice list comes from the error when using invalid voice
                    # But we can also try to import and check the voices directly
                    # Based on the error message, we know the real voices
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
                    
                    for voice_id in real_voices:
                        voices.append({
                            "id": voice_id,
                            "name": voice_id.replace('_', ' ').title(),
                            "language": self._parse_voice_language(voice_id),
                            "accent": self._parse_voice_accent(voice_id)
                        })
                    
                    if voices:
                        return voices
            except Exception as e:
                logger.debug("Could not get voices from kokoro-tts command: %s", e)
            
            # Fallback: return empty list if we can't get real voices
            logger.debug("Could not determine real Kokoro voices, returning empty list")
            return []
            
        except ImportError:
            # This is expected if kokoro_tts is not installed in this venv
            # We should probably return the hardcoded list anyway if we know them
            logger.debug("kokoro_tts module not found, using fallback voice list")
            
            # Use fallback list
            voices = []
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
            
            for voice_id in real_voices:
                voices.append({
                    "id": voice_id,
                    "name": voice_id.replace('_', ' ').title(),
                    "language": self._parse_voice_language(voice_id),
                    "accent": self._parse_voice_accent(voice_id)
                })
            return voices
            
        except Exception as e:
            logger.warning("Error getting Kokoro voices: %s", e)
            return []
    
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
            "voice_1": self._voice_1,
            "voice_2": self._voice_2,
            "speed": {
                "value": self._options.get("speed", 1.0),
                "min": 0.5,
                "max": 2.0,
                "step": 0.1,
                "description": "Speech speed multiplier"
            },
            "temperature": {
                "value": self._options.get("temperature", 0.7),
                "min": 0.0,
                "max": 1.0,
                "step": 0.1,
                "description": "Sampling temperature (higher = more random)"
            },
            "top_p": {
                "value": self._options.get("top_p", 0.9),
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "description": "Nucleus sampling threshold"
            },
            "top_k": {
                "value": self._options.get("top_k", 50),
                "min": 1,
                "max": 100,
                "step": 1,
                "description": "Top-k sampling (number of tokens to consider)"
            },
            "voice_1_weight": {
                "value": self._options.get("voice_1_weight", 0.5),
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "description": "Weight for voice_1 when mixing (0.0-1.0, only used when voice_1 and voice_2 are both set)"
            },
            "voice_2_weight": {
                "value": self._options.get("voice_2_weight", 0.5),
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "description": "Weight for voice_2 when mixing (0.0-1.0, only used when voice_1 and voice_2 are both set)"
            },
            "seed": {
                "value": self._options.get("seed"),
                "description": "Random seed for reproducible generation (None = random, integer = fixed seed)"
            }
        }
    
    def set_options(self, options: Dict[str, Any]) -> bool:
        """Set Kokoro TTS options."""
        try:
            if "voice" in options:
                self._voice = options["voice"]
            if "voice_1" in options:
                self._voice_1 = options["voice_1"]
            if "voice_2" in options:
                self._voice_2 = options["voice_2"]
            
            # Handle structured options (with value key) or direct values
            for key in ["speed", "temperature", "top_p", "top_k", "voice_1_weight", "voice_2_weight", "seed"]:
                if key in options:
                    value = options[key]
                    # If it's a dict with 'value' key, extract the value
                    if isinstance(value, dict) and "value" in value:
                        value = value["value"]
                    
                    if key == "speed" and isinstance(value, (int, float)):
                        self._options["speed"] = max(0.5, min(2.0, float(value)))
                    elif key in ["temperature", "top_p", "voice_1_weight", "voice_2_weight"] and isinstance(value, (int, float)):
                        self._options[key] = max(0.0, min(1.0, float(value)))
                    elif key == "top_k" and isinstance(value, int):
                        self._options["top_k"] = max(1, min(100, int(value)))
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
            logger.error("Error setting Kokoro options: %s", str(e))
            return False


