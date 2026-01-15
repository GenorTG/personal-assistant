"""LLM Server Manager for OpenAI-compatible server."""
import asyncio
import logging
import subprocess
import signal
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
import time
import threading

from ...config.settings import settings
from ...utils.request_logger import get_request_log_store

logger = logging.getLogger(__name__)


class LLMServerManager:
    """Manages the OpenAI-compatible llama-cpp-python server process."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.server_url: str = settings.llm_service_url
        self.server_port: int = 8001
        self.server_host: str = "127.0.0.1"
        self._model_path: Optional[str] = None
        self._server_config: Optional[Dict[str, Any]] = None
        self._last_error: Optional[str] = None
        self._subprocess_logs: List[str] = []
        self._log_reader_task: Optional[asyncio.Task] = None
        self._template_info: Optional[Dict[str, Any]] = None  # Store template info from /props
        self._available_flags: Optional[Dict[str, bool]] = None  # Cache available flags
        self._loading_lock = threading.Lock()  # Prevent concurrent model loading
        
    async def start_server(
        self,
        model_path: str,
        n_ctx: int = 8192,  # Increased from 4096 to ensure tools aren't truncated
        n_gpu_layers: int = 0,
        n_threads: Optional[int] = None,
        n_batch: Optional[int] = None,
        use_mmap: Optional[bool] = None,
        use_mlock: Optional[bool] = None,
        chat_format: Optional[str] = None,
        use_jinja: bool = False,
        chat_template_file: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Start the OpenAI-compatible server with the specified model.
        
        Args:
            model_path: Path to the model file
            n_ctx: Context window size
            n_gpu_layers: Number of GPU layers (0 = CPU only, -1 = all layers)
            n_threads: Number of threads (None = auto)
            n_batch: Batch size (None = auto)
            use_mmap: Use memory mapping
            use_mlock: Lock memory pages
            chat_format: Chat format to use (e.g., "functionary-v2", "chatml-function-calling")
            use_jinja: Whether to enable jinja template support (for function calling)
            chat_template_file: Path to a custom chat template .jinja file
            **kwargs: Additional server parameters
            
        Returns:
            True if server started successfully, False otherwise
        """
        # Prevent concurrent model loading (spam protection)
        if not self._loading_lock.acquire(blocking=False):
            logger.warning("Model loading already in progress, ignoring duplicate request")
            return False
        
        try:
            # CRITICAL: Check for and kill any zombie processes on port 8001
            await self._cleanup_port_conflicts()
            
            # Also cleanup any orphaned llama-cpp-python processes
            await self._cleanup_all_llm_processes()
            
            if self.process is not None:
                logger.warning("Server is already running, stopping it first")
                await self.stop_server()
            
            self._model_path = model_path
            self._server_config = {
                "n_ctx": n_ctx,
                "n_gpu_layers": n_gpu_layers,
                "n_threads": n_threads or settings.llm_n_threads,
                "n_batch": n_batch,
                "use_mmap": use_mmap,
                "use_mlock": use_mlock,
                **kwargs
            }
            
            # Ensure model_path is absolute
            model_path_abs = Path(model_path).resolve()
            if not model_path_abs.exists():
                raise FileNotFoundError(f"Model file does not exist: {model_path_abs}")
            
            # Build server command - use minimal parameters for chatml-function-calling (matching working test)
            # For chatml-function-calling, use the exact working command format
            if chat_format == "chatml-function-calling":
                # Minimal command matching working manual test
                cmd = [
                    sys.executable,
                    "-m",
                    "llama_cpp.server",
                    "--model", str(model_path_abs),
                    "--host", self.server_host,
                    "--port", str(self.server_port),
                    "--n_ctx", str(n_ctx),
                    "--n_gpu_layers", str(n_gpu_layers),
                    "--chat_format", "chatml-function-calling"
                ]
                logger.info("Using minimal server command for chatml-function-calling (matching working test)")
            else:
                # Full command for other formats
                cmd = [
                    sys.executable,
                    "-m",
                    "llama_cpp.server",
                    "--model", str(model_path_abs),
                    "--host", self.server_host,
                    "--port", str(self.server_port),
                    "--n_ctx", str(n_ctx),
                    "--n_gpu_layers", str(n_gpu_layers),
                ]
                
                # Add optional parameters for non-chatml-function-calling formats
                if n_threads is not None:
                    cmd.extend(["--n_threads", str(n_threads)])
                if n_batch is not None:
                    cmd.extend(["--n_batch", str(n_batch)])
                if use_mmap is not None:
                    cmd.extend(["--use_mmap", "true" if use_mmap else "false"])
                if use_mlock is not None:
                    cmd.extend(["--use_mlock", "true" if use_mlock else "false"])
            # Only add chat_format if explicitly provided (not None and not empty string)
            # Some chat formats (like functionary-v2) require external tokenizers which GGUF repos don't have
            # For GGUF files, we skip chat_format to use the embedded tokenizer
            
            # For non-chatml-function-calling formats, add chat_format here
            if chat_format != "chatml-function-calling":
                # CRITICAL: Never allow 'llama-3.2' or 'llama-3.1' - only 'llama-3' is supported by llama-cpp-python
                if chat_format and ("llama-3.2" in str(chat_format) or "llama-3.1" in str(chat_format)):
                    logger.error(f"[FIX] Invalid chat_format '{chat_format}' detected - forcing to 'llama-3'")
                    chat_format = "llama-3"
                
                if chat_format is not None and str(chat_format).strip():
                    cmd.extend(["--chat_format", str(chat_format)])
                    logger.info(f"Setting chat_format to: {chat_format}")
                else:
                    # Explicitly don't pass chat_format - let model use embedded tokenizer
                    logger.info("No chat_format specified - model will use default/embedded tokenizer from GGUF file")
            
            # Check available flags for jinja/template support
            available_flags = self._check_available_flags()
            
            # CRITICAL: For chatml-function-calling format, do NOT add jinja flags or template files
            # The format handles tool calling automatically without these flags
            # Only add jinja/template for other formats that need them
            if chat_format == "chatml-function-calling":
                # chatml-function-calling doesn't need jinja or template files
                logger.info("Using chatml-function-calling format - tool calling enabled automatically (no jinja/template needed)")
            else:
                # For other formats, add jinja flag if requested
                if use_jinja:
                    available_flags = self._check_available_flags()
                    if available_flags.get("jinja", False):
                        cmd.append("--jinja")
                        logger.info("✓ Added --jinja flag for function calling support")
                    else:
                        logger.info("⚠ --jinja flag not available in Python wrapper")
                
                # Add chat template file if provided (for non-chatml-function-calling formats)
                if chat_template_file:
                    template_file_path = Path(chat_template_file)
                    if template_file_path.exists():
                        available_flags = self._check_available_flags()
                        if available_flags.get("chat-template-file", False):
                            cmd.extend(["--chat-template-file", str(template_file_path)])
                            logger.info(f"✓ Using custom chat template file: {template_file_path}")
                        elif available_flags.get("chat_template_file", False):
                            cmd.extend(["--chat_template_file", str(template_file_path)])
                            logger.info(f"✓ Using custom chat template file: {template_file_path}")
                        else:
                            logger.warning(f"⚠ --chat-template-file flag not available in Python wrapper")
                    else:
                        logger.warning(f"⚠ Chat template file does not exist: {template_file_path}")
            
            # Add HuggingFace tokenizer path if provided
            # Note: For GGUF files, tokenizer is usually embedded, so this is typically not needed
            # Only use if explicitly required by the model
            if "hf_pretrained_model_name_or_path" in kwargs and kwargs["hf_pretrained_model_name_or_path"]:
                cmd.extend(["--hf_pretrained_model_name_or_path", str(kwargs["hf_pretrained_model_name_or_path"])])
                logger.info(f"Using HuggingFace tokenizer from: {kwargs['hf_pretrained_model_name_or_path']}")
            # For GGUF files without explicit tokenizer path, llama-cpp-python will use embedded tokenizer
            
            # Add any additional kwargs that are valid server parameters
            # For chatml-function-calling, skip extra parameters to match working test
            if chat_format != "chatml-function-calling":
                valid_params = {
                    "rope_freq_base", "rope_freq_scale", "main_gpu", "tensor_split",
                    "flash_attn", "cache_type_k", "cache_type_v"
                }
                for key, value in kwargs.items():
                    if key in valid_params and value is not None:
                        if isinstance(value, bool):
                            if value:
                                cmd.append(f"--{key}")
                        else:
                            cmd.extend([f"--{key}", str(value)])
            
            logger.info(f"Starting OpenAI-compatible server: {' '.join(cmd)}")
            
            try:
                # Start server process
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    env=env,
                    cwd=str(Path(__file__).parent.parent.parent.parent.parent),
                    text=True,
                    bufsize=1
                )
                
                # Start reading subprocess output
                self._subprocess_logs = []
                self._log_reader_task = asyncio.create_task(self._read_subprocess_output())
                
                # Wait for server to be ready
                logger.info(f"[MODEL LOAD] Waiting for server to start on {self.server_url}...")
                logger.info(f"[MODEL LOAD] Model: {model_path_abs.name}")
                logger.info(f"[MODEL LOAD] Command: {' '.join(cmd)}")
                
                # Reasonable timeout based on model size (larger models take longer)
                # Small models (<5GB): 15s, Medium (5-15GB): 30s, Large (>15GB): 45s
                model_size_gb = model_path_abs.stat().st_size / (1024**3)
                if model_size_gb < 5:
                    max_wait = 15
                elif model_size_gb < 15:
                    max_wait = 30
                else:
                    max_wait = 45
                wait_interval = 0.5  # Check every 0.5 seconds for faster response
                elapsed = 0
                logger.info(f"[MODEL LOAD] Timeout: {max_wait}s (model size: {model_size_gb:.2f}GB)")
                
                while elapsed < max_wait:
                    if self.process.poll() is not None:
                        # Process has terminated - cancel log reader and get remaining output
                        if self._log_reader_task:
                            self._log_reader_task.cancel()
                            try:
                                await self._log_reader_task
                            except asyncio.CancelledError:
                                pass
                        
                        # Get any remaining output
                        try:
                            remaining_output, _ = self.process.communicate(timeout=1)
                            if remaining_output:
                                error_output = remaining_output if isinstance(remaining_output, str) else remaining_output.decode('utf-8', errors='ignore')
                            else:
                                error_output = '\n'.join(self._subprocess_logs) if self._subprocess_logs else ""
                        except Exception:
                            error_output = '\n'.join(self._subprocess_logs) if self._subprocess_logs else ""
                        
                        logger.error(f"Server process exited with code {self.process.returncode}")
                        logger.error(f"Output: {error_output}")
                        self.process = None
                        # Store error for retrieval
                        self._last_error = f"Server failed to start: {error_output}"
                        return False
                    
                    # Check if server is responding (use /v1/models as health check)
                    try:
                        async with httpx.AsyncClient(timeout=1.0) as client:  # Reduced from 2.0 to 1.0
                            response = await client.get(f"{self.server_url}/v1/models")
                            if response.status_code == 200:
                                logger.info(f"[MODEL LOAD] ✓ Server is ready at {self.server_url} (took {elapsed:.1f}s)")
                                # Verify template support after server is ready
                                if use_jinja or chat_template_file:
                                    await self._verify_template_support()
                                return True
                    except Exception as e:
                        # Log only every 2 seconds to avoid spam
                        if int(elapsed) % 2 == 0 and elapsed > 0:
                            logger.debug(f"[MODEL LOAD] Server not ready yet... ({elapsed:.1f}s)")
                    
                    await asyncio.sleep(wait_interval)
                    elapsed += wait_interval
                    if int(elapsed) % 5 == 0 and elapsed > 0:
                        logger.info(f"[MODEL LOAD] Still waiting for server... ({elapsed:.1f}s / {max_wait}s)")
                
                # Get error output from logs
                error_output = '\n'.join(self._subprocess_logs[-20:]) if self._subprocess_logs else "No output captured"
                logger.error(f"[MODEL LOAD] ❌ Server failed to start within {max_wait}s")
                logger.error(f"[MODEL LOAD] Last 20 log lines:\n{error_output}")
                self._last_error = f"Server failed to start within {max_wait} seconds. Last error: {error_output[-200:]}"
                await self.stop_server()
                return False
                
            except Exception as e:
                    error_msg = f"Failed to start server: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    self._last_error = error_msg
                    if self.process:
                        await self.stop_server()
                    return False
        except Exception as e:
            # Handle any errors from cleanup or path validation
            error_msg = f"Failed to start server: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._last_error = error_msg
            if self.process:
                await self.stop_server()
            return False
        finally:
            # Always release the lock
            self._loading_lock.release()
    
    async def stop_server(self) -> bool:
        """Stop the OpenAI-compatible server.
        
        Returns:
            True if server stopped successfully, False otherwise
        """
        if self.process is None:
            return True
        
        logger.info("Stopping OpenAI-compatible server...")
        
        # Cancel log reader task
        if self._log_reader_task:
            self._log_reader_task.cancel()
            try:
                await self._log_reader_task
            except asyncio.CancelledError:
                pass
            self._log_reader_task = None
        
        try:
            # Try graceful shutdown first
            self.process.terminate()
            
            # Wait up to 10 seconds for graceful shutdown
            try:
                self.process.wait(timeout=10)
                logger.info("✓ Server stopped gracefully")
                self.process = None
                self._model_path = None
                self._server_config = None
                self._subprocess_logs = []
                return True
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                logger.warning("Server did not stop gracefully, forcing kill...")
                self.process.kill()
                self.process.wait()
                logger.info("✓ Server force-killed")
                self.process = None
                self._model_path = None
                self._server_config = None
                self._subprocess_logs = []
                return True
                
        except Exception as e:
            logger.error(f"Error stopping server: {e}", exc_info=True)
            if self.process:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            self._model_path = None
            self._server_config = None
            self._subprocess_logs = []
            return False
    
    async def _cleanup_port_conflicts(self):
        """Check for and kill any processes using port 8001."""
        try:
            import psutil
            logger.info(f"[CLEANUP] Checking for processes on port {self.server_port}...")
            killed_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check if process is listening on our port
                    connections = proc.connections()
                    for conn in connections:
                        if conn.status == psutil.CONN_LISTEN and conn.laddr.port == self.server_port:
                            if proc.pid != os.getpid():  # Don't kill ourselves
                                logger.warning(f"[CLEANUP] Found zombie process {proc.pid} ({proc.name()}) using port {self.server_port}")
                                logger.warning(f"[CLEANUP] Cmdline: {' '.join(proc.info.get('cmdline', []))}")
                                try:
                                    proc.terminate()
                                    try:
                                        proc.wait(timeout=2)
                                        logger.info(f"[CLEANUP] ✓ Terminated process {proc.pid} gracefully")
                                    except psutil.TimeoutExpired:
                                        proc.kill()
                                        proc.wait(timeout=1)
                                        logger.info(f"[CLEANUP] ✓ Force-killed process {proc.pid}")
                                    killed_count += 1
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            if killed_count > 0:
                logger.info(f"[CLEANUP] ✓ Cleaned up {killed_count} zombie process(es)")
            else:
                logger.debug(f"[CLEANUP] No conflicts found on port {self.server_port}")
        except ImportError:
            logger.warning("[CLEANUP] psutil not available, skipping port conflict check")
        except Exception as e:
            logger.warning(f"[CLEANUP] Error checking for port conflicts: {e}")
    
    async def _cleanup_all_llm_processes(self):
        """Cleanup all orphaned llama-cpp-python server processes by command line pattern."""
        try:
            import psutil
            logger.info("[CLEANUP] Checking for orphaned llama-cpp-python processes...")
            killed_count = 0
            current_pid = os.getpid()
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.pid == current_pid:
                        continue  # Don't kill ourselves
                    
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue
                    
                    # Check if this is a llama-cpp-python server process
                    cmdline_str = ' '.join(cmdline)
                    is_llm_server = (
                        'llama_cpp.server' in cmdline_str or
                        'llama-cpp-python' in cmdline_str.lower() or
                        (sys.executable in cmdline and 'server' in cmdline_str and '--port' in cmdline_str)
                    )
                    
                    # Also check if it's using our port
                    is_our_port = False
                    try:
                        connections = proc.connections()
                        for conn in connections:
                            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == self.server_port:
                                is_our_port = True
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    
                    if is_llm_server or is_our_port:
                        logger.warning(f"[CLEANUP] Found orphaned LLM server process {proc.pid}")
                        logger.warning(f"[CLEANUP] Cmdline: {cmdline_str}")
                        try:
                            proc.terminate()
                            try:
                                proc.wait(timeout=2)
                                logger.info(f"[CLEANUP] ✓ Terminated process {proc.pid} gracefully")
                            except psutil.TimeoutExpired:
                                proc.kill()
                                proc.wait(timeout=1)
                                logger.info(f"[CLEANUP] ✓ Force-killed process {proc.pid}")
                            killed_count += 1
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if killed_count > 0:
                logger.info(f"[CLEANUP] ✓ Cleaned up {killed_count} orphaned LLM server process(es)")
            else:
                logger.debug("[CLEANUP] No orphaned LLM processes found")
        except ImportError:
            logger.warning("[CLEANUP] psutil not available, skipping LLM process cleanup")
        except Exception as e:
            logger.warning(f"[CLEANUP] Error cleaning up LLM processes: {e}")
    
    def is_running(self) -> bool:
        """Check if the server is running.
        
        Returns:
            True if server process is running, False otherwise
        """
        if self.process is None:
            return False
        return self.process.poll() is None
    
    async def health_check(self) -> bool:
        """Check if the server is healthy (responding to requests).
        
        Returns:
            True if server is healthy, False otherwise
        """
        if not self.is_running():
            return False
        
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:  # Reduced from 2.0 to 1.0
                # Use /v1/models as health check (llama-cpp-python doesn't have /health endpoint)
                response = await client.get(f"{self.server_url}/v1/models")
                return response.status_code == 200
        except Exception:
            return False
    
    def get_server_url(self) -> str:
        """Get the server URL.
        
        Returns:
            Server URL string
        """
        return self.server_url
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message from server startup.
        
        Returns:
            Error message string or None if no error
        """
        return self._last_error
    
    def _check_available_flags(self) -> Dict[str, bool]:
        """Check which flags are available in llama-cpp-python server.
        
        Returns:
            Dictionary mapping flag names to availability (True/False)
        """
        if self._available_flags is not None:
            return self._available_flags
        
        flags_to_check = {
            "jinja": False,
            "chat_template_file": False,
            "chat-template-file": False,
        }
        
        try:
            # Run help command to check available flags
            result = subprocess.run(
                [sys.executable, "-m", "llama_cpp.server", "--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            help_text = result.stdout.lower() + result.stderr.lower()
            
            # Check for jinja flag
            if "--jinja" in help_text or "jinja" in help_text:
                flags_to_check["jinja"] = True
                logger.info("✓ --jinja flag is available")
            else:
                logger.debug("--jinja flag not found in server help")
            
            # Check for chat template file flags (try both formats)
            if "--chat-template-file" in help_text or "chat-template-file" in help_text:
                flags_to_check["chat-template-file"] = True
                logger.info("✓ --chat-template-file flag is available")
            elif "--chat_template_file" in help_text or "chat_template_file" in help_text:
                flags_to_check["chat_template_file"] = True
                logger.info("✓ --chat_template_file flag is available")
            else:
                logger.debug("--chat-template-file flag not found in server help")
                
        except Exception as e:
            logger.warning(f"Could not check available flags: {e}")
        
        self._available_flags = flags_to_check
        return flags_to_check
    
    async def _verify_template_support(self) -> Optional[Dict[str, Any]]:
        """Verify template support by querying /props endpoint.
        
        Returns:
            Dictionary with template info (chat_template, chat_template_tool_use) or None if unavailable
        """
        if not self.is_running():
            logger.warning("Cannot verify template support: server is not running")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.server_url}/props")
                if response.status_code == 200:
                    props_data = response.json()
                    
                    template_info = {
                        "chat_template": props_data.get("chat_template"),
                        "chat_template_tool_use": props_data.get("chat_template_tool_use"),
                        "has_tool_use_template": bool(props_data.get("chat_template_tool_use")),
                        "has_standard_template": bool(props_data.get("chat_template")),
                    }
                    
                    self._template_info = template_info
                    
                    if template_info["has_tool_use_template"]:
                        logger.info("✓ Template verification: Tool-use template is available")
                    elif template_info["has_standard_template"]:
                        logger.info("✓ Template verification: Standard template is available (tool-use template not found)")
                    else:
                        logger.warning("⚠ Template verification: No templates found in /props")
                    
                    return template_info
                else:
                    logger.warning(f"Failed to get /props: status {response.status_code}")
                    return None
        except Exception as e:
            logger.warning(f"Error verifying template support: {e}")
            return None
    
    def get_template_info(self) -> Optional[Dict[str, Any]]:
        """Get cached template info from last verification.
        
        Returns:
            Template info dictionary or None if not verified yet
        """
        return self._template_info
    
    async def _read_subprocess_output(self):
        """Read subprocess output and add to request logs."""
        if not self.process or not self.process.stdout:
            return
        
        try:
            while self.process.poll() is None:
                line = await asyncio.to_thread(self.process.stdout.readline)
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                # Store in subprocess logs
                self._subprocess_logs.append(line)
                
                # Determine log level from content
                level = "INFO"
                line_lower = line.lower()
                if "error" in line_lower or "failed" in line_lower or "exception" in line_lower or "traceback" in line_lower:
                    level = "ERROR"
                elif "warning" in line_lower or "warn" in line_lower:
                    level = "WARNING"
                elif "debug" in line_lower:
                    level = "DEBUG"
                
                # Add to request log store if available
                log_store = get_request_log_store()
                if log_store:
                    log_store.add_log(
                        level=level,
                        logger_name="llm_server",
                        message=line
                    )
                
                # Also log to standard logger
                if level == "ERROR":
                    logger.error(f"[LLM SERVER] {line}")
                elif level == "WARNING":
                    logger.warning(f"[LLM SERVER] {line}")
                else:
                    logger.debug(f"[LLM SERVER] {line}")
        except asyncio.CancelledError:
            # Task was cancelled, this is expected
            pass
        except Exception as e:
            logger.error(f"Error reading subprocess output: {e}", exc_info=True)

