"""Chatterbox TTS API service manager."""
import os
import subprocess
import asyncio
import logging
import shutil
import collections
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# Optional import for psutil (used for process management)
try:
    import psutil
except ImportError:
    psutil = None

# Import extracted modules
from .chatterbox.python_finder import find_system_python, get_venv_python, find_python_exe
from .chatterbox.installation_checker import check_installation, check_dependencies_installed
from .chatterbox.cuda_detector import detect_cuda_and_get_pytorch_cmd, check_device_info
from .chatterbox.port_checker import check_port_available
from ...config.settings import settings

logger = logging.getLogger(__name__)

class ChatterboxServiceManager:
    """Manages the Chatterbox TTS API server process."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.api_url = "http://localhost:4123/v1"
        self.api_port = 4123
        self.frontend_port = 4321
        # Repo service lives at: <project root>/services/tts-chatterbox
        self.base_dir = settings.base_dir / "services" / "tts-chatterbox"
        # Prefer `.venv` but support `venv/` (this repo uses `venv/`)
        if (self.base_dir / ".venv").exists():
            self.venv_dir = self.base_dir / ".venv"
        else:
            self.venv_dir = self.base_dir / "venv"
        self.python_exe: Optional[str] = None
        self._status = "stopped"  # stopped, starting, running, stopping, error
        self._error_message: Optional[str] = None
        self._installing = False  # Flag to prevent concurrent installations
        self._install_lock = asyncio.Lock()  # Lock for installation operations
        self._logs = collections.deque(maxlen=1000)  # Store last 1000 log lines

    
    @property
    def status(self) -> str:
        """Get current service status."""
        if self.process is None:
            # If status was "running" but process is None, it means it crashed
            if self._status in ("running", "starting"):
                self._status = "error"
                self._error_message = "Process terminated unexpectedly"
            return "stopped" if self._status != "error" else "error"
        
        # Check if process is still running
        poll_result = self.process.poll()
        if poll_result is not None:
            # Process has terminated
            if self._status in ("running", "starting"):
                self._status = "error"
                self._error_message = f"Process terminated with exit code {poll_result}"
            else:
                self._status = "stopped"
            self.process = None
            return self._status
        
        # Process is alive, but verify it's actually responding if status is "running"
        if self._status == "running":
            # Do a quick health check to verify it's actually working
            try:
                import httpx
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't do sync check in async context, trust the process is running
                    return self._status
                else:
                    # Can do a quick sync check
                    with httpx.Client(timeout=1.0) as client:
                        response = client.get(f"{self.api_url.replace('/v1', '')}/health")
                        if response.status_code != 200:
                            # Process is alive but not responding
                            self._status = "error"
                            self._error_message = "Process is running but not responding to health checks"
                            return "error"
            except Exception:
                # Health check failed, but process is alive - might be initializing
                # Don't change status to error, just return current status
                pass
        
        return self._status
    
    @property
    def is_running(self) -> bool:
        """Check if service is running by checking both status and port availability."""
        # First check internal status
        if self.status != "running":
            # If status says not running, verify by checking port
            # This handles cases where service was started externally
            return self._check_port_available()
        
        # If status says running, verify port is actually accessible
        # This handles cases where process died but status wasn't updated
        if not self._check_port_available():
            # Port not available - update status
            self._status = "stopped"
            if self.process:
                try:
                    if self.process.poll() is not None:
                        # Process has exited
                        self.process = None
                except Exception:
                    pass
            return False
        
        return True
    
    def _check_port_available(self) -> bool:
        """Check if the service port is actually accessible."""
        return check_port_available(self.api_port)
    
    def _find_system_python(self) -> Optional[str]:
        """Find system Python executable (3.11+) for creating venv."""
        return find_system_python()
    
    def _get_venv_python(self) -> Optional[str]:
        """Get Python executable from Chatterbox venv."""
        return get_venv_python(self.venv_dir)
    
    def _find_python_exe(self) -> Optional[str]:
        """Find Python executable for Chatterbox - prefer venv, fallback to system."""
        return find_python_exe(self.venv_dir)
    
    def _check_installation(self) -> bool:
        """Check if Chatterbox TTS API is installed."""
        return check_installation(self.base_dir)
    
    def _check_dependencies_installed(self) -> bool:
        """Check if dependencies are installed in shared venv."""
        venv_python = self._get_venv_python()
        return check_dependencies_installed(venv_python)

    
    async def _ensure_venv(self) -> bool:
        """Ensure service venv exists."""
        if not self.venv_dir.exists():
            # Try alternate venv folder name
            alt = (self.base_dir / "venv") if self.venv_dir.name == ".venv" else (self.base_dir / ".venv")
            if alt.exists():
                self.venv_dir = alt
            else:
                logger.error(
                    "Service venv not found at %s (or %s). Install the service via the launcher.",
                    str(self.base_dir / ".venv"),
                    str(self.base_dir / "venv"),
                )
            return False
        
        logger.info("Using service venv at: %s", str(self.venv_dir))
        return True

    
    def _detect_cuda_and_get_pytorch_cmd(self, venv_python: str) -> Tuple[bool, Optional[List[str]]]:
        """
        Detect CUDA availability and return appropriate PyTorch installation command.
        Returns: (has_cuda, pytorch_install_cmd or None)
        """
        try:
            # Try to detect CUDA using nvidia-smi (most reliable method)
            nvidia_smi = shutil.which("nvidia-smi")
            if nvidia_smi:
                result = subprocess.run(
                    [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_name = result.stdout.strip().split('\n')[0]
                    logger.info("CUDA GPU detected: %s", gpu_name)
                    
                    # Try to detect CUDA version
                    cuda_version_result = subprocess.run(
                        [nvidia_smi, "--query-gpu=driver_version", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    driver_version = cuda_version_result.stdout.strip().split('\n')[0] if cuda_version_result.returncode == 0 else "unknown"
                    logger.info("NVIDIA Driver version: %s", driver_version)
                    
                    # Determine CUDA version for PyTorch
                    # CUDA 12.x -> use cu121
                    # CUDA 11.8 -> use cu118
                    # Default to cu121 (most common)
                    cuda_index = "https://download.pytorch.org/whl/cu121"
                    
                    # Try to get CUDA runtime version if nvcc is available
                    nvcc = shutil.which("nvcc")
                    if nvcc:
                        nvcc_result = subprocess.run(
                            [nvcc, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if nvcc_result.returncode == 0:
                            # Parse CUDA version from nvcc output
                            for line in nvcc_result.stdout.split('\n'):
                                if 'release' in line.lower():
                                    # Extract version like "12.1" or "11.8"
                                    import re
                                    match = re.search(r'release\s+(\d+)\.(\d+)', line, re.IGNORECASE)
                                    if match:
                                        major, minor = match.groups()
                                        if major == "12":
                                            cuda_index = "https://download.pytorch.org/whl/cu121"
                                        elif major == "11" and minor == "8":
                                            cuda_index = "https://download.pytorch.org/whl/cu118"
                                        logger.info("Detected CUDA runtime version: %s.%s", major, minor)
                    
                    # Build PyTorch installation command with CUDA support
                    pytorch_cmd = [
                        venv_python, "-m", "pip", "install",
                        "torch>=2.0.0,<2.7.0",
                        "torchaudio>=2.0.0,<2.7.0",
                        "--index-url", cuda_index
                    ]
                    return True, pytorch_cmd
        except Exception as e:
            logger.debug("CUDA detection error (non-fatal): %s", str(e))
        
        # No CUDA detected, will use CPU version from requirements.txt
        logger.info("No CUDA GPU detected, will install CPU-only PyTorch")
        return False, None
    
    async def _install_dependencies(self) -> bool:
        """Install dependencies for Chatterbox TTS API in its venv."""
        # Use lock to prevent concurrent installations
        async with self._install_lock:
            # Check if already installing
            if self._installing:
                logger.warning("Installation already in progress, waiting...")
                # Wait for current installation to complete
                max_wait = 60  # Wait up to 60 seconds
                waited = 0
                while self._installing and waited < max_wait:
                    await asyncio.sleep(2)
                    waited += 2
                if self._installing:
                    logger.error("Installation timeout - another process may be stuck")
                    return False
                # Check if dependencies are now installed
                if self._check_dependencies_installed():
                    logger.info("Dependencies installed by concurrent process")
                    return True
            
            # Mark as installing
            self._installing = True
            
            try:
                # Ensure venv exists
                if not await self._ensure_venv():
                    return False
                
                # Get venv Python
                venv_python = self._get_venv_python()
                if not venv_python:
                    logger.error("Chatterbox venv Python not found")
                    return False
                
                logger.info("Using Chatterbox venv Python: %s", venv_python)
                self._logs.append(f"Using Chatterbox venv Python: {venv_python}")
                
                loop = asyncio.get_event_loop()
                
                async def _install():
                    max_retries = 3
                    retry_delay = 5
                    
                    for attempt in range(max_retries):
                        try:
                            # First, upgrade pip, setuptools, and wheel
                            logger.info("Upgrading pip, setuptools, and wheel in venv...")
                            self._logs.append("Upgrading pip, setuptools, and wheel in venv...")
                            
                            upgrade_cmd = [venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
                            returncode, _, stderr = await self._run_command(
                                upgrade_cmd,
                                cwd=str(self.base_dir)
                            )
                            
                            if returncode != 0:
                                logger.warning("Failed to upgrade pip tools: %s", stderr[:200] if stderr else "Unknown")
                            else:
                                logger.info("pip tools upgraded successfully")
                            
                            # Detect CUDA and install PyTorch with CUDA support if available
                            has_cuda, pytorch_cmd = self._detect_cuda_and_get_pytorch_cmd(venv_python)
                            pytorch_installed_with_cuda = False
                            
                            if has_cuda and pytorch_cmd:
                                # Check if PyTorch is already installed and if it has CUDA support
                                logger.info("Checking for existing PyTorch installation...")
                                self._logs.append("Checking for existing PyTorch installation...")
                                
                                verify_cuda_cmd = [venv_python, "-c", "import torch; print('VERSION:', torch.__version__); print('CUDA:', torch.cuda.is_available())"]
                                returncode, stdout, _ = await self._run_command(
                                    verify_cuda_cmd,
                                    timeout=10
                                )
                                
                                if returncode == 0:
                                    output = stdout.strip()
                                    # Check if CUDA is available
                                    if "CUDA: True" in output:
                                        # Extract version
                                        version_line = [line for line in output.split('\n') if 'VERSION:' in line]
                                        if version_line:
                                            version = version_line[0].split('VERSION:')[1].strip()
                                            logger.info("PyTorch with CUDA support is already installed: %s", version)
                                            self._logs.append(f"PyTorch with CUDA support is already installed: {version}")
                                            pytorch_installed_with_cuda = True
                                    else:
                                        # CPU-only version detected, uninstall it
                                        version_line = [line for line in output.split('\n') if 'VERSION:' in line]
                                        if version_line:
                                            version = version_line[0].split('VERSION:')[1].strip()
                                            logger.info("Found CPU-only PyTorch: %s", version)
                                            logger.info("Uninstalling CPU-only PyTorch to install CUDA version...")
                                            self._logs.append("Uninstalling CPU-only PyTorch to install CUDA version...")
                                            
                                            uninstall_cmd = [venv_python, "-m", "pip", "uninstall", "torch", "torchaudio", "-y"]
                                            await self._run_command(
                                                uninstall_cmd,
                                                cwd=str(self.base_dir)
                                            )
                                
                                # Install CUDA version if not already installed
                                if not pytorch_installed_with_cuda:
                                    logger.info("Installing PyTorch with CUDA support...")
                                    logger.info("Running: %s", " ".join(pytorch_cmd))
                                    self._logs.append("Installing PyTorch with CUDA support...")
                                    
                                    returncode, _, stderr = await self._run_command(
                                        pytorch_cmd,
                                        timeout=1800,  # 30 minutes
                                        cwd=str(self.base_dir)
                                    )
                                    
                                    if returncode == 0:
                                        # Verify CUDA installation
                                        verify_cmd = [venv_python, "-c", "import torch; print('CUDA:', torch.cuda.is_available())"]
                                        returncode, stdout, _ = await self._run_command(
                                            verify_cmd,
                                            timeout=10
                                        )
                                        
                                        if returncode == 0 and "CUDA: True" in stdout:
                                            logger.info("PyTorch with CUDA support installed and verified successfully")
                                            self._logs.append("PyTorch with CUDA support installed and verified successfully")
                                            pytorch_installed_with_cuda = True
                                        else:
                                            logger.warning("PyTorch installed but CUDA verification failed")
                                            self._logs.append("PyTorch installed but CUDA verification failed")
                                    else:
                                        logger.warning("Failed to install PyTorch with CUDA, will try CPU version: %s", 
                                                     stderr[:200] if stderr else "Unknown")
                                        self._logs.append(f"Failed to install PyTorch with CUDA: {stderr[:200]}")
                                        # Continue with CPU installation
                            
                            # Check for requirements.txt
                            if not (self.base_dir / "requirements.txt").exists():
                                logger.error("requirements.txt not found in %s", str(self.base_dir))
                                self._logs.append("requirements.txt not found")
                                return False
                            
                            # Install requirements
                            logger.info("Installing dependencies from requirements.txt...")
                            logger.info("This may take several minutes (PyTorch and other large packages)...")
                            self._logs.append("Installing dependencies from requirements.txt...")
                            self._logs.append("This may take several minutes...")
                            
                            # If PyTorch was installed with CUDA, create a temporary requirements file without torch/torchaudio
                            if pytorch_installed_with_cuda:
                                # Read requirements.txt and filter out torch/torchaudio
                                requirements_path = self.base_dir / "requirements.txt"
                                temp_requirements_path = self.base_dir / "requirements_temp.txt"
                                
                                try:
                                    with open(requirements_path, 'r', encoding='utf-8') as f:
                                        lines = f.readlines()
                                    
                                    filtered_lines = []
                                    for line in lines:
                                        line_stripped = line.strip()
                                        # Skip torch and torchaudio lines
                                        if line_stripped.startswith('torch') or line_stripped.startswith('torchaudio'):
                                            continue
                                        filtered_lines.append(line)
                                    
                                    with open(temp_requirements_path, 'w', encoding='utf-8') as f:
                                        f.writelines(filtered_lines)
                                    
                                    install_cmd = [venv_python, "-m", "pip", "install", "-r", "requirements_temp.txt"]
                                    logger.info("Note: PyTorch already installed with CUDA, using filtered requirements.txt")
                                    self._logs.append("Note: PyTorch already installed with CUDA, using filtered requirements.txt")
                                except Exception as e:
                                    logger.warning("Failed to create filtered requirements, using full requirements.txt: %s", str(e))
                                    install_cmd = [venv_python, "-m", "pip", "install", "-r", "requirements.txt"]
                            else:
                                install_cmd = [venv_python, "-m", "pip", "install", "-r", "requirements.txt"]
                            
                            logger.info("Running: %s", " ".join(install_cmd))
                            
                            returncode, _, stderr = await self._run_command(
                                install_cmd,
                                timeout=1800,  # 30 minutes for large packages
                                cwd=str(self.base_dir)
                            )
                            
                            # Clean up temporary requirements file if it was created
                            if pytorch_installed_with_cuda:
                                temp_requirements_path = self.base_dir / "requirements_temp.txt"
                                try:
                                    if temp_requirements_path.exists():
                                        temp_requirements_path.unlink()
                                except Exception:
                                    pass  # Ignore cleanup errors
                            
                            if returncode == 0:
                                logger.info("Dependencies installed successfully")
                                self._logs.append("Dependencies installed successfully")
                                return True
                            else:
                                # Check for file lock errors
                                error_output = stderr
                                if "WinError 32" in error_output or "being used by another process" in error_output:
                                    if attempt < max_retries - 1:
                                        logger.warning("File lock detected, retrying in %d seconds... (attempt %d/%d)", retry_delay, attempt + 1, max_retries)
                                        self._logs.append(f"File lock detected, retrying in {retry_delay} seconds...")
                                        import time
                                        await asyncio.sleep(retry_delay)
                                        retry_delay *= 2  # Exponential backoff
                                        continue
                                    else:
                                        logger.error("File lock persists after %d retries. Another process may be using the venv.", max_retries)
                                        self._logs.append("File lock persists. Another process may be using the venv.")
                                
                                # Show relevant error lines
                                error_lines = error_output.strip().split('\n') if error_output else []
                                
                                # Filter out common warnings and show actual errors
                                important_lines = []
                                for line in error_lines:
                                    line_upper = line.upper()
                                    if any(keyword in line_upper for keyword in ['ERROR', 'FAILED', 'EXCEPTION', 'TRACEBACK', 'CANNOT', 'MISSING', 'REQUIREMENT']):
                                        important_lines.append(line)
                                
                                if important_lines:
                                    error_msg = '\n'.join(important_lines[-20:])  # Last 20 important lines
                                else:
                                    error_msg = '\n'.join(error_lines[-15:])  # Last 15 lines if no keywords found
                                
                                logger.error("pip install failed. Error output:\n%s", error_msg)
                                self._logs.append(f"pip install failed:\n{error_msg}")
                                return False
                        except Exception as e:
                            if attempt < max_retries - 1:
                                logger.warning("Installation attempt %d failed: %s, retrying...", attempt + 1, str(e))
                                self._logs.append(f"Installation attempt {attempt + 1} failed: {str(e)}, retrying...")
                                import time
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                logger.error("Installation failed after %d attempts: %s", max_retries, str(e))
                                self._logs.append(f"Installation failed after {max_retries} attempts: {str(e)}")
                                return False
                    
                    return False
                
                return await _install()
            except Exception as e:
                logger.error("Failed to install dependencies: %s", str(e), exc_info=True)
                self._logs.append(f"Failed to install dependencies: {str(e)}")
                return False
            finally:
                # Always clear the installing flag
                self._installing = False
    
    async def install(self) -> Dict[str, Any]:
        """Check if Chatterbox TTS API is installed (now a local service)."""
        if self._check_installation():
            return {
                "status": "success",
                "message": "Chatterbox TTS API is installed",
                "path": str(self.base_dir)
            }
        
        return {
            "status": "error",
            "message": "Chatterbox TTS API not found. Please install via the launcher.",
            "path": None
        }
    
    async def start(self) -> Dict[str, Any]:
        """Start the Chatterbox TTS API server."""
        # Check if already running by verifying port is accessible
        if self._check_port_available():
            # Port is accessible - service is running (maybe started externally)
            self._status = "running"
            return {
                "status": "success",
                "message": "Chatterbox TTS API is already running (detected on port)",
                "url": self.api_url
            }
        
        # Also check internal status
        if self.status == "running":
            # Status says running but port check failed - update status
            self._status = "stopped"
            if self.process:
                try:
                    if self.process.poll() is not None:
                        self.process = None
                except Exception:
                    pass
        
        if not self._check_installation():
            install_result = await self.install()
            if install_result["status"] != "success":
                return {
                    "status": "error",
                    "message": f"Cannot start: {install_result.get('message', 'Installation failed')}",
                    "error": install_result.get("error")
                }
        
        try:
            self._status = "starting"
            # Ensure venv exists and dependencies are installed
            if not await self._ensure_venv():
                raise RuntimeError("Failed to create Chatterbox TTS API virtual environment")
            
            # Get venv Python
            python_exe = self._get_venv_python()
            if not python_exe:
                raise RuntimeError("Chatterbox venv Python not found. Please reinstall.")
            
            self.python_exe = python_exe
            
            # Ensure dependencies are installed before starting
            if not self._check_dependencies_installed():
                logger.info("Dependencies not installed, installing now...")
                if not await self._install_dependencies():
                    raise RuntimeError("Failed to install Chatterbox TTS API dependencies. Check logs for details.")
            
            # Verify CUDA availability and PyTorch CUDA support before starting
            device_info = self._check_device_info()
            if device_info.get("cuda_available", False):
                logger.info("CUDA detected: %s (PyTorch %s)", 
                          device_info.get("gpu_name", "Unknown GPU"),
                          device_info.get("pytorch_version", "Unknown"))
            else:
                logger.warning("CUDA not available - Chatterbox will run in CPU mode. "
                             "For GPU support, ensure PyTorch with CUDA is installed in the Chatterbox venv.")
            
            logger.info("Starting Chatterbox TTS API server at %s...", self.api_url)
            
            # Start the server process
            loop = asyncio.get_event_loop()
            
            def _start():
                # Determine which file to run
                api_file = None
                if (self.base_dir / "main.py").exists():
                    api_file = "main.py"
                elif (self.base_dir / "api.py").exists():
                    api_file = "api.py"
                elif (self.base_dir / "src" / "main.py").exists():
                    api_file = str(self.base_dir / "src" / "main.py")
                else:
                    raise RuntimeError(f"No entry point found in {self.base_dir}. Expected main.py, api.py, or src/main.py")
                
                logger.info("Starting with entry point: %s, Python: %s", api_file, python_exe)
                
                # Use venv Python to run the API
                cmd = [python_exe, api_file]
                logger.info("Executing: %s in %s", " ".join(cmd), str(self.base_dir))
                
                # Set up environment with UTF-8 encoding
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                # Ensure PYTHONPATH includes the base directory for imports
                base_dir_str = str(self.base_dir.resolve())
                if 'PYTHONPATH' in env:
                    env['PYTHONPATH'] = f"{base_dir_str}{os.pathsep}{env['PYTHONPATH']}"
                else:
                    env['PYTHONPATH'] = base_dir_str
                
                # OPTIMIZATION: Detect CUDA and set DEVICE environment variable for GPU support
                # Check if CUDA is available in the venv
                device_info = self._check_device_info()
                if device_info.get("cuda_available", False):
                    env['DEVICE'] = 'cuda'
                    logger.info("CUDA detected - setting DEVICE=cuda for GPU inference")
                    self._logs.append("CUDA detected - setting DEVICE=cuda for GPU inference")
                else:
                    # Explicitly set to auto (will detect best available device)
                    env['DEVICE'] = 'auto'
                    logger.info("No CUDA detected - using DEVICE=auto (will use CPU or MPS if available)")
                    self._logs.append("No CUDA detected - using DEVICE=auto")
                
                # On Windows, create a new console window so logs are visible
                # On Unix, use default behavior (inherit terminal)
                if os.name == 'nt':
                    # CREATE_NEW_CONSOLE creates a new window for the process
                    creation_flags = subprocess.CREATE_NEW_CONSOLE
                    # Don't redirect stdout/stderr so they appear in the new window
                    stdout_handle = None
                    stderr_handle = None
                else:
                    creation_flags = 0
                    # On Unix, we can still capture output if needed, but for now show it
                    stdout_handle = None
                    stderr_handle = None
                
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.base_dir),
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    creationflags=creation_flags,
                    env=env
                )
                
                return process
            
            self.process = await loop.run_in_executor(None, _start)
            
            # Wait a moment to see if it starts successfully
            await asyncio.sleep(2)
            
            if self.process.poll() is not None:
                # Process died immediately
                # Note: If we're using a new console window, we can't capture stdout/stderr
                # The error will be visible in the console window
                error_msg = "Chatterbox TTS API process exited immediately. Check the console window for error details."
                
                logger.error("Chatterbox TTS API process exited immediately. Check the console window for details.")
                self._status = "error"
                self._error_message = error_msg
                self.process = None
                raise RuntimeError(f"Chatterbox TTS API failed to start: {error_msg}")
            
            # Don't mark as running yet - wait for health check
            self._status = "starting"
            self._error_message = None
            
            # Wait for the service to actually start and respond to health checks
            # Try health check with retries
            try:
                import httpx
            except ImportError:
                # httpx not available, skip health check
                logger.warning("httpx not available, skipping health check verification")
                self._status = "starting"
                return {
                    "status": "success",
                    "message": "Chatterbox TTS API process started (health check unavailable)",
                    "url": self.api_url,
                    "frontend_url": f"http://localhost:{self.frontend_port}"
                }
            
            max_health_retries = 30  # 30 seconds total
            health_check_passed = False
            
            for attempt in range(max_health_retries):
                # Check if process is still alive
                if self.process.poll() is not None:
                    error_msg = "Chatterbox TTS API process died during startup. Check the console window for error details."
                    logger.error("Chatterbox TTS API process died during startup. Check the console window for details.")
                    self._status = "error"
                    self._error_message = error_msg
                    self.process = None
                    raise RuntimeError(f"Chatterbox TTS API died during startup: {error_msg}")
                
                # Try health check
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        response = await client.get(f"{self.api_url.replace('/v1', '')}/health")
                        if response.status_code == 200:
                            health_check_passed = True
                            logger.info("Chatterbox TTS API health check passed")
                            break
                except Exception:
                    # Health check failed, wait and retry
                    if attempt < max_health_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        logger.warning("Chatterbox TTS API health check did not pass after %d attempts, but process is running", max_health_retries)
            
            if health_check_passed:
                self._status = "running"
                logger.info("Chatterbox TTS API server started successfully and is responding")
            else:
                # Process is running but not responding - might still be initializing
                self._status = "starting"
                logger.warning("Chatterbox TTS API process is running but not responding to health checks yet (may still be initializing)")
            
            return {
                "status": "success",
                "message": "Chatterbox TTS API started successfully",
                "url": self.api_url,
                "frontend_url": f"http://localhost:{self.frontend_port}"
            }
        except Exception as e:
            self._status = "error"
            self._error_message = str(e)
            logger.error(f"Failed to start Chatterbox TTS API: {e}")
            return {
                "status": "error",
                "message": f"Failed to start: {str(e)}",
                "error": str(e)
            }
    
    async def stop(self) -> Dict[str, Any]:
        """Stop the Chatterbox TTS API server."""
        if not self.is_running:
            return {
                "status": "success",
                "message": "Chatterbox TTS API is not running"
            }
        
        try:
            self._status = "stopping"
            logger.info("Stopping Chatterbox TTS API server...")
            
            if self.process:
                # Try graceful shutdown first
                try:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        self.process.kill()
                        self.process.wait()
                except Exception as e:
                    logger.warning(f"Error during graceful shutdown: {e}")
                    if self.process:
                        try:
                            self.process.kill()
                            self.process.wait()
                        except Exception:
                            pass
                
                self.process = None
            
            self._status = "stopped"
            self._error_message = None
            
            logger.info("Chatterbox TTS API server stopped")
            
            return {
                "status": "success",
                "message": "Chatterbox TTS API stopped successfully"
            }
        except Exception as e:
            self._status = "error"
            self._error_message = str(e)
            logger.error(f"Failed to stop Chatterbox TTS API: {e}")
            return {
                "status": "error",
                "message": f"Failed to stop: {str(e)}",
                "error": str(e)
            }
    
    async def restart(self) -> Dict[str, Any]:
        """Restart the Chatterbox TTS API server.
        
        This will restart with GPU support if CUDA is available.
        The DEVICE environment variable will be set to 'cuda' if CUDA is detected.
        """
        await self.stop()
        await asyncio.sleep(1)
        return await self.start()
    
    def _check_device_info(self) -> Dict[str, Any]:
        """Check if CUDA is available in the venv."""
        venv_python = self._get_venv_python()
        return check_device_info(venv_python)
    
    def _get_service_device_info(self) -> Optional[Dict[str, Any]]:
        """Get device info from the running service via health endpoint."""
        if not self.is_running:
            return None
        
        # Don't try to fetch from service synchronously - it causes async issues
        # The device info will be checked from venv instead
        # This avoids ConnectionResetError on Windows when connections are closed
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current service status with installation and device information."""
        status = self.status
        installed = self._check_installation()
        dependencies_installed = self._check_dependencies_installed() if installed else False
        
        # Get device info
        device_info = None
        if self.is_running:
            # Try to get from running service first
            device_info = self._get_service_device_info()
        
        # Fall back to checking venv if service not running or device info not available
        if device_info is None:
            device_info = self._check_device_info()
        
        return {
            "status": status,
            "is_running": self.is_running,
            "is_installing": self._installing,
            "api_url": self.api_url if self.is_running else None,
            "frontend_url": f"http://localhost:{self.frontend_port}" if self.is_running else None,
            "installed": installed,
            "dependencies_installed": dependencies_installed,
            "device": device_info.get("device", "unknown"),
            "cuda_available": device_info.get("cuda_available", False),
            "gpu_name": device_info.get("gpu_name"),
            "pytorch_version": device_info.get("pytorch_version"),
            "error_message": self._error_message,
            "base_dir": str(self.base_dir) if installed else None
        }


    def get_logs(self) -> List[str]:
        """Get recent service logs."""
        return list(self._logs)

    async def _run_command(self, cmd: List[str], cwd: Optional[str] = None, timeout: int = 300) -> Tuple[int, str, str]:
        """Run command and capture output in real-time to logs."""
        try:
            self._logs.append(f"> {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=os.environ.copy()
            )
            
            stdout_lines = []
            stderr_lines = []
            
            async def read_stream(stream, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode().strip()
                    if line_str:
                        self._logs.append(line_str)
                        if is_stderr:
                            stderr_lines.append(line_str)
                        else:
                            stdout_lines.append(line_str)
            
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, is_stderr=True)
            )
            
            returncode = await asyncio.wait_for(process.wait(), timeout=timeout)
            
            return returncode, "\n".join(stdout_lines), "\n".join(stderr_lines)
            
        except asyncio.TimeoutError:
            self._logs.append(f"Command timed out after {timeout} seconds")
            if process:
                try:
                    process.kill()
                except Exception:
                    pass
            return -1, "", "Timeout"
        except Exception as e:
            self._logs.append(f"Command failed: {str(e)}")
            return -1, "", str(e)


# Global instance
chatterbox_service = ChatterboxServiceManager()

