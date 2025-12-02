"""Service for managing the llama-cpp-python server process."""
import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import aiohttp

from ...config.settings import settings

logger = logging.getLogger(__name__)


class LLMServerService:
    """Manages the llama-cpp-python server subprocess.
    
    The llama-cpp-python server is started with a config file that specifies
    model loading parameters. This service manages the server lifecycle.
    """
    
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.host = "127.0.0.1"
        self.port = 8001  # Use 8001 to avoid conflict with backend (8000)
        self.current_model_path: Optional[str] = None
        self.startup_options: Dict[str, Any] = {}
        # Use LLM service's Python interpreter (where llama-cpp-python is installed)
        self.venv_python = self._get_llm_python()
    
    def _get_llm_python(self) -> str:
        """Get the Python interpreter from the LLM service's venv."""
        import sys
        from pathlib import Path
        
        # Get project root from settings
        llm_venv_dir = settings.base_dir / "services" / "llm" / ".venv"
        
        # Determine Python executable path based on platform
        if sys.platform == "win32":
            python_exe = llm_venv_dir / "Scripts" / "python.exe"
        else:
            python_exe = llm_venv_dir / "bin" / "python"
        
        # Check if it exists, fallback to sys.executable if not
        if python_exe.exists():
            logger.info("Using LLM service Python: %s", python_exe)
            return str(python_exe)
        else:
            logger.warning(
                "LLM service venv not found at %s, falling back to gateway Python: %s. "
                "Please ensure the LLM service is installed.",
                llm_venv_dir, sys.executable
            )
            return sys.executable
        
    def is_running(self) -> bool:
        """Check if server is running."""
        return self.process is not None and self.process.returncode is None

    async def start_server(
        self, 
        model_path: str,
        # GPU settings
        n_gpu_layers: int = -1,
        main_gpu: int = 0,
        tensor_split: Optional[List[float]] = None,
        # Context/batch settings
        n_ctx: int = 4096,
        n_batch: int = 512,
        n_threads: Optional[int] = None,
        n_threads_batch: Optional[int] = None,
        # Memory settings
        use_mlock: bool = False,
        use_mmap: bool = True,
        # Performance settings
        flash_attn: bool = False,
        # RoPE settings
        rope_freq_base: Optional[float] = None,
        rope_freq_scale: Optional[float] = None,
        rope_scaling_type: Optional[int] = None,
        yarn_ext_factor: Optional[float] = None,
        yarn_attn_factor: Optional[float] = None,
        yarn_beta_fast: Optional[float] = None,
        yarn_beta_slow: Optional[float] = None,
        yarn_orig_ctx: Optional[int] = None,
        # KV cache settings
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None,
        # MoE settings
        n_cpu_moe: Optional[int] = None,
    ) -> bool:
        """Start the LLM server with a specific model.
        
        Args:
            model_path: Path to the GGUF model file
            n_gpu_layers: Number of layers to offload to GPU (-1 = all, 0 = CPU only)
            main_gpu: Main GPU device ID for multi-GPU setups
            tensor_split: How to split model across GPUs (e.g., [0.5, 0.5])
            n_ctx: Context window size
            n_batch: Batch size for prompt processing
            n_threads: Number of CPU threads for inference
            n_threads_batch: Number of threads for batch processing
            use_mlock: Lock model in memory (prevents swapping)
            use_mmap: Use memory-mapped files for model loading
            flash_attn: Enable Flash Attention (requires compatible hardware)
            rope_freq_base: RoPE frequency base for context extension
            rope_freq_scale: RoPE frequency scale for context extension
            rope_scaling_type: RoPE scaling type (-1=unspecified, 0=none, 1=linear, 2=yarn)
            yarn_*: YaRN context extension parameters
            cache_type_k: KV cache data type for K (f16, q8_0, q4_0, etc.)
            cache_type_v: KV cache data type for V (f16, q8_0, q4_0, etc.)
            n_cpu_moe: Number of CPU threads for MoE experts (for Mixture of Experts models)
            
        Returns:
            True if server started successfully, False otherwise
        """
        if self.is_running():
            logger.info("Stopping existing LLM server...")
            await self.stop_server()
            
        self.current_model_path = model_path
        
        # Store startup options for status reporting
        self.startup_options = {
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
            "n_threads": n_threads,
            "use_mlock": use_mlock,
            "use_mmap": use_mmap,
            "flash_attn": flash_attn,
            "cache_type_k": cache_type_k,
            "cache_type_v": cache_type_v,
        }
        
        # Build model config for llama-cpp-python server
        # Only include parameters that are set (non-None) and non-default
        model_config: Dict[str, Any] = {
            "model": model_path,
            "model_alias": "default",
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
        }
        
        # Add optional parameters only if specified
        if n_threads is not None:
            model_config["n_threads"] = n_threads
        if n_threads_batch is not None:
            model_config["n_threads_batch"] = n_threads_batch
        if use_mlock:
            model_config["use_mlock"] = use_mlock
        if not use_mmap:  # Default is True, only set if False
            model_config["use_mmap"] = use_mmap
        if flash_attn:
            model_config["flash_attn"] = flash_attn
        if main_gpu != 0:
            model_config["main_gpu"] = main_gpu
        if tensor_split:
            model_config["tensor_split"] = tensor_split
            
        # RoPE settings
        if rope_freq_base is not None:
            model_config["rope_freq_base"] = rope_freq_base
        if rope_freq_scale is not None:
            model_config["rope_freq_scale"] = rope_freq_scale
        if rope_scaling_type is not None:
            model_config["rope_scaling_type"] = rope_scaling_type
            
        # YaRN settings
        if yarn_ext_factor is not None:
            model_config["yarn_ext_factor"] = yarn_ext_factor
        if yarn_attn_factor is not None:
            model_config["yarn_attn_factor"] = yarn_attn_factor
        if yarn_beta_fast is not None:
            model_config["yarn_beta_fast"] = yarn_beta_fast
        if yarn_beta_slow is not None:
            model_config["yarn_beta_slow"] = yarn_beta_slow
        if yarn_orig_ctx is not None:
            model_config["yarn_orig_ctx"] = yarn_orig_ctx
            
        # KV cache settings
        if cache_type_k and cache_type_k != "f16":
            model_config["cache_type_k"] = cache_type_k
        if cache_type_v and cache_type_v != "f16":
            model_config["cache_type_v"] = cache_type_v
            
        # MoE settings
        if n_cpu_moe is not None:
            model_config["n_cpu_moe"] = n_cpu_moe
            
        # Build server config
        config = {
            "host": self.host,
            "port": self.port,
            "models": [model_config]
        }

        # Write config to temp file
        import json
        
        # Use model directory for config file
        config_path = Path(model_path).parent / "server_config.json"
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            logger.info("Server config written to: %s", config_path)
            logger.info("Model config: %s", json.dumps(model_config, indent=2))
        except Exception as e:
            logger.error("Failed to write config file: %s", e)
            return False
            
        cmd = [
            self.venv_python, "-m", "llama_cpp.server",
            "--config_file", str(config_path)
        ]

        logger.info("Starting LLM server: %s", " ".join(cmd))
        
        try:
            # Start process - use CREATE_NO_WINDOW on Windows to avoid popup CMD windows
            if sys.platform == "win32":
                # CREATE_NO_WINDOW (0x08000000) prevents console window from appearing
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                creationflags = 0
            
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags
            )
            
            # Start log monitoring immediately to prevent buffer filling
            asyncio.create_task(self._monitor_logs())
            
            # Wait for server to be ready
            if await self._wait_for_server():
                logger.info("LLM Server started successfully on http://%s:%s", self.host, self.port)
                return True
            else:
                logger.error("LLM Server failed to start within timeout")
                await self.stop_server()
                return False
                
        except Exception as e:
            logger.error("Failed to start LLM server: %s", e, exc_info=True)
            await self.stop_server()
            return False

    async def stop_server(self):
        """Stop the LLM server."""
        if self.process:
            logger.info("Stopping LLM server...")
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("LLM server didn't stop gracefully, killing...")
                    self.process.kill()
                    await self.process.wait()
            except Exception as e:
                logger.error("Error stopping server: %s", e)
            
            self.process = None
            self.current_model_path = None
            logger.info("LLM server stopped")

    async def _wait_for_server(self, timeout: int = 120) -> bool:
        """Wait for server to respond to health check."""
        start_time = time.time()
        url = f"http://{self.host}:{self.port}/v1/models"
        
        while time.time() - start_time < timeout:
            if self.process is None or self.process.returncode is not None:
                logger.error("LLM server process died unexpectedly with code %s", 
                           self.process.returncode if self.process else "N/A")
                return False
                
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            return True
                        logger.debug("Server returned status %s", response.status)
            except asyncio.TimeoutError:
                logger.debug("Health check timed out, retrying...")
            except Exception as e:
                # Server not ready yet
                logger.debug("Server check failed: %s", e)
            
            await asyncio.sleep(1)
                
        return False

    async def _monitor_logs(self):
        """Monitor server logs and forward to logger."""
        if not self.process:
            return
            
        async def log_stream(stream, prefix: str):
            while True:
                try:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode(errors='replace').strip()
                    if decoded:
                        logger.info("[%s] %s", prefix, decoded)
                except Exception:
                    break

        try:
            await asyncio.gather(
                log_stream(self.process.stdout, "LLM"),
                log_stream(self.process.stderr, "LLM")
            )
        except Exception as e:
            logger.error("Error monitoring logs: %s", e)

    def get_status(self) -> Dict[str, Any]:
        """Get server status."""
        return {
            "running": self.is_running(),
            "model": self.current_model_path,
            "port": self.port,
            "url": f"http://{self.host}:{self.port}/v1",
            "options": self.startup_options
        }


# Global instance
llm_server = LLMServerService()
