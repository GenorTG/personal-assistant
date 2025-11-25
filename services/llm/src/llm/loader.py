"""LLM loader using llama.cpp."""
from typing import Optional, Any, AsyncIterator, Tuple, Dict, List
from pathlib import Path
import asyncio
import logging
from llama_cpp import Llama
from .sampler import SamplerSettings
from src.config import settings

logger = logging.getLogger(__name__)


class LLMLoader:
    """Loads and manages llama.cpp models."""
    
    def __init__(self):
        self.models: Dict[str, Llama] = {}
        self._lock = asyncio.Lock()
        self._gpu_layers = self._detect_gpu_layers()
    
    def _verify_cuda_runtime(self) -> Tuple[bool, str]:
        """Verify CUDA runtime is actually available and usable.
        
        Returns:
            Tuple of (is_available, message) where is_available indicates if CUDA is usable
        """
        # Method 1: Check if llama-cpp-python has CUDA support compiled in
        try:
            from llama_cpp import llama_cpp
            # Check for CUDA-related functions/symbols
            has_cuda_support = (
                hasattr(llama_cpp, 'llama_supports_gpu_offload') or
                hasattr(llama_cpp, 'llama_gpu_offload') or
                hasattr(llama_cpp, 'llama_n_gpu_layers') or
                'cuda' in str(llama_cpp).lower()
            )
            if not has_cuda_support:
                return False, "llama-cpp-python was compiled without CUDA support. Install with: pip install llama-cpp-python[cuda]"
        except (ImportError, AttributeError) as e:
            return False, f"Could not verify llama-cpp-python CUDA support: {e}"
        
        # Method 2: Try PyTorch CUDA (most reliable)
        try:
            import torch
            if torch.cuda.is_available():
                try:
                    # Actually try to use CUDA
                    device = torch.device('cuda:0')
                    test_tensor = torch.zeros(1).to(device)
                    gpu_count = torch.cuda.device_count()
                    cuda_version = torch.version.cuda
                    gpu_name = torch.cuda.get_device_name(0)
                    return True, f"CUDA runtime verified: {gpu_count} GPU(s) available, CUDA {cuda_version}, GPU: {gpu_name}"
                except Exception as e:
                    return False, f"CUDA hardware detected but runtime not usable: {e}"
            else:
                return False, "PyTorch CUDA not available (torch.cuda.is_available() = False)"
        except ImportError:
            pass  # PyTorch not installed, try other methods
        except Exception as e:
            logger.debug("PyTorch CUDA check failed: %s", e)
        
        # Method 3: Check nvidia-smi (driver check)
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                gpu_info = result.stdout.strip().split('\n')[0] if result.stdout.strip() else "Unknown GPU"
                return False, f"NVIDIA driver detected ({gpu_info}) but CUDA runtime not verified. Install CUDA toolkit and llama-cpp-python[cuda]"
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.debug("nvidia-smi check failed: %s", e)
        
        # Method 4: Check CUDA libraries directly
        try:
            import ctypes
            try:
                cuda = ctypes.CDLL("libcuda.so.1")
                # Try to get CUDA version
                return False, "CUDA library found but runtime not verified. Install llama-cpp-python[cuda] to use GPU"
            except OSError:
                try:
                    # Windows
                    cuda = ctypes.windll.LoadLibrary("nvcuda.dll")
                    return False, "CUDA library found (Windows) but runtime not verified. Install llama-cpp-python[cuda] to use GPU"
                except OSError:
                    pass
        except Exception as e:
            logger.debug("CUDA library check failed: %s", e)
        
        return False, "No CUDA runtime detected. Install CUDA toolkit and llama-cpp-python[cuda] to use GPU"
    
    def _detect_gpu_layers(self) -> int:
        """Auto-detect GPU and return appropriate n_gpu_layers value.
        
        Returns:
            Number of GPU layers to use (0 if no GPU, -1 for all layers if GPU available)
        """
        # If user explicitly set a value, use it (even if 0)
        if settings.llm_n_gpu_layers != 0:
            logger.info("Using %d GPU layers (user specified)", settings.llm_n_gpu_layers)
            return settings.llm_n_gpu_layers
        
        # Verify CUDA runtime is actually available and usable
        cuda_available, cuda_message = self._verify_cuda_runtime()
        
        if cuda_available:
            logger.info("✓ %s", cuda_message)
            logger.info("GPU detected - defaulting to all layers on GPU (-1). Set llm_n_gpu_layers=0 to force CPU mode.")
            return -1  # -1 means all layers on GPU
        else:
            logger.warning("✗ CUDA runtime not available: %s", cuda_message)
            logger.info("Using CPU mode. Set llm_n_gpu_layers > 0 to use GPU if available.")
            return 0
    
    async def load_model(
        self,
        model_path: str,
        n_ctx: Optional[int] = None,
        n_threads: Optional[int] = None,
        n_gpu_layers: Optional[int] = None,
        use_flash_attention: Optional[bool] = None,
        use_mmap: Optional[bool] = None,
        use_mlock: Optional[bool] = None,
        n_batch: Optional[int] = None,
        n_predict: Optional[int] = None,
        rope_freq_base: Optional[float] = None,
        rope_freq_scale: Optional[float] = None,
        low_vram: Optional[bool] = None,
        main_gpu: Optional[int] = None,
        tensor_split: Optional[List[float]] = None,
        offload_kqv: Optional[bool] = None
    ) -> Llama:
        """Load a GGUF model using llama.cpp.
        
        Args:
            model_path: Path to the GGUF model file
            n_ctx: Context window size (defaults to settings.llm_context_size)
            n_threads: Number of threads (defaults to settings.llm_n_threads)
            n_gpu_layers: Number of GPU layers (defaults to settings.llm_n_gpu_layers)
        
        Returns:
            Loaded Llama model instance
        
        Raises:
            FileNotFoundError: If model file doesn't exist
            RuntimeError: If model loading fails
        """
        model_path_obj = Path(model_path)
        if not model_path_obj.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        # Use absolute path as key for caching
        abs_path = str(model_path_obj.resolve())
        
        async with self._lock:
            # Check if already loaded
            if abs_path in self.models:
                return self.models[abs_path]
            
            # Load model in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            # Use detected GPU layers if not explicitly provided
            effective_gpu_layers = n_gpu_layers if n_gpu_layers is not None else self._gpu_layers
            model = await loop.run_in_executor(
                None,
                self._load_model_sync,
                abs_path,
                n_ctx or settings.llm_context_size,
                n_threads or settings.llm_n_threads,
                effective_gpu_layers,
                use_flash_attention,
                use_mmap,
                use_mlock,
                n_batch,
                n_predict,
                rope_freq_base,
                rope_freq_scale,
                low_vram,
                main_gpu,
                tensor_split,
                offload_kqv
            )
            
            self.models[abs_path] = model
            return model
    
    def _load_model_sync(
        self,
        model_path: str,
        n_ctx: int,
        n_threads: int,
        n_gpu_layers: int,
        use_flash_attention: Optional[bool] = None,
        use_mmap: Optional[bool] = None,
        use_mlock: Optional[bool] = None,
        n_batch: Optional[int] = None,
        n_predict: Optional[int] = None,
        rope_freq_base: Optional[float] = None,
        rope_freq_scale: Optional[float] = None,
        low_vram: Optional[bool] = None,
        main_gpu: Optional[int] = None,
        tensor_split: Optional[List[float]] = None,
        offload_kqv: Optional[bool] = None
    ) -> Llama:
        """Synchronous model loading (runs in executor)."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("Initializing Llama model with n_gpu_layers=%d, n_threads=%d, n_ctx=%d", 
                       n_gpu_layers, n_threads, n_ctx)
            
            # Check if llama-cpp-python has CUDA support
            try:
                from llama_cpp import llama_cpp
                has_cuda = hasattr(llama_cpp, 'llama_supports_gpu_offload') or hasattr(llama_cpp, 'llama_gpu_offload')
                if n_gpu_layers != 0 and not has_cuda:
                    logger.error("=" * 60)
                    logger.error("GPU INFERENCE NOT AVAILABLE")
                    logger.error("=" * 60)
                    logger.error("GPU layers requested (%d) but llama-cpp-python doesn't have CUDA support compiled in.", n_gpu_layers)
                    logger.error("")
                    logger.error("To fix this, install llama-cpp-python with CUDA support:")
                    logger.error("  pip uninstall llama-cpp-python")
                    logger.error("  pip install llama-cpp-python[cuda]")
                    logger.error("")
                    logger.error("This will compile llama-cpp-python with CUDA support.")
                    logger.error("Falling back to CPU mode.")
                    logger.error("=" * 60)
                    n_gpu_layers = 0
            except (ImportError, AttributeError):
                logger.warning("Could not verify CUDA support in llama-cpp-python")
            
            # Build Llama parameters
            llama_params = {
                "model_path": model_path,
                "n_ctx": n_ctx,
                "n_threads": n_threads,
                "n_gpu_layers": n_gpu_layers,
                "verbose": True  # Enable verbose to see GPU usage
            }
            
            # Add optional parameters if provided
            if use_mmap is not None:
                llama_params["use_mmap"] = use_mmap
            if use_mlock is not None:
                llama_params["use_mlock"] = use_mlock
            if n_batch is not None:
                llama_params["n_batch"] = n_batch
            if n_predict is not None:
                llama_params["n_predict"] = n_predict
            if rope_freq_base is not None:
                llama_params["rope_freq_base"] = rope_freq_base
            if rope_freq_scale is not None:
                llama_params["rope_freq_scale"] = rope_freq_scale
            if low_vram is not None:
                llama_params["low_vram"] = low_vram
            if main_gpu is not None:
                llama_params["main_gpu"] = main_gpu
            if tensor_split is not None:
                llama_params["tensor_split"] = tensor_split
            if offload_kqv is not None:
                llama_params["offload_kqv"] = offload_kqv
            if use_flash_attention is not None:
                # Flash attention is typically handled at model level in llama.cpp
                # Some models support it natively, but we log it for now
                logger.info("Flash attention requested: %s (note: model must support it)", use_flash_attention)
                # Note: llama-cpp-python doesn't have a direct flash_attention parameter
                # It's usually enabled automatically if the model supports it
                # Flash attention is enabled by default in newer llama.cpp versions if supported
            
            model = Llama(**llama_params)
            
            # Verify GPU usage after loading
            if n_gpu_layers != 0:
                try:
                    # Try to get GPU info from the model if available
                    if hasattr(model, 'ctx') and hasattr(model.ctx, 'gpu_layers'):
                        actual_gpu_layers = getattr(model.ctx, 'gpu_layers', 0)
                        if actual_gpu_layers == 0 and n_gpu_layers != 0:
                            logger.error("=" * 60)
                            logger.error("WARNING: GPU LAYERS MISMATCH!")
                            logger.error("=" * 60)
                            logger.error("Requested %d GPU layers but model loaded with 0 GPU layers (CPU only)!", n_gpu_layers)
                            logger.error("This usually means llama-cpp-python was compiled without CUDA support.")
                            logger.error("To fix: pip uninstall llama-cpp-python && pip install llama-cpp-python[cuda]")
                            logger.error("=" * 60)
                        else:
                            logger.info("✓ Model loaded with %d GPU layers (requested: %d)", actual_gpu_layers, n_gpu_layers)
                            # Additional verification: check if CUDA is actually being used
                            try:
                                import torch
                                if torch.cuda.is_available():
                                    gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                                    logger.info("✓ CUDA GPU available: %s (%.1f GB)", torch.cuda.get_device_name(0), gpu_memory)
                            except Exception:
                                pass
                    else:
                        # Try alternative method to verify GPU usage
                        logger.warning("Could not verify GPU layers from model context, but n_gpu_layers=%d was set", n_gpu_layers)
                except Exception as e:
                    logger.warning("Could not verify GPU layers: %s", e)
            
            logger.info("Model initialized successfully")
            return model
        except Exception as e:
            logger.error("Failed to load model: %s", e, exc_info=True)
            raise RuntimeError(f"Failed to load model {model_path}: {str(e)}") from e
    
    async def generate(
        self,
        model: Llama,
        prompt: str,
        settings: SamplerSettings,
        stream: bool = False
    ) -> str:
        """Generate text using the model.
        
        Args:
            model: Loaded Llama model instance
            prompt: Input prompt
            settings: Sampler settings
            stream: Whether to stream the response (not yet implemented)
        
        Returns:
            Generated text response
        """
        loop = asyncio.get_event_loop()
        
        # Run generation in executor to avoid blocking
        response = await loop.run_in_executor(
            None,
            self._generate_sync,
            model,
            prompt,
            settings
        )
        
        return response
    
    def _generate_sync(
        self,
        model: Llama,
        prompt: str,
        settings: SamplerSettings
    ) -> str:
        """Synchronous text generation (runs in executor)."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug("Generating text with prompt length: %d, max_tokens: %d", 
                       len(prompt), settings.max_tokens)
            
            response = model(
                prompt,
                temperature=settings.temperature,
                top_p=settings.top_p,
                top_k=settings.top_k,
                repeat_penalty=settings.repeat_penalty,
                max_tokens=settings.max_tokens,
                stop=["</s>", "\n\n\n"],  # Common stop sequences
                echo=False
            )
            
            # Extract text from response
            if response and "choices" in response and len(response["choices"]) > 0:
                text = response["choices"][0]["text"].strip()
                logger.debug("Generated text length: %d", len(text))
                return text
            else:
                logger.warning("No text in model response")
                return ""
        except Exception as e:
            logger.error("Text generation failed: %s", e, exc_info=True)
            raise RuntimeError(f"Text generation failed: {str(e)}") from e
    
    async def generate_stream(
        self,
        model: Llama,
        prompt: str,
        settings: SamplerSettings
    ) -> AsyncIterator[str]:
        """Generate text with streaming (yields tokens as they're generated).
        
        Args:
            model: Loaded Llama model instance
            prompt: Input prompt
            settings: Sampler settings
        
        Yields:
            Generated text tokens
        """
        # Note: llama-cpp-python doesn't have native async streaming
        # We'll use a thread pool to run the sync streaming
        loop = asyncio.get_event_loop()
        
        def _stream_sync():
            """Synchronous streaming generator."""
            try:
                stream = model(
                    prompt,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    top_k=settings.top_k,
                    repeat_penalty=settings.repeat_penalty,
                    max_tokens=settings.max_tokens,
                    stop=["</s>", "\n\n\n"],
                    echo=False,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("text", "")
                        if delta:
                            yield delta
            except Exception as e:
                raise RuntimeError(f"Streaming generation failed: {str(e)}") from e
        
        # Run streaming in executor and yield results
        stream_gen = _stream_sync()
        while True:
            try:
                chunk = await loop.run_in_executor(None, lambda: next(stream_gen, None))
                if chunk is None:
                    break
                yield chunk
            except StopIteration:
                break
            except Exception as e:
                raise RuntimeError(f"Streaming error: {str(e)}") from e
    
    async def unload_model(self, model_path: str) -> bool:
        """Unload a model from memory.
        
        Args:
            model_path: Path to the model to unload
        
        Returns:
            True if model was unloaded, False if not found
        """
        abs_path = str(Path(model_path).resolve())
        
        async with self._lock:
            if abs_path in self.models:
                # llama-cpp-python models don't have explicit cleanup
                # Python GC will handle it
                del self.models[abs_path]
                return True
            return False
    
    def is_loaded(self, model_path: str) -> bool:
        """Check if a model is currently loaded.
        
        Args:
            model_path: Path to the model
        
        Returns:
            True if model is loaded, False otherwise
        """
        abs_path = str(Path(model_path).resolve())
        return abs_path in self.models
