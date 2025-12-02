"""Service for managing the llama-cpp-python server process from cloned repository."""
import asyncio
import logging
import subprocess
import sys
import time
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List
import aiohttp

from .config import settings

logger = logging.getLogger(__name__)


class LLMServerService:
    """Manages the llama-cpp-python server subprocess from cloned repository."""
    
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.host = "127.0.0.1"
        self.port = 8001  # Use 8001 to avoid conflict with backend (8000)
        self.current_model_path: Optional[str] = None
        self.startup_options: Dict[str, Any] = {}
        
        # Path to cloned llama-cpp-python repository
        # Calculate from config: services/llm/src/server.py -> parent(src) -> parent(llm) -> parent(services) -> parent(root)
        base_dir = Path(__file__).parent.parent.parent.parent
        self.repo_dir = base_dir / "external_services" / "llama-cpp-python"
        self.repo_venv = self.repo_dir / ".venv"
        
        # Determine Python executable from cloned repo venv
        if self.repo_venv.exists():
            venv_python = self.repo_venv / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
            if platform.system() == "Windows":
                venv_python = venv_python.with_suffix(".exe")
            if venv_python.exists():
                self.venv_python = str(venv_python)
            else:
                self.venv_python = sys.executable
        else:
            # Fallback to system Python if venv doesn't exist yet
            self.venv_python = sys.executable
        
    def is_running(self) -> bool:
        """Check if server is running."""
        return self.process is not None and self.process.returncode is None

    async def start_server(
        self, 
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 2048,
        n_batch: int = 512,
        n_threads: Optional[int] = None,
        use_mlock: bool = False,
        use_mmap: bool = True,
        flash_attn: bool = False,
        main_gpu: int = 0,
        tensor_split: Optional[List[float]] = None,
        n_cpu_moe: Optional[int] = None,
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None
    ) -> bool:
        """Start the LLM server with a specific model."""
        if self.is_running():
            logger.info("Stopping existing LLM server...")
            await self.stop_server()
        
        # Convert model_path to absolute path to ensure it works from any directory
        model_path = Path(model_path).resolve()
        if not model_path.exists():
            logger.error(f"Model file not found: {model_path}")
            return False
            
        self.current_model_path = str(model_path)
        self.startup_options = {
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
            "n_threads": n_threads,
            "use_mlock": use_mlock,
            "use_mmap": use_mmap,
            "flash_attn": flash_attn,
            "n_cpu_moe": n_cpu_moe,
            "cache_type_k": cache_type_k,
            "cache_type_v": cache_type_v
        }
        
        if n_threads:
            self.startup_options["n_threads"] = n_threads
            
        # Create config for the server
        # Use absolute path for model to ensure it works from any directory
        config = {
            "host": self.host,
            "port": self.port,
            "models": [
                {
                    "model": str(model_path),  # Absolute path
                    "model_alias": "current_model",
                    "n_gpu_layers": n_gpu_layers,
                    "n_ctx": n_ctx,
                    "n_batch": n_batch,
                    "n_threads": n_threads if n_threads else None,
                    "use_mlock": use_mlock,
                    "use_mmap": use_mmap,
                    "flash_attn": flash_attn,
                }
            ]
        }
        
        # Add MoE args if provided
        if n_cpu_moe is not None:
             config["models"][0]["n_cpu_moe"] = n_cpu_moe
             
        # Add cache types if provided
        if cache_type_k:
            config["models"][0]["cache_type_k"] = cache_type_k
        if cache_type_v:
            config["models"][0]["cache_type_v"] = cache_type_v
             
        # Add tensor split if provided
        if tensor_split:
            config["models"][0]["tensor_split"] = tensor_split
            
        # Add main gpu if provided
        if main_gpu != 0:
            config["models"][0]["main_gpu"] = main_gpu

        # Write config to temp file
        import json
        
        # Use a fixed path for config (in data directory, not model directory)
        # This keeps configs separate from models
        # Calculate data_dir from base_dir (services/llm/src/server.py -> parent(src) -> parent(llm) -> parent(services) -> parent(root))
        base_dir = Path(__file__).parent.parent.parent.parent
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        config_path = data_dir / "llm_server_config.json"
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write config file: {e}")
            return False
        
        # Build command to run from cloned repo directory
        cmd = [
            self.venv_python, "-m", "llama_cpp.server",
            "--config_file", str(config_path)
        ]

        logger.info(f"Starting LLM server from {self.repo_dir} with config: {config_path}")
        
        try:
            # Start process from cloned repo directory
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.repo_dir) if self.repo_dir.exists() else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            
            # Start log monitoring immediately to prevent buffer filling
            asyncio.create_task(self._monitor_logs())
            
            # Wait for server to be ready
            if await self._wait_for_server():
                logger.info(f"LLM Server started successfully on http://{self.host}:{self.port}")
                return True
            else:
                logger.error("LLM Server failed to start within timeout")
                await self.stop_server()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start LLM server: {e}", exc_info=True)
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
                logger.error(f"Error stopping server: {e}")
            
            self.process = None
            self.current_model_path = None
            logger.info("LLM server stopped")

    async def _wait_for_server(self, timeout: int = 120) -> bool:
        """Wait for server to respond to health check."""
        start_time = time.time()
        url = f"http://{self.host}:{self.port}/v1/models"
        
        while time.time() - start_time < timeout:
            if self.process.returncode is not None:
                logger.error(f"LLM server process died unexpectedly with code {self.process.returncode}")
                return False
                
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return True
                        else:
                            logger.debug(f"Server returned status {response.status}")
            except Exception as e:
                # Server not ready yet
                logger.debug(f"Server check failed: {e}")
                await asyncio.sleep(1)
                continue
                
        return False

    async def _monitor_logs(self):
        """Monitor server logs."""
        if not self.process:
            return
            
        async def log_stream(stream, prefix):
            while True:
                line = await stream.readline()
                if not line:
                    break
                try:
                    decoded = line.decode().strip()
                    if decoded:
                        logger.info(f"[{prefix}] {decoded}")
                except:
                    pass

        try:
            await asyncio.gather(
                log_stream(self.process.stdout, "LLM_OUT"),
                log_stream(self.process.stderr, "LLM_ERR")
            )
        except Exception as e:
            logger.error(f"Error monitoring logs: {e}")

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
