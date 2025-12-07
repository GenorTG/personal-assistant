#!/usr/bin/env python3
"""
Unified Personal Assistant Management Application
Handles installation, process management, health checks, and testing
Works on Windows, Linux, and macOS
"""

import sys
import os
import subprocess
import platform
import shutil
import time
import signal
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import threading
import socket
import webbrowser
from datetime import datetime

# Try to import rich for better UI, fallback to basic if not available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Confirm, Prompt
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("Warning: 'rich' library not found. Install with: pip install rich")
    print("Falling back to basic console output.\n")

# Try to import psutil for process management
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class ServiceStatus(Enum):
    """Service status enumeration."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    UNKNOWN = "unknown"

class ServiceManager:
    """Manages all Personal Assistant services."""
    
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).parent.parent.resolve()
        self.console = Console() if HAS_RICH else None
        self.processes: Dict[str, subprocess.Popen] = {}
        self.service_status: Dict[str, ServiceStatus] = {}
        self.service_info: Dict[str, Dict[str, Any]] = {}
        
        # Initialize external services manager lazily (only when needed)
        # This defers the metadata file loading until actually needed
        self.external_services_mgr = None
        
        # Core services share a single venv
        self.core_services = ["memory", "tools", "gateway", "llm"]
        self.core_venv = self.root_dir / "services" / ".core_venv"
        
        # Service configurations
        # Note: Core services (memory, tools, gateway, llm) share a venv and start simultaneously
        self.services = {
            "memory": {
                "name": "Core: Memory Service",
                "port": 8005,
                "url": "http://localhost:8005",
                "health_endpoint": "/health",
                "start_cmd": lambda: self._get_python_service_start_cmd("memory", "main:app", 8005),
                "install_cmd": lambda: self._install_python_service("memory"),
                "dir": self.root_dir / "services" / "memory",
                "venv": self.core_venv,  # Shared venv for core services
                "optional": False,
                "is_core": True
            },
            "tools": {
                "name": "Core: Tool Service",
                "port": 8006,
                "url": "http://localhost:8006",
                "health_endpoint": "/health",
                "start_cmd": lambda: self._get_python_service_start_cmd("tools", "main:app", 8006),
                "install_cmd": lambda: self._install_python_service("tools"),
                "dir": self.root_dir / "services" / "tools",
                "venv": self.core_venv,  # Shared venv for core services
                "optional": True,
                "is_core": True
            },
            "gateway": {
                "name": "Core: API Gateway",
                "port": 8000,
                "url": "http://localhost:8000",
                "health_endpoint": "/health",
                "start_cmd": lambda: self._get_python_service_start_cmd("gateway", "main:app", 8000),
                "install_cmd": lambda: self._install_python_service("gateway"),
                "dir": self.root_dir / "services" / "gateway",
                "venv": self.core_venv,  # Shared venv for core services
                "optional": False,
                "is_core": True
            },
            "llm": {
                "name": "Core: LLM Service",
                "port": 8001,
                "url": "http://localhost:8001",
                "health_endpoint": "/health",
                "start_cmd": lambda: [],  # LLM is managed by Gateway, not directly started
                "install_cmd": lambda: self._install_python_service("llm"),
                "dir": self.root_dir / "services" / "llm",
                "venv": self.core_venv,  # Shared venv for core services
                "optional": False,
                "is_core": True
            },
            "whisper": {
                "name": "Whisper Service (STT)",
                "port": 8003,
                "url": "http://localhost:8003",
                "health_endpoint": "/health",
                "start_cmd": self._get_whisper_start_cmd,
                "install_cmd": self._get_whisper_install_cmd,
                "dir": self.root_dir / "services" / "stt-whisper",
                "venv": self.root_dir / "services" / "stt-whisper" / ".venv",
                "optional": True,
                "is_core": False
            },
            "piper": {
                "name": "Piper Service (TTS)",
                "port": 8004,
                "url": "http://localhost:8004",
                "health_endpoint": "/health",
                "start_cmd": self._get_piper_start_cmd,
                "install_cmd": self._get_piper_install_cmd,
                "dir": self.root_dir / "services" / "tts-piper",
                "venv": self.root_dir / "services" / "tts-piper" / ".venv",
                "optional": True,
                "is_core": False
            },
            "chatterbox": {
                "name": "Chatterbox Service (TTS)",
                "port": 4123,
                "url": "http://localhost:4123",
                "health_endpoint": "/health",
                "start_cmd": self._get_chatterbox_start_cmd,
                "install_cmd": self._get_chatterbox_install_cmd,
                "dir": self.root_dir / "external_services" / "chatterbox-tts-api",
                "venv": self.root_dir / "external_services" / "chatterbox-tts-api" / ".venv",
                "repo_url": "https://github.com/travisvn/chatterbox-tts-api",
                "is_external": True,
                "optional": True,
                "is_core": False,
                "python_version": "3.11"
            },
            "kokoro": {
                "name": "Kokoro Service (TTS)",
                "port": 8880,
                "url": "http://localhost:8880",
                "health_endpoint": "/health",
                "start_cmd": self._get_kokoro_start_cmd,
                "install_cmd": self._get_kokoro_install_cmd,
                "dir": self.root_dir / "services" / "tts-kokoro",
                "venv": self.root_dir / "services" / "tts-kokoro" / ".venv",
                "optional": True,
                "is_core": False
            },
            "frontend": {
                "name": "Frontend (Next.js)",
                "port": 8002,
                "url": "http://localhost:8002",
                "health_endpoint": None,
                "start_cmd": self._get_frontend_start_cmd,
                "install_cmd": self._get_frontend_install_cmd,
                "dir": self.root_dir / "services" / "frontend",
                "venv": None,
                "optional": False,
                "is_core": False
            }
        }
        
        # Initialize status
        for service_id in self.services:
            self.service_status[service_id] = ServiceStatus.UNKNOWN
            self.service_info[service_id] = {}
    
    def _get_backend_start_cmd(self) -> List[str]:
        """Get backend start command."""
        python_exe = self._get_python_exe()
        return [python_exe, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
    
    def _get_frontend_start_cmd(self) -> List[str]:
        """Get frontend start command (Production)."""
        if platform.system() == "Windows":
            return ["npm.cmd", "run", "start"]
        return ["npm", "run", "start"]

    def _get_backend_install_cmd(self) -> List[str]:
        """Get backend install command."""
        # Use the root install.bat if on Windows, otherwise pip
        if platform.system() == "Windows" and (self.root_dir / "install.bat").exists():
            return [str(self.root_dir / "install.bat")]
        
        python_exe = self._get_python_exe()
        return [python_exe, "-m", "pip", "install", "-r", "requirements.txt"]

    def _get_frontend_install_cmd(self) -> List[str]:
        """Get frontend install command.
        Returns a Python script that executes npm install and npm run build.
        """
        import tempfile
        
        # Create a temporary Python script that runs npm commands
        frontend_dir = str(self.services['frontend']['dir'])
        # Escape backslashes for raw string in Python script
        frontend_dir_escaped = frontend_dir.replace('\\', '\\\\')
        
        install_script = f"""import sys
import subprocess
import os
import atexit
import platform

# Script path for cleanup (will be replaced with actual path)
script_path = r"__SCRIPT_PATH_PLACEHOLDER__"

def cleanup():
    try:
        if script_path and os.path.exists(script_path):
            os.remove(script_path)
    except Exception:
        pass

atexit.register(cleanup)

# Change to frontend directory
frontend_dir = r"{frontend_dir_escaped}"
if not os.path.exists(frontend_dir):
    print(f"[FAIL] Frontend directory does not exist: {{frontend_dir}}")
    sys.exit(1)

os.chdir(frontend_dir)
print("[INFO] Installing frontend dependencies...")
print(f"[INFO] Working directory: {{os.getcwd()}}")

# Check if Node.js is available
try:
    # Use shell on Windows, direct call on Unix
    use_shell = platform.system() == "Windows"
    result = subprocess.run(
        ["node", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
        shell=use_shell
    )
    if result.returncode != 0:
        print("[FAIL] Node.js not found. Please install Node.js first.")
        sys.exit(1)
    print(f"[OK] Node.js version: {{result.stdout.strip()}}")
except FileNotFoundError:
    print("[FAIL] Node.js not found. Please install Node.js first.")
    sys.exit(1)
except Exception as e:
    print(f"[FAIL] Error checking Node.js: {{e}}")
    sys.exit(1)

# Determine npm command based on platform
use_shell = platform.system() == "Windows"
# On Windows with shell=True, use "npm", otherwise use "npm.cmd"
npm_cmd = "npm" if use_shell else ("npm.cmd" if platform.system() == "Windows" else "npm")

# Run npm install
print("[INFO] Running npm install...")
print(f"[INFO] Command: {{' '.join([npm_cmd, 'install'])}}")
sys.stdout.flush()
try:
    # Use Popen to stream output in real-time
    process = subprocess.Popen(
        [npm_cmd, "install"],
        shell=use_shell,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    # Stream output line by line
    for line in iter(process.stdout.readline, ''):
        if line:
            print(line.rstrip())
            sys.stdout.flush()
    process.wait()
    if process.returncode != 0:
        print("[FAIL] npm install failed")
        sys.exit(1)
    print("[OK] npm install completed")
    sys.stdout.flush()
except Exception as e:
    print(f"[FAIL] Error running npm install: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Update Next.js and other packages to latest versions
print("[INFO] Updating packages to latest versions...")
print(f"[INFO] Command: {{' '.join([npm_cmd, 'update'])}}")
sys.stdout.flush()
try:
    # Run npm update to update packages within their version ranges
    process = subprocess.Popen(
        [npm_cmd, "update"],
        shell=use_shell,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    # Stream output line by line
    for line in iter(process.stdout.readline, ''):
        if line:
            print(line.rstrip())
            sys.stdout.flush()
    process.wait()
    # npm update returns 0 even if nothing was updated, so we don't fail on non-zero
    print("[OK] npm update completed")
    sys.stdout.flush()
except Exception as e:
    print(f"[WARNING] Error running npm update: {{e}}")
    # Don't fail installation if update fails
    import traceback
    traceback.print_exc()

# Update Next.js to latest version explicitly
print("[INFO] Updating Next.js to latest version...")
print(f"[INFO] Command: {{' '.join([npm_cmd, 'install', 'next@latest'])}}")
sys.stdout.flush()
try:
    # Install latest Next.js version
    process = subprocess.Popen(
        [npm_cmd, "install", "next@latest"],
        shell=use_shell,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    # Stream output line by line
    for line in iter(process.stdout.readline, ''):
        if line:
            print(line.rstrip())
            sys.stdout.flush()
    process.wait()
    if process.returncode != 0:
        print("[WARNING] Next.js update failed, but continuing...")
    else:
        print("[OK] Next.js updated to latest version")
    sys.stdout.flush()
except Exception as e:
    print(f"[WARNING] Error updating Next.js: {{e}}")
    # Don't fail installation if Next.js update fails
    import traceback
    traceback.print_exc()

# Run npm run build
print("[INFO] Running npm run build...")
print(f"[INFO] Command: {{' '.join([npm_cmd, 'run', 'build'])}}")
sys.stdout.flush()
try:
    # Use Popen to stream output in real-time
    process = subprocess.Popen(
        [npm_cmd, "run", "build"],
        shell=use_shell,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    # Stream output line by line
    for line in iter(process.stdout.readline, ''):
        if line:
            print(line.rstrip())
            sys.stdout.flush()
    process.wait()
    if process.returncode != 0:
        print("[FAIL] npm run build failed")
        sys.exit(1)
    print("[OK] npm run build completed")
    print("[OK] Frontend installation completed successfully!")
    sys.stdout.flush()
except Exception as e:
    print(f"[FAIL] Error running npm run build: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
        
        # Write script to temporary file
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as script_file:
                script_path = script_file.name
                # Update script to include the actual script path
                final_script = install_script.replace(
                    '__SCRIPT_PATH_PLACEHOLDER__',
                    script_path.replace('\\', '\\\\')
                )
                script_file.write(final_script)
            
            # Return command to execute the script
            return [sys.executable, script_path]
        except Exception as e:
            self._print(f"Failed to create install script: {e}", "red")
            return [sys.executable, "-c", "import sys; print('[FAIL] Failed to create install script'); sys.exit(1)"]

    def _get_kokoro_install_cmd(self) -> List[str]:
        """Get Kokoro install command."""
        if platform.system() == "Windows" and (self.services["kokoro"]["dir"] / "install.bat").exists():
            return [str(self.services["kokoro"]["dir"] / "install.bat")]
        return [] # Manual install required if no script
    
    def _get_kokoro_start_cmd(self) -> List[str]:
        """Get Kokoro TTS service start command."""
        venv_python = self.services["kokoro"]["venv"] / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
        if not venv_python.exists():
            venv_python = self.services["kokoro"]["venv"] / ("Scripts" if platform.system() == "Windows" else "bin") / "python.exe"
        if venv_python.exists():
            return [str(venv_python), "main.py"]
    def _get_whisper_install_cmd(self) -> List[str]:
        return self._install_python_service("whisper")

    def _get_whisper_start_cmd(self) -> List[str]:
        return self._get_python_service_start_cmd("whisper", "main:app", 8003)

    def _get_piper_install_cmd(self) -> List[str]:
        return self._install_python_service("piper")

    def _get_piper_start_cmd(self) -> List[str]:
        return self._get_python_service_start_cmd("piper", "main:app", 8004)

    def _get_chatterbox_install_cmd(self) -> List[str]:
        # Ensure repo is cloned and .env is prepared
        if not self._ensure_external_service("chatterbox"):
            return []
        # Use standard python service installer - it will handle CUDA detection
        # The _install_python_service method has special handling for Chatterbox
        # Always run full install
        return self._install_python_service("chatterbox")


    def _get_chatterbox_start_cmd(self) -> List[str]:
        return self._get_python_service_start_cmd("chatterbox", "app.main:app", 4123)

    def _get_kokoro_install_cmd(self) -> List[str]:
        return self._install_python_service("kokoro")

    def _get_kokoro_start_cmd(self) -> List[str]:
        return self._get_python_service_start_cmd("kokoro", "main:app", 8880)

    def _get_python_service_start_cmd(self, service_key: str, app_module: str, port: int) -> List[str]:
        """Generic start command for Python services."""
        service = self.services[service_key]
        venv_python = service["venv"] / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
        if platform.system() == "Windows":
            venv_python = venv_python.with_suffix(".exe")
        
        if venv_python.exists():
            return [str(venv_python), "-m", "uvicorn", app_module, "--host", "0.0.0.0", "--port", str(port)]
        return []

    def _check_venv_locks(self, venv_dir: Path) -> bool:
        """Check if venv is locked by running processes. Returns True if safe to proceed."""
        if not venv_dir.exists():
            return True
        
        if platform.system() == "Windows":
            try:
                # Check if any Python processes are using files in the venv
                import psutil
                venv_str = str(venv_dir).lower()
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        if proc.info['name'] and 'python' in proc.info['name'].lower():
                            # Check if process is using files in venv
                            try:
                                for file in proc.open_files():
                                    if venv_str in file.path.lower():
                                        self._print(f"Warning: Python process (PID {proc.info['pid']}) is using files in venv", "yellow")
                                        self._print("Please stop all services before reinstalling", "yellow")
                                        return False
                            except (psutil.AccessDenied, psutil.NoSuchProcess):
                                pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except ImportError:
                # psutil not available, skip check
                pass
            except Exception:
                # Any other error, continue anyway
                pass
        
        return True

    def _install_python_service(self, service_key: str) -> List[str]:
        """Install a Python service using a virtual environment and pip.
        Executes commands directly to avoid shell quoting issues.
        Special handling for LLM service to build llama-cpp-python with CUDA.
        Core services (memory, tools, gateway, llm) share a single venv.
        Always runs pip install -r requirements.txt (pip will skip already installed packages).
        
        Args:
            service_key: Key of the service to install
        """
        service = self.services[service_key]
        venv_dir = service["venv"]
        req_file = service["dir"] / "requirements.txt"
        service_dir = service["dir"]
        is_core = service.get("is_core", False)
        
        # For core services, if shared venv already exists, check if it's valid
        # If venv exists but pip is missing, we need to set it up properly
        if is_core and venv_dir.exists():
            # Check if venv is valid
            if platform.system() == "Windows":
                python_exe = venv_dir / "Scripts" / "python.exe"
            else:
                python_exe = venv_dir / "bin" / "python"
            
            if python_exe.exists():
                # Check if pip is available
                creation_flags = 0
                if platform.system() == "Windows":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                # Test if pip is available
                try:
                    result = subprocess.run(
                        [str(python_exe), "-m", "pip", "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        creationflags=creation_flags
                    )
                    pip_available = result.returncode == 0
                except Exception:
                    pip_available = False
                
                if pip_available:
                    # Shared venv exists and pip works - install this service's requirements
                    # pip will handle skipping if already satisfied, or install missing packages
                    print(f"[CORE] Shared venv exists. Installing {service['name']} dependencies...")
                    
                    # Build pip install command (always run, pip will skip already installed packages)
                    pip_cmd = [str(python_exe), "-m", "pip", "install", "-r", str(req_file)]
                    
                    try:
                        # Stream output directly to stdout (not captured) so launcher can capture it
                        result = subprocess.run(
                            pip_cmd,
                            check=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                        print(f"[SUCCESS] {service['name']} dependencies installed in shared venv")
                        return [sys.executable, "-c", "print('[SUCCESS] Dependencies installed')"]
                    except subprocess.CalledProcessError as e:
                        error_msg = str(e)
                        print(f"[ERROR] Failed to install dependencies: {error_msg[:500]}")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
                else:
                    # Venv exists but pip is missing - need to install pip first
                    print(f"[CORE] Shared venv exists but pip is missing. Installing pip...")
                    try:
                        # Use ensurepip to bootstrap pip - stream output to stdout
                        result = subprocess.run(
                            [str(python_exe), "-m", "ensurepip", "--upgrade"],
                            check=True,
                            text=True,
                            timeout=60,
                            creationflags=creation_flags
                        )
                        print("[CORE] Pip installed successfully")
                        # Now try installing requirements (always run, pip will skip already installed packages)
                        pip_cmd = [str(python_exe), "-m", "pip", "install", "-r", str(req_file)]
                        result = subprocess.run(
                            pip_cmd,
                            check=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                        print(f"[SUCCESS] {service['name']} dependencies installed in shared venv")
                        return [sys.executable, "-c", "print('[SUCCESS] Dependencies installed')"]
                    except subprocess.CalledProcessError as e:
                        error_msg = str(e)
                        print(f"[ERROR] Failed to install pip or dependencies: {error_msg[:500]}")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
                    except Exception as e:
                        print(f"[ERROR] Unexpected error: {e}")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
        
        if is_core:
            print(f"Setting up Core Services shared environment...")
        else:
            print(f"Setting up {service['name']} environment...")

        # 0. Check for locked files
        if not self._check_venv_locks(venv_dir):
            print("[ERROR] Cannot proceed - venv is locked by running processes")
            return [sys.executable, "-c", "import sys; print('[ERROR] Venv locked'); sys.exit(1)"]

        # NEVER remove existing venvs - that's too destructive!
        # Always run pip install -r requirements.txt (pip will skip already installed packages)
        # We only create venvs if they don't exist

        # 1. Create virtual environment (if it doesn't exist)
        # Determine Python version
        # Default to 3.12 as requested
        target_minor = 12
        
        # Check for service-specific override
        if "python_version" in service:
            try:
                # format "3.10"
                ver_str = str(service["python_version"])
                if "." in ver_str:
                    target_minor = int(ver_str.split(".")[1])
                    print(f"Service {service['name']} requests Python 3.{target_minor}")
            except (ValueError, IndexError):
                print(f"[WARNING] Invalid python_version '{service.get('python_version')}' for {service['name']}, defaulting to 3.12")

        # Check existing venv version if it exists
        if venv_dir.exists():
            try:
                if platform.system() == "Windows":
                    check_python = venv_dir / "Scripts" / "python.exe"
                else:
                    check_python = venv_dir / "bin" / "python"
                
                if check_python.exists():
                    # Check version
                    creation_flags = 0
                    if platform.system() == "Windows":
                        creation_flags = subprocess.CREATE_NO_WINDOW
                        
                    res = subprocess.run(
                        [str(check_python), "--version"], 
                        capture_output=True, 
                        text=True, 
                        creationflags=creation_flags
                    )
                    if res.returncode == 0:
                        # Output format: "Python 3.11.9"
                        out = res.stdout.strip() or res.stderr.strip()
                        if out.startswith("Python 3."):
                            current_minor = int(out.split(".")[1])
                            if current_minor != target_minor:
                                print(f"[WARNING] Venv at {venv_dir} has Python 3.{current_minor}, but service requires 3.{target_minor}")
                                print(f"[INFO] Deleting venv to reinstall with correct version...")
                                import shutil
                                try:
                                    shutil.rmtree(venv_dir, ignore_errors=True)
                                    if venv_dir.exists():
                                        # Try shell delete if shutil fails
                                        if platform.system() == "Windows":
                                            os.system(f'rmdir /S /Q "{venv_dir}"')
                                except Exception as e:
                                    print(f"[ERROR] Failed to delete venv: {e}")
            except Exception as e:
                print(f"[WARNING] Failed to check venv version: {e}")

        if not venv_dir.exists():
            if is_core:
                print(f"Creating shared virtual environment for core services (Python 3.{target_minor})...")
            else:
                print(f"Creating virtual environment for {service['name']} (Python 3.{target_minor})...")
            
            python_exe = self.find_latest_python(max_major=3, max_minor=target_minor)
            
            try:
                # Use CREATE_NO_WINDOW on Windows
                creation_flags = 0
                if platform.system() == "Windows":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                result = subprocess.run(
                    [python_exe, "-m", "venv", str(venv_dir)], 
                    check=True, 
                    timeout=60,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creation_flags
                )
                if result.stdout:
                    print(result.stdout)
            except subprocess.CalledProcessError as e:
                error_msg = e.stdout or str(e) if hasattr(e, 'stdout') else str(e)
                print(f"[ERROR] Failed to create venv: {error_msg}")
                return [sys.executable, "-c", "import sys; print('[ERROR] Failed to create venv'); sys.exit(1)"]
            except subprocess.TimeoutExpired:
                print("[ERROR] Timeout creating venv")
                return [sys.executable, "-c", "import sys; print('[ERROR] Timeout creating venv'); sys.exit(1)"]

        # 2. Install dependencies
        python_exe = venv_dir / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
        if platform.system() == "Windows":
            python_exe = python_exe.with_suffix(".exe")
        
        # Verify python executable exists
        if not python_exe.exists():
            print(f"[ERROR] Python executable not found at {python_exe}")
            return [sys.executable, "-c", "import sys; print('[ERROR] Python executable not found'); sys.exit(1)"]
        
        # Use CREATE_NO_WINDOW on Windows for all subprocess calls
        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW
        
        try:
            # Upgrade pip and install build tools - stream output to stdout
            print("Upgrading pip and installing build tools...")
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools", "cmake"],
                check=False,
                text=True,
                timeout=300,
                creationflags=creation_flags
            )
            if result.returncode != 0:
                print(f"[WARNING] pip upgrade had issues (exit code: {result.returncode})")
            
            # Special handling for Chatterbox service - install PyTorch with CUDA by default
            if service_key == "chatterbox":
                import shutil
                import re
                
                # Detect CUDA availability
                nvidia_smi = shutil.which("nvidia-smi")
                has_cuda = False
                cuda_index = "https://download.pytorch.org/whl/cu121"  # Default to CUDA 12.1
                
                if nvidia_smi:
                    cuda_check_result = subprocess.run(
                        [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=creation_flags
                    )
                    if cuda_check_result.returncode == 0 and cuda_check_result.stdout.strip():
                        has_cuda = True
                        print("[CHATTERBOX] CUDA GPU detected - will install PyTorch with CUDA support by default")
                        
                        # Try to detect CUDA version
                        nvcc = shutil.which("nvcc")
                        if nvcc:
                            nvcc_result = subprocess.run(
                                [nvcc, "--version"],
                                capture_output=True,
                                text=True,
                                timeout=10,
                                creationflags=creation_flags
                            )
                            if nvcc_result.returncode == 0:
                                for line in nvcc_result.stdout.split('\n'):
                                    if 'release' in line.lower():
                                        match = re.search(r'release\s+(\d+)\.(\d+)', line, re.IGNORECASE)
                                        if match:
                                            major, minor = match.groups()
                                            # Use cu124 for CUDA 12.4+ (recommended), cu121 for CUDA 12.1-12.3
                                            if major == "12" and int(minor) >= 4:
                                                cuda_index = "https://download.pytorch.org/whl/cu124"
                                                print(f"[CHATTERBOX] Detected CUDA version: {major}.{minor} (using cu124 PyTorch build)")
                                            elif major == "12":
                                                cuda_index = "https://download.pytorch.org/whl/cu121"
                                                print(f"[CHATTERBOX] Detected CUDA version: {major}.{minor} (using cu121 PyTorch build)")
                                            elif major == "11" and minor == "8":
                                                cuda_index = "https://download.pytorch.org/whl/cu118"
                                                print(f"[CHATTERBOX] Detected CUDA version: {major}.{minor} (using cu118 PyTorch build)")
                                            break
                
                # Check if PyTorch with CUDA is already installed (preserve it!)
                pytorch_has_cuda = False
                if has_cuda:
                    check_cuda_cmd = [str(python_exe), "-c", "import torch; print('CUDA:', torch.cuda.is_available())"]
                    try:
                        cuda_check = subprocess.run(
                            check_cuda_cmd,
                            capture_output=True,
                            text=True,
                            timeout=10,
                            creationflags=creation_flags
                        )
                        if cuda_check.returncode == 0 and "CUDA: True" in cuda_check.stdout:
                            pytorch_has_cuda = True
                            print("[CHATTERBOX] PyTorch with CUDA support already installed - preserving it")
                    except Exception:
                        pass
                
                # Install PyTorch with CUDA if CUDA is available and PyTorch doesn't have CUDA
                pytorch_cmd = None  # Define outside if block for use in verification later
                if has_cuda and not pytorch_has_cuda:
                    print("[CHATTERBOX] Installing PyTorch with CUDA support (default for Chatterbox)...")
                    # First, uninstall any existing CPU-only PyTorch
                    try:
                        print("[CHATTERBOX] Uninstalling existing PyTorch (if any)...")
                        uninstall_cmd = [str(python_exe), "-m", "pip", "uninstall", "torch", "torchaudio", "-y"]
                        # Stream uninstall output to stdout
                        uninstall_result = subprocess.run(
                            uninstall_cmd,
                            text=True,
                            timeout=300,
                            creationflags=creation_flags
                        )
                    except Exception as e:
                        print(f"[CHATTERBOX] Note: Uninstall step had issues (may be normal): {e}")
                    
                    # Chatterbox requires torch==2.6.0 and torchaudio==2.6.0 (exact versions)
                    # CUDA index was already determined above based on CUDA version
                    pytorch_cmd = [
                        str(python_exe), "-m", "pip", "install",
                        "torch==2.6.0",
                        "torchaudio==2.6.0",
                        "--index-url", cuda_index,
                        "--no-cache-dir"  # Ensure fresh download
                    ]
                    try:
                        # Stream PyTorch installation output to stdout
                        pytorch_result = subprocess.run(
                            pytorch_cmd,
                            check=True,
                            text=True,
                            timeout=1800,  # 30 minutes
                            creationflags=creation_flags
                        )
                        
                        # VERIFY CUDA installation actually worked
                        verify_cmd = [str(python_exe), "-c", "import torch; print('CUDA_BUILT:', torch.version.cuda if hasattr(torch.version, 'cuda') and torch.version.cuda else 'None'); print('CUDA_AVAILABLE:', torch.cuda.is_available())"]
                        verify_result = subprocess.run(
                            verify_cmd,
                            capture_output=True,
                            text=True,
                            timeout=10,
                            creationflags=creation_flags
                        )
                        if verify_result.returncode == 0:
                            if "CUDA_BUILT: None" in verify_result.stdout or "CUDA_AVAILABLE: False" in verify_result.stdout:
                                print("[CHATTERBOX] WARNING: PyTorch installation completed but CUDA is not available!")
                                print("[CHATTERBOX] This may indicate:")
                                print("[CHATTERBOX]   - CUDA runtime/drivers not installed")
                                print("[CHATTERBOX]   - PyTorch CUDA build doesn't match CUDA runtime")
                                print("[CHATTERBOX]   - GPU not accessible")
                                print("[CHATTERBOX] Will continue with CPU-only installation")
                                pytorch_has_cuda = False
                            else:
                                print("[CHATTERBOX] PyTorch with CUDA support installed and verified successfully")
                                pytorch_has_cuda = True
                        else:
                            print("[CHATTERBOX] WARNING: Could not verify CUDA installation")
                            pytorch_has_cuda = False
                    except subprocess.CalledProcessError as e:
                        print(f"[CHATTERBOX] Warning: Failed to install PyTorch with CUDA: {e.stdout[:200] if e.stdout else str(e)}")
                        print("[CHATTERBOX] Will continue with CPU-only installation")
                        pytorch_has_cuda = False
                
                # Install requirements, filtering out torch/torchaudio if CUDA PyTorch is installed
                if req_file.exists():
                    if pytorch_has_cuda:
                        # Read requirements and filter out torch/torchaudio
                        print("[CHATTERBOX] Installing dependencies (excluding torch/torchaudio - CUDA version already installed)...")
                        with open(req_file, 'r', encoding='utf-8') as f:
                            req_lines = f.readlines()
                        
                        filtered_reqs = []
                        for line in req_lines:
                            line_lower = line.lower().strip()
                            # Skip torch and torchaudio lines (case-insensitive, handle comments)
                            if line.strip().startswith('#'):
                                continue  # Skip comments
                            if not any(pkg in line_lower for pkg in ['torch', 'torchaudio']):
                                filtered_reqs.append(line.strip())
                        
                        # Install filtered requirements
                        if filtered_reqs:
                            # Write filtered requirements to temp file
                            import tempfile
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp_req:
                                tmp_req.write('\n'.join(filtered_reqs))
                                tmp_req_path = tmp_req.name
                            
                            try:
                                # Stream requirements installation output to stdout
                                req_result = subprocess.run(
                                    [str(python_exe), "-m", "pip", "install", "-r", tmp_req_path],
                                    check=True,
                                    text=True,
                                    timeout=600,
                                    creationflags=creation_flags
                                )
                                
                                # VERIFY CUDA PyTorch is still installed after requirements install
                                verify_cmd = [str(python_exe), "-c", "import torch; print('CUDA_BUILT:', torch.version.cuda if hasattr(torch.version, 'cuda') and torch.version.cuda else 'None'); print('CUDA_AVAILABLE:', torch.cuda.is_available())"]
                                verify_result = subprocess.run(
                                    verify_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                    creationflags=creation_flags
                                )
                                if verify_result.returncode == 0:
                                    if "CUDA_BUILT: None" in verify_result.stdout or "CUDA_AVAILABLE: False" in verify_result.stdout:
                                        print("[CHATTERBOX] ERROR: CUDA PyTorch was overwritten by requirements.txt!")
                                        if pytorch_cmd:
                                            print("[CHATTERBOX] Reinstalling CUDA PyTorch...")
                                            # Reinstall CUDA PyTorch - stream output
                                            subprocess.run(
                                                pytorch_cmd,
                                                check=True,
                                                text=True,
                                                timeout=1800,
                                                creationflags=creation_flags
                                            )
                                            print("[CHATTERBOX] CUDA PyTorch reinstalled")
                                        else:
                                            print("[CHATTERBOX] WARNING: Cannot reinstall CUDA PyTorch (command not available)")
                                    else:
                                        print("[CHATTERBOX] Dependencies installed successfully (CUDA PyTorch preserved)")
                            finally:
                                # Clean up temp file
                                try:
                                    os.unlink(tmp_req_path)
                                except Exception:
                                    pass
                    else:
                        # Install all requirements normally (includes CPU torch) - stream output
                        print("[CHATTERBOX] Installing all dependencies from requirements.txt...")
                        req_result = subprocess.run(
                            [str(python_exe), "-m", "pip", "install", "-r", str(req_file)],
                            check=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                        print("[CHATTERBOX] Dependencies installed successfully")
                else:
                    print(f"[WARNING] requirements.txt not found at {req_file}")
                
                return [sys.executable, "-c", "print('[SUCCESS] Chatterbox installed with CUDA support')"]
            
            # Special handling for LLM service - install prebuilt llama-cpp-python with CUDA
            if service_key == "llm":
                self._print("Installing LLM service with CUDA support (prebuilt wheels)...", "cyan")
                
                # Detect GPU and CUDA version
                cuda_version = "cpu" # Default to CPU
                cuda_index_url = ""
                
                # Check for CUDA
                try:
                    nvcc_result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
                    if nvcc_result.returncode == 0:
                        import re
                        # Parse version
                        # Example: Cuda compilation tools, release 12.4, V12.4.131
                        match = re.search(r"release (\d+)\.(\d+)", nvcc_result.stdout)
                        if match:
                            major, minor = match.groups()
                            major = int(major)
                            minor = int(minor)
                            
                            if major == 12:
                                if minor >= 4:
                                    cuda_version = "cu124"
                                    cuda_index_url = "https://abetlen.github.io/llama-cpp-python/whl/cu124"
                                else:
                                    cuda_version = "cu121"
                                    cuda_index_url = "https://abetlen.github.io/llama-cpp-python/whl/cu121"
                                self._print(f"Detected CUDA {major}.{minor} - using {cuda_version} wheels", "green")
                            elif major == 11:
                                cuda_version = "cu118" # Most common for 11.x
                                cuda_index_url = "https://abetlen.github.io/llama-cpp-python/whl/cu118"
                                self._print(f"Detected CUDA {major}.{minor} - using {cuda_version} wheels", "green")
                            else:
                                self._print(f"Detected CUDA {major}.{minor} - no prebuilt wheels found, falling back to CPU", "yellow")
                        else:
                            self._print("Could not parse CUDA version, falling back to CPU", "yellow")
                    else:
                        self._print("No CUDA compiler found (nvcc), checking nvidia-smi...", "dim")
                        # Fallback to nvidia-smi check
                        nvidia_smi = shutil.which("nvidia-smi")
                        if nvidia_smi:
                            smi_result = subprocess.run([nvidia_smi], capture_output=True, text=True)
                            if smi_result.returncode == 0 and "CUDA Version: 12" in smi_result.stdout:
                                # Assume 12.1 safe fallback for 12.x drivers if nvcc missing
                                cuda_version = "cu121"
                                cuda_index_url = "https://abetlen.github.io/llama-cpp-python/whl/cu121"
                                self._print("Detected CUDA 12 via nvidia-smi - using cu121 wheels", "green")
                except Exception as e:
                    self._print(f"Error detecting CUDA: {e}", "yellow")
                
                # Install llama-cpp-python
                if cuda_index_url:
                    self._print(f"Installing llama-cpp-python from {cuda_index_url}...", "cyan")
                    try:
                        # Uninstall first to be safe
                        subprocess.run(
                            [str(python_exe), "-m", "pip", "uninstall", "llama-cpp-python", "-y"],
                            capture_output=True,
                            creationflags=creation_flags
                        )
                        
                        install_cmd = [
                            str(python_exe), "-m", "pip", "install", 
                            "llama-cpp-python>=0.3.0", 
                            "--extra-index-url", cuda_index_url,
                            "--no-cache-dir",
                            "--force-reinstall"
                        ]
                        
                        result = subprocess.run(
                            install_cmd,
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                        
                        if result.returncode != 0:
                            self._print(f"Failed to install prebuilt wheel: {result.stderr[:500]}", "red")
                            self._print("Falling back to CPU version...", "yellow")
                            cuda_index_url = "" # Trigger CPU fallback
                        else:
                            self._print("Successfully installed llama-cpp-python with CUDA support", "green")
                    except Exception as e:
                        self._print(f"Error installing prebuilt wheel: {e}", "red")
                        cuda_index_url = "" # Trigger CPU fallback
                
                if not cuda_index_url:
                    self._print("Installing CPU-only llama-cpp-python...", "yellow")
                    try:
                        subprocess.run(
                            [str(python_exe), "-m", "pip", "install", "llama-cpp-python>=0.3.0"],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                    except Exception as e:
                        self._print(f"Failed to install llama-cpp-python: {e}", "red")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]

                # Install other requirements (skip llama-cpp-python as we just installed it)
                self._print("Installing other dependencies...", "dim")
                other_deps = []
                if req_file.exists():
                    with open(req_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and 'llama-cpp-python' not in line:
                                other_deps.append(line)
                
                if other_deps:
                    # Create temp requirements file without llama-cpp-python
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                        tmp.write('\n'.join(other_deps))
                        tmp_req = tmp.name
                    
                    try:
                        result = subprocess.run(
                            [str(python_exe), "-m", "pip", "install", "-r", tmp_req],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                    except subprocess.CalledProcessError as e:
                        self._print(f"Failed to install dependencies: {e.stderr[:500] if e.stderr else str(e)}", "red")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
                    finally:
                        if os.path.exists(tmp_req):
                            try:
                                os.remove(tmp_req)
                            except (PermissionError, OSError):
                                pass
            else:
                # For core services, install all core services' requirements
                if is_core:
                    self._print("Installing all core services dependencies (this may take a while)...", "dim")
                    core_req_files = []
                    for core_svc_key in self.core_services:
                        core_svc = self.services[core_svc_key]
                        core_req = core_svc["dir"] / "requirements.txt"
                        if core_req.exists():
                            core_req_files.append(str(core_req))
                    
                    if core_req_files:
                        try:
                            # Install all core services' requirements (always run, pip will skip already installed packages)
                            for req_file_path in core_req_files:
                                self._print(f"Installing dependencies from {Path(req_file_path).name}...", "dim")
                                pip_cmd = [str(python_exe), "-m", "pip", "install", "-r", req_file_path]
                                # Stream output to stdout
                                result = subprocess.run(
                                    pip_cmd,
                                    check=True,
                                    text=True,
                                    timeout=600,
                                    creationflags=creation_flags
                                )
                        except subprocess.CalledProcessError as e:
                            error_msg = e.stderr or e.stdout or str(e)
                            if "Permission denied" in error_msg or "Access is denied" in error_msg:
                                self._print("Permission denied installing dependencies", "red")
                                self._print("Make sure you have write access to the venv directory", "red")
                            else:
                                self._print(f"Failed to install dependencies: {error_msg[:500]}", "red")
                            return [sys.executable, "-c", "import sys; sys.exit(1)"]
                        except subprocess.TimeoutExpired:
                            self._print("Installation timed out", "red")
                            return [sys.executable, "-c", "import sys; sys.exit(1)"]
                else:
                    # Normal installation for other services (always run, pip will skip already installed packages)
                    self._print("Installing dependencies (this may take a while)...", "dim")
                    try:
                        pip_cmd = [str(python_exe), "-m", "pip", "install", "-r", str(req_file)]
                        # Stream output to stdout
                        result = subprocess.run(
                            pip_cmd,
                            check=True,
                            text=True,
                            timeout=600,
                            creationflags=creation_flags
                        )
                    except subprocess.CalledProcessError as e:
                        error_msg = e.stderr or e.stdout or str(e)
                        if "Permission denied" in error_msg or "Access is denied" in error_msg:
                            self._print("Permission denied installing dependencies", "red")
                            self._print("Make sure you have write access to the venv directory", "red")
                        else:
                            self._print(f"Failed to install dependencies: {error_msg[:500]}", "red")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
                    except subprocess.TimeoutExpired:
                        self._print("Installation timed out", "red")
                        return [sys.executable, "-c", "import sys; sys.exit(1)"]
                
        except Exception as e:
            self._print(f"Unexpected error during installation: {e}", "red")
            return [sys.executable, "-c", "import sys; sys.exit(1)"]

        # 3. Copy .env.example -> .env
        env_example = service_dir / ".env.example"
        env_target = service_dir / ".env"
        if env_example.exists() and not env_target.exists():
            print("Copying .env.example to .env")
            try:
                shutil.copy(str(env_example), str(env_target))
            except Exception as e:
                print(f"[WARNING] Failed to copy .env: {e}")
        
        if is_core:
            print(f"[SUCCESS] Core services shared environment installation completed successfully")
        else:
            print(f"[SUCCESS] {service['name']} installation completed successfully")
        # Return a dummy success command since we already did the work
        return [sys.executable, "-c", "print('[SUCCESS] Installation completed')"]

    def _get_external_services_manager(self):
        """Lazy-load external services manager."""
        if self.external_services_mgr is None:
            # Use absolute import to avoid relative import errors
            import sys
            from pathlib import Path
            launcher_dir = Path(__file__).parent
            if str(launcher_dir) not in sys.path:
                sys.path.insert(0, str(launcher_dir))
            from external_services_manager import ExternalServicesManager
            self.external_services_mgr = ExternalServicesManager(self.root_dir)
        return self.external_services_mgr
    
    def _ensure_external_service(self, service_name: str) -> bool:
        """Ensure external service is cloned and configured."""
        service = self.services.get(service_name)
        if not service:
            return False
        
        # Check if it's an external service
        if not service.get("is_external"):
            return True  # Not an external service, nothing to do
        
        repo_url = service.get("repo_url")
        target_dir = service.get("dir")
        
        if not repo_url or not target_dir:
            self._print(f"Missing repo_url or dir for external service {service_name}", "red")
            return False
        
        # Clone the repository if needed
        self._print(f"Ensuring {service_name} is cloned...", "cyan")
        external_mgr = self._get_external_services_manager()
        if not external_mgr.ensure_service_cloned(repo_url, service_name, target_dir):
            self._print(f"Failed to clone {service_name}", "red")
            return False
        
        # Setup the service (create .env, etc.)
        if not external_mgr.setup_service(service_name, target_dir):
            self._print(f"Failed to setup {service_name}", "red")
            return False
        
        self._print(f"External service {service_name} ready", "green")
        return True

    

    def _get_python_exe(self) -> str:
        """Get Python executable path."""
        # Only use venv Python if venv exists and is valid
        if self.check_venv():
            venv_python = self.root_dir / "venv" / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
            if platform.system() == "Windows":
                venv_python = venv_python.with_suffix(".exe")
            if venv_python.exists():
                return str(venv_python)
        # Fall back to system Python
        return sys.executable
    
    def _print(self, message: str, style: str = ""):
        """Print message with optional styling."""
        if self.console:
            self.console.print(message, style=style)
        else:
            print(message)
    
    def _print_panel(self, title: str, content: str, style: str = "blue"):
        """Print a panel."""
        if self.console:
            self.console.print(Panel(content, title=title, border_style=style))
        else:
            print(f"\n{'='*60}")
            print(f"{title}")
            print(f"{'='*60}")
            print(content)
            print(f"{'='*60}\n")
    
    def _print_table(self, title: str, data: List[Dict[str, Any]]):
        """Print a table."""
        if self.console:
            table = Table(title=title, box=box.ROUNDED)
            if data:
                for key in data[0].keys():
                    table.add_column(key.replace("_", " ").title())
                for row in data:
                    table.add_row(*[str(row.get(k, "")) for k in data[0].keys()])
            self.console.print(table)
        else:
            print(f"\n{title}")
            print("-" * 60)
            if data:
                for row in data:
                    for key, value in row.items():
                        print(f"  {key.replace('_', ' ').title()}: {value}")
            print()
    
    def check_python(self) -> Tuple[bool, str]:
        """Check if Python is available."""
        try:
            version = sys.version_info
            version_str = f"{version.major}.{version.minor}.{version.micro}"
            if version.major < 3 or (version.major == 3 and version.minor < 10):
                return False, f"Python {version_str} found, but Python 3.10+ is required"
            return True, version_str
        except Exception as e:
            return False, f"Error checking Python: {e}"

    def find_latest_python(self, max_major=3, max_minor=12):
        candidates = []

        # Windows: Try 'py' launcher first
        if platform.system() == "Windows":
            try:
                # Check available versions via py --list
                result = subprocess.run(["py", "--list"], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        # Output format: " -V:3.12          Python 3.12 (64-bit)"
                        if "-V:" in line:
                            try:
                                ver_part = line.split()[0].split(":")[1] # "3.12"
                                major, minor = map(int, ver_part.split("."))
                                if major == 3 and minor <= max_minor:
                                    # Found a valid version, verify we can use it
                                    py_cmd = f"py -{major}.{minor}"
                                    # Get the actual executable path
                                    path_res = subprocess.run(
                                        ["py", f"-{major}.{minor}", "-c", "import sys; print(sys.executable)"],
                                        capture_output=True,
                                        text=True
                                    )
                                    if path_res.returncode == 0:
                                        exe_path = path_res.stdout.strip()
                                        candidates.append((major, minor, exe_path))
                            except (ValueError, IndexError):
                                continue
            except FileNotFoundError:
                pass

        # Try common executable names (Linux/Mac or Windows fallback)
        for major in range(3, max_major + 1):
            for minor in range(0, max_minor + 1):
                name = f"python{major}.{minor}"
                try:
                    result = subprocess.run(
                        [name, "--version"],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        version_str = result.stdout.strip() or result.stderr.strip()
                        # Confirm version is within limits
                        if version_str.startswith(f"Python {major}.{minor}"):
                            candidates.append((major, minor, name))
                except FileNotFoundError:
                    continue

        # Sort descending and pick highest
        if candidates:
            # Remove duplicates based on path/name
            unique_candidates = {}
            for maj, min_v, path in candidates:
                key = (maj, min_v)
                if key not in unique_candidates:
                    unique_candidates[key] = path
            
            sorted_keys = sorted(unique_candidates.keys(), reverse=True)
            best_ver = sorted_keys[0]
            best_path = unique_candidates[best_ver]
            
            print(f"Using Python {best_ver[0]}.{best_ver[1]} executable: {best_path}")
            return best_path

        # Fallback to current Python
        print(f"No newer Python found, using current: {sys.executable}")
        return sys.executable

    def check_node(self) -> Tuple[bool, str]:
        """Check if Node.js is available."""
        try:
            cmd = ["node", "--version"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, "Node.js not found"
        except FileNotFoundError:
            return False, "Node.js not installed"
        except Exception as e:
            return False, f"Error checking Node.js: {e}"
    
    def check_cuda(self) -> Dict[str, Any]:
        """Check CUDA availability."""
        cuda_info = {
            "nvidia_driver": False,
            "gpu_name": None,
            "cuda_version": None,
            "pytorch_cuda": False,
            "llama_cuda": False
        }
        
        # Check nvidia-smi
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                result = subprocess.run(
                    [nvidia_smi, "--query-gpu=name,driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.strip().split('\n')
                    if lines:
                        parts = lines[0].split(',')
                        cuda_info["nvidia_driver"] = True
                        cuda_info["gpu_name"] = parts[0].strip() if len(parts) > 0 else "Unknown"
                        cuda_info["driver_version"] = parts[1].strip() if len(parts) > 1 else "Unknown"
            except Exception:
                pass
        
        # Check PyTorch CUDA
        try:
            import torch
            if torch.cuda.is_available():
                cuda_info["pytorch_cuda"] = True
                cuda_info["pytorch_cuda_version"] = torch.version.cuda
                cuda_info["gpu_count"] = torch.cuda.device_count()
        except ImportError:
            pass
        except Exception:
            pass
        
        # Check llama-cpp-python CUDA
        try:
            from llama_cpp import llama_cpp
            cuda_info["llama_cuda"] = (
                hasattr(llama_cpp, 'llama_supports_gpu_offload') or
                hasattr(llama_cpp, 'llama_gpu_offload')
            )
        except ImportError:
            pass
        except Exception:
            pass
        
        return cuda_info
    
    def check_venv(self) -> bool:
        """Check if virtual environment exists."""
        venv_path = self.root_dir / "venv"
        if platform.system() == "Windows":
            return (venv_path / "Scripts" / "python.exe").exists()
        return (venv_path / "bin" / "python").exists()
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check if dependencies are installed."""
        deps = {
            "venv": self.check_venv(),
            "backend_deps": False,
            "frontend_deps": False,
            "chatterbox_deps": False
        }
        
        if deps["venv"]:
            python_exe = self._get_python_exe()
            # Check backend dependencies
            try:
                result = subprocess.run(
                    [python_exe, "-c", "import fastapi, uvicorn"],
                    capture_output=True,
                    timeout=5
                )
                deps["backend_deps"] = result.returncode == 0
            except Exception:
                pass
        
        # Check frontend dependencies
        frontend_dir = self.services.get("frontend", {}).get("dir")
        if frontend_dir:
            frontend_node_modules = frontend_dir / "node_modules"
            deps["frontend_deps"] = frontend_node_modules.exists()
        else:
            deps["frontend_deps"] = False
        
        return deps

    def install_service(self, service_name: str) -> bool:
        """Install dependencies for a specific service."""
        if service_name not in self.services:
            self._print(f"Unknown service: {service_name}", "red")
            return False
            
        service = self.services[service_name]
        cmd = service["install_cmd"]()
        
        if not cmd:
            self._print(f"No install command for {service_name}", "yellow")
            return True
            
        self._print(f"Installing {service_name}...", "blue")
        try:
            # Run command (output capture handled by launcher if used through GUI)
            process = subprocess.run(
                cmd,
                cwd=str(service["dir"]),
                check=False,
                shell=True if platform.system() == "Windows" else False
            )
            
            if process.returncode == 0:
                self._print(f"Successfully installed {service_name}", "green")
                return True
            else:
                self._print(f"Failed to install {service_name} (Exit code: {process.returncode})", "red")
                return False
        except Exception as e:
            self._print(f"Error installing {service_name}: {e}", "red")
            return False
    
    def recreate_venv(self) -> bool:
        """Completely recreate the virtual environment from scratch."""
        self._print_panel("Recreating Virtual Environment", "This will delete the existing venv and create a fresh one...")
        
        venv_path = self.root_dir / "venv"
        
        # Check Python
        python_ok, python_version = self.check_python()
        if not python_ok:
            self._print(f"[ERROR] {python_version}", style="red")
            return False
        self._print(f"[OK] Python {python_version} found", style="green")
        
        # Delete existing venv - kill any processes using it first
        if venv_path.exists():
            self._print("Stopping processes that might be using the venv...", style="yellow")
            
            # Kill processes using the venv - wrap in try-except to prevent crashes
            killed_count = 0
            try:
                if HAS_PSUTIL:
                    try:
                        for proc in psutil.process_iter(['pid', 'name', 'exe']):
                            try:
                                exe = proc.info.get('exe', '')
                                if exe and str(venv_path) in exe:
                                    proc_name = proc.info.get('name', 'unknown')
                                    proc_pid = proc.info.get('pid', 'unknown')
                                    self._print(f"Killing process: {proc_name} (PID: {proc_pid})", style="cyan")
                                    try:
                                        proc.kill()
                                        killed_count += 1
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        pass
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError, TypeError, KeyError):
                                pass
                    except Exception as e:
                        self._print(f"[WARNING] Could not kill processes with psutil: {e}", style="yellow")
                
                # Fallback: try to kill Python processes on Windows (more aggressive)
                if platform.system() == "Windows":
                    try:
                        # Try taskkill for Python processes
                        result = subprocess.run(
                            ["taskkill", "/F", "/IM", "python.exe", "/T"], 
                            capture_output=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            killed_count += 1
                        time.sleep(1)
                    except Exception:
                        pass
                
                if killed_count > 0:
                    self._print(f"[OK] Stopped {killed_count} process(es)", style="green")
                    time.sleep(2)  # Wait for processes to fully terminate
                else:
                    self._print("[INFO] No processes found using the venv", style="cyan")
            except Exception as e:
                # Don't fail if process killing fails - just warn and continue
                self._print(f"[WARNING] Error stopping processes: {e}", style="yellow")
                self._print("Continuing with venv deletion anyway...", style="cyan")
            
            self._print("Deleting existing virtual environment...", style="yellow")
            
            # Try multiple deletion methods
            deletion_success = False
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    if platform.system() == "Windows":
                        # Method 1: Use rmdir with retry
                        result = subprocess.run(
                            ["cmd", "/c", "rmdir", "/s", "/q", str(venv_path)],
                            capture_output=True,
                            timeout=30
                        )
                        if result.returncode == 0 or not venv_path.exists():
                            deletion_success = True
                            break
                        
                        # Method 2: Use PowerShell Remove-Item (more robust)
                        if attempt > 0:
                            ps_cmd = f"Remove-Item -Path '{venv_path}' -Recurse -Force -ErrorAction SilentlyContinue"
                            result = subprocess.run(
                                ["powershell", "-Command", ps_cmd],
                                capture_output=True,
                                timeout=30
                            )
                            if not venv_path.exists():
                                deletion_success = True
                                break
                    else:
                        # Unix/Linux/Mac
                        import shutil
                        shutil.rmtree(venv_path, ignore_errors=True)
                        if not venv_path.exists():
                            deletion_success = True
                            break
                    
                    # Wait before retry
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        self._print(f"Retry {attempt + 1}/{max_retries}...", style="yellow")
                        time.sleep(2)
                    else:
                        self._print(f"[WARNING] Could not fully delete venv: {e}", style="yellow")
            
            if not deletion_success and venv_path.exists():
                # Last resort: rename the directory and create new one
                self._print("Could not delete venv, renaming old venv...", style="yellow")
                try:
                    old_venv = self.root_dir / f"venv.old.{int(time.time())}"
                    venv_path.rename(old_venv)
                    self._print(f"[OK] Old venv renamed to {old_venv.name}", style="green")
                    self._print("You can delete it manually later", style="cyan")
                except Exception as e:
                    self._print(f"[ERROR] Could not rename venv: {e}", style="red")
                    self._print("Please close all Python processes and try again", style="yellow")
                    return False
            else:
                self._print("[OK] Old virtual environment deleted", style="green")
        
        # Create fresh venv
        self._print("Creating fresh virtual environment...", style="yellow")
        python_exe = self.find_latest_python(max_major=3, max_minor=12)
        
        # Use --clear flag if venv still exists (will clear it)
        venv_args = [python_exe, "-m", "venv", str(venv_path)]
        if venv_path.exists():
            venv_args.append("--clear")
        
        result = subprocess.run(
            venv_args,
            cwd=str(self.root_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout
            self._print(f"[ERROR] Failed to create virtual environment: {error_msg}", style="red")
            return False
        
        # Verify venv was created
        if not (venv_path / "pyvenv.cfg").exists():
            self._print("[ERROR] Virtual environment created but pyvenv.cfg not found", style="red")
            return False
        
        self._print("[OK] Fresh virtual environment created", style="green")
        return True
    
    def install_dependencies(self, install_cuda: bool = False, recreate_venv: bool = False) -> bool:
        """Install all dependencies."""
        self._print_panel("Installing Dependencies", "This may take several minutes...")
        
        # Check Python
        python_ok, python_version = self.check_python()
        if not python_ok:
            self._print(f"[ERROR] {python_version}", style="red")
            return False
        self._print(f"[OK] Python {python_version} found", style="green")
        
        # Only recreate venv if explicitly requested
        if recreate_venv:
            if not self.recreate_venv():
                return False
        
        # Create venv if it doesn't exist
        if not self.check_venv():
            self._print("Virtual environment not found. Creating new virtual environment...", style="yellow")
            python_exe = sys.executable
            venv_path = self.root_dir / "venv"
            
            # Make sure the directory doesn't exist or is empty
            if venv_path.exists():
                self._print("[WARNING] venv directory exists but is invalid. Removing...", style="yellow")
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["rmdir", "/s", "/q", str(venv_path)], shell=True, timeout=10, capture_output=True)
                    else:
                        import shutil
                        shutil.rmtree(venv_path, ignore_errors=True)
                    time.sleep(1)
                except Exception:
                    pass
            
            result = subprocess.run(
                [python_exe, "-m", "venv", str(venv_path)],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout
                self._print(f"[ERROR] Failed to create virtual environment", style="red")
                self._print(f"Error: {error_msg}", style="red")
                self._print(f"Python executable: {python_exe}", style="yellow")
                self._print(f"Venv path: {venv_path}", style="yellow")
                return False
            
            # Verify venv was created successfully - check multiple things
            venv_valid = True
            venv_python = venv_path / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python")
            pyvenv_cfg = venv_path / "pyvenv.cfg"
            
            if not venv_python.exists():
                self._print(f"[ERROR] Virtual environment Python not found at: {venv_python}", style="red")
                venv_valid = False
            
            if not pyvenv_cfg.exists():
                self._print(f"[ERROR] pyvenv.cfg not found at: {pyvenv_cfg}", style="red")
                venv_valid = False
            
            if not venv_valid:
                self._print("[ERROR] Virtual environment creation incomplete", style="red")
                self._print("Attempting to remove incomplete venv and recreate...", style="yellow")
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["rmdir", "/s", "/q", str(venv_path)], shell=True, timeout=10, capture_output=True)
                    else:
                        import shutil
                        shutil.rmtree(venv_path, ignore_errors=True)
                    time.sleep(1)
                    # Try creating again
                    result2 = subprocess.run(
                        [python_exe, "-m", "venv", str(venv_path)],
                        cwd=str(self.root_dir),
                        capture_output=True,
                        text=True
                    )
                    if result2.returncode == 0 and venv_python.exists() and pyvenv_cfg.exists():
                        self._print("[OK] Virtual environment recreated successfully", style="green")
                    else:
                        self._print("[ERROR] Failed to recreate virtual environment", style="red")
                        return False
                except Exception as e:
                    self._print(f"[ERROR] Failed to recreate venv: {e}", style="red")
                    return False
            else:
                self._print("[OK] Virtual environment created successfully", style="green")
        
        # Get Python executable - verify it exists before using
        python_exe = self._get_python_exe()
        if not Path(python_exe).exists():
            self._print(f"[ERROR] Python executable not found: {python_exe}", style="red")
            self._print("Falling back to system Python...", style="yellow")
            python_exe = sys.executable
        
        # Verify we're using the venv Python if venv exists
        if self.check_venv():
            expected_venv_python = self.root_dir / "venv" / ("Scripts" if platform.system() == "Windows" else "bin") / ("python.exe" if platform.system() == "Windows" else "python")
            if python_exe != str(expected_venv_python) and not Path(python_exe).exists():
                self._print(f"[WARNING] Using system Python instead of venv Python", style="yellow")
                self._print(f"Expected: {expected_venv_python}", style="yellow")
                self._print(f"Using: {python_exe}", style="yellow")
        
        # Upgrade pip
        self._print("Upgrading pip...", style="yellow")
        subprocess.run(
            [python_exe, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            cwd=str(self.root_dir),
            capture_output=True
        )
        
        # Fix corrupted numpy distribution first
        self._print("Checking for corrupted packages...", style="yellow")
        try:
            # Clean up any corrupted distributions
            if platform.system() == "Windows":
                # On Windows, manually remove corrupted numpy directories
                site_packages = self.root_dir / "venv" / "Lib" / "site-packages"
                corrupted_dirs = ["-umpy.dist-info", "umpy.dist-info"]
                for corrupt_dir in corrupted_dirs:
                    corrupt_path = site_packages / corrupt_dir
                    if corrupt_path.exists():
                        try:
                            if platform.system() == "Windows":
                                subprocess.run(["rmdir", "/s", "/q", str(corrupt_path)], shell=True, timeout=10)
                            else:
                                import shutil
                                shutil.rmtree(corrupt_path, ignore_errors=True)
                        except Exception:
                            pass
            
            # Uninstall and reinstall numpy cleanly
            subprocess.run(
                [python_exe, "-m", "pip", "uninstall", "numpy", "-y"],
                cwd=str(self.root_dir),
                capture_output=True,
                timeout=30
            )
            # Wait a moment for cleanup
            time.sleep(1)
            subprocess.run(
                [python_exe, "-m", "pip", "install", "numpy>=1.22.0,<2.0.0", "--force-reinstall", "--no-cache-dir"],
                cwd=str(self.root_dir),
                capture_output=True,
                timeout=120
            )
            self._print("[OK] NumPy fixed", style="green")
        except Exception as e:
            self._print(f"Warning: Could not fix numpy: {e}", style="yellow")
        
        # Install base dependencies (excluding llama-cpp-python if CUDA is needed)
        self._print("Installing base dependencies...", style="yellow")
        requirements = self.root_dir / "requirements.txt"
        if requirements.exists():
            # If installing CUDA, temporarily remove llama-cpp-python from requirements
            # since we'll install it separately with CUDA support
            if install_cuda:
                import tempfile
                with open(requirements, 'r', encoding='utf-8') as f:
                    req_lines = f.readlines()
                
                # Filter out llama-cpp-python line
                filtered_lines = [line for line in req_lines if 'llama-cpp-python' not in line.lower()]
                
                # Create temporary requirements file
                temp_req = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                temp_req.write(''.join(filtered_lines))
                temp_req.close()
                
                try:
                    result = subprocess.run(
                        [python_exe, "-m", "pip", "install", "-r", temp_req.name, "--upgrade"],
                        cwd=str(self.root_dir),
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        self._print(f"[ERROR] Failed to install base dependencies", style="red")
                        if result.stderr:
                            self._print(f"Error: {result.stderr[:500]}", style="red")
                        if result.stdout:
                            # Check for specific error messages
                            if "No pyvenv.cfg file" in result.stdout:
                                self._print("[ERROR] Virtual environment is incomplete. Please recreate it.", style="red")
                                self._print("Try running: python -m venv venv", style="yellow")
                        return False
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(temp_req.name)
                    except Exception:
                        pass
            else:
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", str(requirements), "--upgrade"],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True
                )
            
            if result.returncode != 0:
                self._print("[ERROR] Failed to install base dependencies", style="red")
                if result.stderr:
                    self._print(f"Error: {result.stderr[:500]}", style="red")
                if result.stdout:
                    # Check for specific error messages
                    if "No pyvenv.cfg file" in result.stdout:
                        self._print("[ERROR] Virtual environment is incomplete. Please recreate it.", style="red")
                        self._print("Try running: python -m venv venv", style="yellow")
                return False
        
        # Install CUDA dependencies if requested
        if install_cuda:
            cuda_info = self.check_cuda()
            if cuda_info["nvidia_driver"]:
                self._print("Installing CUDA-enabled packages...", style="yellow")
                
                # First, uninstall any existing CPU-only versions
                self._print("Removing CPU-only packages...", style="yellow")
                subprocess.run(
                    [python_exe, "-m", "pip", "uninstall", "torch", "torchaudio", "llama-cpp-python", "-y"],
                    cwd=str(self.root_dir),
                    capture_output=True
                )
                
                # Install PyTorch with CUDA FIRST (before other packages that depend on it)
                self._install_pytorch_cuda(python_exe)
                
                # Verify PyTorch CUDA works
                self._print("Verifying PyTorch CUDA...", style="yellow")
                try:
                    verify_result = subprocess.run(
                        [python_exe, "-c", "import torch; print('CUDA available:', torch.cuda.is_available()); print('CUDA version:', torch.version.cuda if torch.cuda.is_available() else 'N/A')"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if verify_result.returncode == 0:
                        self._print(verify_result.stdout.strip(), style="cyan")
                        if "CUDA available: True" in verify_result.stdout:
                            self._print("[OK] PyTorch CUDA verified", style="green")
                        else:
                            self._print("[WARNING] PyTorch CUDA not available", style="yellow")
                except Exception as e:
                    self._print(f"[WARNING] Could not verify PyTorch CUDA: {e}", style="yellow")
                
                # Install llama-cpp-python with CUDA
                self._install_llama_cuda(python_exe)
            else:
                self._print("[WARNING] No CUDA GPU detected, skipping CUDA installations", style="yellow")
        
        # Install frontend dependencies
        self._print("Installing frontend dependencies...", style="yellow")
        frontend_dir = self.root_dir / "frontend-next"
        if frontend_dir.exists():
            node_ok, node_version = self.check_node()
            if node_ok:
                if platform.system() == "Windows":
                    npm_cmd = "npm.cmd"
                else:
                    npm_cmd = "npm"
                result = subprocess.run(
                    [npm_cmd, "install"],
                    cwd=str(frontend_dir),
                    capture_output=False
                )
                if result.returncode == 0:
                    self._print("[OK] Frontend dependencies installed", style="green")
            else:
                self._print(f"[WARNING] {node_version}, skipping frontend dependencies", style="yellow")
        
        self._print_panel("Installation Complete", "All dependencies have been installed successfully!", style="green")
        return True
    
    def _install_pytorch_cuda(self, python_exe: str):
        """Install PyTorch with CUDA support."""
        self._print("Installing PyTorch with CUDA...", style="yellow")
        # Detect CUDA version
        cuda_index = "https://download.pytorch.org/whl/cu121"  # Default to CUDA 12.1
        
        nvcc = shutil.which("nvcc")
        if nvcc:
            try:
                result = subprocess.run(
                    [nvcc, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    import re
                    match = re.search(r'release\s+(\d+)\.(\d+)', result.stdout, re.IGNORECASE)
                    if match:
                        major, minor = match.groups()
                        if major == "11" and minor == "8":
                            cuda_index = "https://download.pytorch.org/whl/cu118"
            except Exception:
                pass
        
        subprocess.run(
            [python_exe, "-m", "pip", "install", "torch>=2.0.0,<2.7.0", "torchaudio>=2.0.0,<2.7.0",
             "--index-url", cuda_index],
            cwd=str(self.root_dir),
            capture_output=False
        )
    
    def _verify_llama_cuda(self, python_exe: str) -> bool:
        """Verify if llama-cpp-python has CUDA support."""
        try:
            # More comprehensive CUDA check
            test_code = """
import sys
try:
    from llama_cpp import llama_cpp
    # Check for CUDA support attributes
    has_cuda = (
        hasattr(llama_cpp, 'llama_supports_gpu_offload') or
        hasattr(llama_cpp, 'llama_gpu_offload') or
        hasattr(llama_cpp, 'llama_supports_cublas') or
        hasattr(llama_cpp, 'llama_cublas_init')
    )
    if has_cuda:
        # Try to actually initialize CUDA to verify it works
        try:
            # This will fail if CUDA is not actually available
            import torch
            if torch.cuda.is_available():
                print('CUDA: True')
                sys.exit(0)
        except:
            pass
    print('CUDA: False')
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
"""
            test_result = subprocess.run(
                [python_exe, "-c", test_code],
                capture_output=True,
                text=True,
                timeout=15
            )
            return test_result.returncode == 0 and 'CUDA: True' in test_result.stdout
        except Exception:
            return False
    
    def _install_llama_cuda(self, python_exe: str):
        """Install llama-cpp-python with CUDA support."""
        self._print("Installing llama-cpp-python with CUDA...", style="yellow")
        
        # Check current version first
        current_version = None
        try:
            result = subprocess.run(
                [python_exe, "-m", "pip", "show", "llama-cpp-python"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                import re
                version_match = re.search(r'Version:\s+(\S+)', result.stdout)
                if version_match:
                    current_version = version_match.group(1)
                    self._print(f"Current version: {current_version}", style="cyan")
                    
                    # Check if CUDA is already available
                    if self._verify_llama_cuda(python_exe):
                        self._print("[OK] llama-cpp-python already has CUDA support", style="green")
                        return
        except Exception as e:
            self._print(f"Warning: Could not check current version: {e}", style="yellow")
        
        # Uninstall existing version
        self._print("Uninstalling existing llama-cpp-python...", style="yellow")
        subprocess.run(
            [python_exe, "-m", "pip", "uninstall", "llama-cpp-python", "-y"],
            cwd=str(self.root_dir),
            capture_output=True
        )
        
        # Detect CUDA version for proper installation
        cuda_version = None
        cuda_major = None
        cuda_minor = None
        nvcc = shutil.which("nvcc")
        if nvcc:
            try:
                result = subprocess.run([nvcc, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    import re
                    match = re.search(r'release\s+(\d+)\.(\d+)', result.stdout, re.IGNORECASE)
                    if match:
                        major, minor = match.groups()
                        cuda_version = f"{major}.{minor}"
                        cuda_major = major
                        cuda_minor = minor
                        self._print(f"Detected CUDA version: {cuda_version}", style="cyan")
            except Exception:
                pass
        
        # Set environment variables for CUDA compilation (fallback method)
        env = os.environ.copy()
        env["CMAKE_ARGS"] = "-DLLAMA_CUBLAS=on"
        env["FORCE_CMAKE"] = "1"
        
        # Try multiple installation methods
        installation_success = False
        
        # Method 1: Official extra-index-url method (RECOMMENDED)
        # See: https://github.com/abetlen/llama-cpp-python#installation-with-cuda
        if cuda_major:
            # Map CUDA version to wheel index version
            # Official wheels use format: cu118, cu121, cu123, etc.
            cuda_wheel_version = None
            if cuda_major == "12":
                if cuda_minor in ["3", "4", "5", "6", "7", "8", "9"]:
                    cuda_wheel_version = "cu123"  # CUDA 12.3+
                elif cuda_minor in ["1", "2"]:
                    cuda_wheel_version = "cu121"  # CUDA 12.1-12.2
                else:
                    cuda_wheel_version = "cu121"  # Default for CUDA 12.x
            elif cuda_major == "11":
                if cuda_minor == "8":
                    cuda_wheel_version = "cu118"  # CUDA 11.8
                else:
                    cuda_wheel_version = "cu118"  # Default for CUDA 11.x
            
            if cuda_wheel_version:
                self._print(f"Method 1: Installing from official CUDA wheels (CUDA {cuda_wheel_version})...", style="yellow")
                self._print("Using official extra-index-url method", style="cyan")
                
                extra_index_url = f"https://abetlen.github.io/llama-cpp-python/whl/{cuda_wheel_version}"
                
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "llama-cpp-python", 
                     "--extra-index-url", extra_index_url, "--no-cache-dir", "--upgrade"],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode == 0:
                    if self._verify_llama_cuda(python_exe):
                        self._print("[OK] Official CUDA wheel installed successfully!", style="green")
                        installation_success = True
                    else:
                        self._print("[WARNING] Wheel installed but CUDA support not verified", style="yellow")
                        # Check stderr for clues
                        if result.stderr and "not found" in result.stderr.lower():
                            self._print(f"Wheel not found for CUDA {cuda_wheel_version}, trying alternatives...", style="yellow")
                else:
                    self._print(f"[WARNING] Official wheel installation failed: {result.stderr[:200]}", style="yellow")
        
        # Method 2: Try alternative CUDA versions if primary failed
        if not installation_success and cuda_major:
            self._print("Method 2: Trying alternative CUDA wheel versions...", style="yellow")
            alternative_versions = []
            
            if cuda_major == "12":
                alternative_versions = ["cu123", "cu121", "cu118"]
            elif cuda_major == "11":
                alternative_versions = ["cu118"]
            else:
                alternative_versions = ["cu123", "cu121", "cu118"]  # Try all if unknown
            
            for alt_version in alternative_versions:
                if installation_success:
                    break
                    
                extra_index_url = f"https://abetlen.github.io/llama-cpp-python/whl/{alt_version}"
                self._print(f"Trying CUDA {alt_version}...", style="cyan")
                
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "llama-cpp-python", 
                     "--extra-index-url", extra_index_url, "--no-cache-dir", "--upgrade"],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode == 0:
                    if self._verify_llama_cuda(python_exe):
                        self._print(f"[OK] CUDA {alt_version} wheel installed successfully!", style="green")
                        installation_success = True
                        break
        
        # Method 3: Try installing latest version (may have CUDA built-in)
        if not installation_success:
            self._print("Method 3: Installing latest version (may have CUDA built-in)...", style="yellow")
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "llama-cpp-python", "--upgrade", "--no-cache-dir"],
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                if self._verify_llama_cuda(python_exe):
                    self._print("[OK] Latest version installed with CUDA support!", style="green")
                    installation_success = True
        
        # Method 4: Try compiling from source with CUDA flags (requires build tools)
        if not installation_success:
            self._print("Method 4: Compiling from source with CUDA support...", style="yellow")
            self._print("This requires Visual Studio Build Tools and may take 10-15 minutes...", style="cyan")
            
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "llama-cpp-python", "--no-cache-dir", "--force-reinstall", "--no-binary=llama-cpp-python"],
                cwd=str(self.root_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout for compilation
            )
            
            if result.returncode == 0:
                if self._verify_llama_cuda(python_exe):
                    self._print("[OK] llama-cpp-python compiled with CUDA support!", style="green")
                    installation_success = True
                else:
                    # Check if compilation actually succeeded but CUDA wasn't enabled
                    if "CMAKE" in result.stdout or "cmake" in result.stdout.lower():
                        self._print("[WARNING] Compiled but CUDA support not detected", style="yellow")
                        self._print("This may mean CUDA libraries weren't found during compilation", style="yellow")
        
        # Final fallback - install CPU version to avoid breaking the system
        if not installation_success:
            self._print("All CUDA methods failed, installing CPU version as fallback...", style="yellow")
            subprocess.run(
                [python_exe, "-m", "pip", "install", "llama-cpp-python==0.2.20", "--no-cache-dir"],
                cwd=str(self.root_dir),
                capture_output=True
            )
            self._print("[WARNING] Installed CPU-only version. For CUDA support:", style="yellow")
            self._print("Option A: Install Visual Studio Build Tools + CUDA Toolkit, then re-run this installer", style="cyan")
            self._print("Option B: Use pre-built wheels from:", style="cyan")
            self._print("  https://github.com/jllllll/llama-cpp-python-cuBLAS-wheels/releases", style="cyan")
            self._print("  Download the wheel matching your Python and CUDA version, then:", style="cyan")
            self._print("  pip install <wheel_file>.whl", style="cyan")
        
        if installation_success:
            self._print("[OK] llama-cpp-python with CUDA support installed successfully!", style="green")
        else:
            self._print("[WARNING] CUDA installation failed, using CPU version", style="yellow")
    
    def check_service_health(self, service_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Check health of a service."""
        service = self.services.get(service_id)
        if not service:
            return False, {"error": "Unknown service"}
        
        # Check if port is open
        port_open = self._check_port(service["port"])
        
        info = {
            "port_open": port_open,
            "status": "running" if port_open else "stopped"
        }
        
        # Try health endpoint if available
        if service["health_endpoint"] and port_open:
            try:
                import urllib.request
                import urllib.error
                url = f"{service['url']}{service['health_endpoint']}"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        info["health_check"] = "ok"
                        try:
                            data = json.loads(response.read().decode())
                            info["health_data"] = data
                        except Exception:
                            pass
            except Exception as e:
                info["health_check"] = f"error: {str(e)}"
        
        return port_open, info
    
    def _check_port(self, port: int) -> bool:
        """Check if a port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def start_service(self, service_id: str, background: bool = True) -> bool:
        """Start a service."""
        service = self.services.get(service_id)
        if not service:
            self._print(f"[ERROR] Unknown service: {service_id}", style="red")
            return False
        
        # Check if already running
        is_running, _ = self.check_service_health(service_id)
        if is_running:
            self._print(f"[INFO] {service['name']} is already running", style="yellow")
            return True
        
        self._print(f"Starting {service['name']}...", style="yellow")
        
        # Get start command
        cmd = service["start_cmd"]()
        
        # Set up environment
        env = os.environ.copy()
        if service["venv"] and service["venv"].exists():
            if platform.system() == "Windows":
                venv_bin = service["venv"] / "Scripts"
            else:
                venv_bin = service["venv"] / "bin"
            env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
        
        # Start process
        try:
            if background:
                if platform.system() == "Windows":
                    # On Windows, hide console window - logs go to launcher GUI
                    creation_flags = subprocess.CREATE_NO_WINDOW
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(service["dir"]),
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        creationflags=creation_flags
                    )
                    if service_id == "backend":
                        self._print("Backend starting (check launcher logs for output).", style="cyan")
                        self._print("Backend may take 15-30 seconds to fully initialize.", style="cyan")
                else:
                    # On Unix, run in background
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(service["dir"]),
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
            else:
                # Run in foreground
                process = subprocess.Popen(
                    cmd,
                    cwd=str(service["dir"]),
                    env=env
                )
            
            self.processes[service_id] = process
            self.service_status[service_id] = ServiceStatus.STARTING
            
            # Wait longer for backend to start (it needs to import modules, initialize services, etc.)
            wait_time = 10 if service_id == "backend" else 5
            self._print(f"Waiting {wait_time} seconds for {service['name']} to start...", style="cyan")
            time.sleep(wait_time)
            
            # Check if process is still alive first
            if process.poll() is not None:
                # Process exited - check exit code
                exit_code = process.returncode
                self.service_status[service_id] = ServiceStatus.ERROR
                self._print(f"[ERROR] {service['name']} process exited immediately with code {exit_code}", style="red")
                
                # Try to read log file if it exists
                log_file = self.root_dir / f"{service_id}_startup.log"
                if log_file.exists():
                    try:
                        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                            log_content = f.read()
                            if log_content:
                                self._print("Last log output:", style="yellow")
                                # Show last 20 lines
                                lines = log_content.strip().split('\n')
                                for line in lines[-20:]:
                                    self._print(f"  {line}", style="yellow")
                    except Exception:
                        pass
                
                return False
            
            # Check if service is responding
            is_running, info = self.check_service_health(service_id)
            if is_running:
                self.service_status[service_id] = ServiceStatus.RUNNING
                self.service_info[service_id] = info
                self._print(f"[OK] {service['name']} started successfully", style="green")
                return True
            else:
                # Process is still running but not responding yet - give it more time
                if process.poll() is None:
                    self._print(f"[INFO] {service['name']} is starting but not responding yet...", style="yellow")
                    self._print("This is normal - backend may take 15-30 seconds to fully initialize", style="cyan")
                    # Wait a bit more and check again
                    time.sleep(5)
                    is_running, info = self.check_service_health(service_id)
                    if is_running:
                        self.service_status[service_id] = ServiceStatus.RUNNING
                        self.service_info[service_id] = info
                        self._print(f"[OK] {service['name']} is now responding", style="green")
                        return True
                    else:
                        self.service_status[service_id] = ServiceStatus.STARTING
                        self._print(f"[INFO] {service['name']} is still starting (check console window for progress)", style="yellow")
                        return True  # Return True anyway - process is running
                else:
                    # Process died
                    exit_code = process.returncode
                    self.service_status[service_id] = ServiceStatus.ERROR
                    self._print(f"[ERROR] {service['name']} failed to start (exited with code {exit_code})", style="red")
                    
                    # Try to read log file if it exists
                    log_file = self.root_dir / f"{service_id}_startup.log"
                    if log_file.exists():
                        try:
                            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                                log_content = f.read()
                                if log_content:
                                    self._print("Error log:", style="yellow")
                                    lines = log_content.strip().split('\n')
                                    for line in lines[-30:]:  # Show last 30 lines
                                        if 'error' in line.lower() or 'exception' in line.lower() or 'traceback' in line.lower():
                                            self._print(f"  {line}", style="red")
                                        else:
                                            self._print(f"  {line}", style="yellow")
                        except Exception:
                            pass
                    
                    return False
        except Exception as e:
            self._print(f"[ERROR] Failed to start {service['name']}: {e}", style="red")
            self._print(f"Command: {' '.join(cmd)}", style="yellow")
            self._print(f"Working directory: {service['dir']}", style="yellow")
            self.service_status[service_id] = ServiceStatus.ERROR
            return False
    
    def stop_service(self, service_id: str) -> bool:
        """Stop a service with graceful shutdown procedure."""
        service = self.services.get(service_id)
        if not service:
            return False
        
        # Stop process if we have it
        if service_id in self.processes:
            process = self.processes[service_id]
            try:
                # Step 1: Send graceful shutdown signal (like Ctrl+C)
                if platform.system() == "Windows":
                    self._print(f"Sending shutdown signal to {service['name']}...", style="yellow")
                    process.terminate()  # SIGTERM on Windows
                else:
                    # On Unix, send SIGINT (Ctrl+C equivalent)
                    self._print(f"Sending SIGINT to {service['name']}...", style="yellow")
                    process.send_signal(signal.SIGINT)
                
                # Step 2: Wait for graceful shutdown (10 seconds)
                try:
                    process.wait(timeout=10)
                    self._print(f"{service['name']} shut down gracefully", style="green")
                except subprocess.TimeoutExpired:
                    # Step 3: Force kill if graceful shutdown times out
                    self._print(f"{service['name']} did not shut down gracefully, force killing...", style="yellow")
                    process.kill()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._print(f"Warning: {service['name']} process may still be running", style="red")
            except Exception as e:
                self._print(f"Error during shutdown: {e}", style="red")
            
            del self.processes[service_id]
        
        # Step 4: Verify port is freed and force kill any stragglers
        if HAS_PSUTIL:
            try:
                killed_any = False
                for proc in psutil.process_iter(['pid', 'name', 'connections']):
                    try:
                        for conn in proc.info['connections'] or []:
                            if conn.laddr.port == service["port"]:
                                if not killed_any:
                                    self._print(f"Warning: Found straggler process on port {service['port']}", style="yellow")
                                    killed_any = True
                                proc_obj = psutil.Process(proc.info['pid'])
                                proc_obj.kill()
                                try:
                                    proc_obj.wait(timeout=2)
                                except psutil.TimeoutExpired:
                                    pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                
                if not killed_any:
                    self._print(f"Port {service['port']} is now free", style="green")
            except Exception as e:
                self._print(f"Warning: Error checking port: {e}", style="yellow")
        
        self.service_status[service_id] = ServiceStatus.STOPPED
        self._print(f"[OK] {service['name']} stopped", style="green")
        return True
    
    def install_chatterbox(self) -> bool:
        """Install Chatterbox TTS API."""
        self._print("Installing Chatterbox TTS API...", style="yellow")
        try:
            # Try to use the backend service if available
            try:
                from backend.src.services.external.chatterbox_service import chatterbox_service
                import asyncio
                result = asyncio.run(chatterbox_service.install())
                if result.get("status") == "success":
                    self._print("[OK] Chatterbox TTS API installed", style="green")
                    return True
                else:
                    self._print(f"[ERROR] Installation failed: {result.get('message', 'Unknown error')}", style="red")
                    return False
            except ImportError:
                # Fallback: manually install using the test script or direct installation
                chatterbox_dir = self.root_dir / "chatterbox-tts-api"
                if not chatterbox_dir.exists():
                    self._print("[ERROR] Chatterbox TTS API directory not found", style="red")
                    return False
                
                # Check for test script
                test_script = chatterbox_dir / ("test_chatterbox.ps1" if platform.system() == "Windows" else "test_chatterbox.sh")
                if test_script.exists():
                    self._print("Using test script for installation...", style="yellow")
                    if platform.system() == "Windows":
                        result = subprocess.run(
                            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(test_script), "-Install"],
                            cwd=str(chatterbox_dir)
                        )
                    else:
                        result = subprocess.run(
                            ["bash", str(test_script), "--install"],
                            cwd=str(chatterbox_dir)
                        )
                    return result.returncode == 0
                else:
                    # Manual installation
                    venv_dir = chatterbox_dir / ".venv"
                    if not venv_dir.exists():
                        python_exe = sys.executable
                        subprocess.run([python_exe, "-m", "venv", str(venv_dir)], cwd=str(chatterbox_dir))
                    
                    if platform.system() == "Windows":
                        venv_python = venv_dir / "Scripts" / "python.exe"
                    else:
                        venv_python = venv_dir / "bin" / "python"
                    
                    if venv_python.exists():
                        # Install dependencies
                        requirements = chatterbox_dir / "requirements.txt"
                        if requirements.exists():
                            result = subprocess.run(
                                [str(venv_python), "-m", "pip", "install", "-r", str(requirements)],
                                cwd=str(chatterbox_dir)
                            )
                            if result.returncode == 0:
                                self._print("[OK] Chatterbox TTS API installed", style="green")
                                return True
                    self._print("[ERROR] Failed to install Chatterbox TTS API", style="red")
                    return False
        except Exception as e:
            self._print(f"[ERROR] Installation error: {e}", style="red")
            return False
    
    def install_service(self, service_id: str) -> bool:
        """Install a specific service."""
        if service_id not in self.services:
            self._print(f"[ERROR] Unknown service: {service_id}", style="red")
            return False
        
        service = self.services[service_id]
        self._print(f"Installing {service['name']}...", style="yellow")
        
        try:
            cmd = service["install_cmd"]()
            if not cmd:
                 self._print(f"[ERROR] No install command for {service['name']}", style="red")
                 return False
                 
            # Run the command
            # Use service directory as CWD
            cwd = service["dir"]
            if not cwd.exists():
                self._print(f"[ERROR] Service directory not found: {cwd}", style="red")
                return False
                
            if isinstance(cmd, str):
                result = subprocess.run(cmd, cwd=str(cwd), shell=True)
            else:
                result = subprocess.run(cmd, cwd=str(cwd))
                
            if result.returncode == 0:
                self._print(f"[OK] {service['name']} installed", style="green")
                return True
            else:
                self._print(f"[ERROR] Failed to install {service['name']} (Exit code: {result.returncode})", style="red")
                return False
        except Exception as e:
             self._print(f"[ERROR] Installation failed: {e}", style="red")
             return False

    def run_tests(self, test_type: str = "all") -> bool:
        """Run tests."""
        self._print_panel("Running Tests", f"Test type: {test_type}")
        
        python_exe = self._get_python_exe()
        test_dir = self.root_dir / "backend" / "tests"
        
        if test_type == "all":
            cmd = [python_exe, "-m", "pytest", str(test_dir), "-v"]
        elif test_type == "quick":
            cmd = [python_exe, "-m", "pytest", str(test_dir), "-v", "-m", "not slow"]
        else:
            cmd = [python_exe, "-m", "pytest", str(test_dir), "-v", "-k", test_type]
        
        result = subprocess.run(cmd, cwd=str(self.root_dir))
        return result.returncode == 0
    
    def show_status(self):
        """Show status of all services."""
        status_data = []
        
        for service_id, service in self.services.items():
            is_running, info = self.check_service_health(service_id)
            status = "🟢 Running" if is_running else "🔴 Stopped"
            
            status_data.append({
                "Service": service["name"],
                "Status": status,
                "Port": str(service["port"]),
                "URL": service["url"]
            })
        
        self._print_table("Service Status", status_data)
        
        # Show system info
        python_ok, python_version = self.check_python()
        node_ok, node_version = self.check_node()
        cuda_info = self.check_cuda()
        deps = self.check_dependencies()
        
        system_data = [
            {"Component": "Python", "Status": f"✅ {python_version}" if python_ok else "❌ Not found"},
            {"Component": "Node.js", "Status": f"✅ {node_version}" if node_ok else "❌ Not found"},
            {"Component": "Virtual Environment", "Status": "✅ Installed" if deps["venv"] else "❌ Not found"},
            {"Component": "Backend Dependencies", "Status": "✅ Installed" if deps["backend_deps"] else "❌ Not installed"},
            {"Component": "Frontend Dependencies", "Status": "✅ Installed" if deps["frontend_deps"] else "❌ Not installed"},
            {"Component": "Chatterbox Dependencies", "Status": "✅ Installed" if deps["chatterbox_deps"] else "❌ Not installed"},
        ]
        
        if cuda_info["nvidia_driver"]:
            system_data.append({
                "Component": "CUDA GPU",
                "Status": f"✅ {cuda_info.get('gpu_name', 'Unknown')}"
            })
            system_data.append({
                "Component": "PyTorch CUDA",
                "Status": "✅ Available" if cuda_info["pytorch_cuda"] else "❌ Not available"
            })
            system_data.append({
                "Component": "llama-cpp CUDA",
                "Status": "✅ Available" if cuda_info["llama_cuda"] else "❌ Not available"
            })
        
        self._print_table("System Information", system_data)
    
    def interactive_menu(self):
        """Show interactive menu."""
        while True:
            self._print_panel("Personal Assistant Manager", "Main Menu", style="blue")
            
            menu_items = [
                "1. Show Status",
                "2. Install Dependencies",
                "3. Install CUDA Dependencies",
                "4. Install Chatterbox TTS API",
                "5. Start Backend",
                "6. Start Frontend",
                "7. Start Chatterbox TTS",
                "8. Start All Services",
                "9. Stop Backend",
                "10. Stop Frontend",
                "11. Stop Chatterbox TTS",
                "12. Stop All Services",
                "13. Run Tests",
                "14. Health Check",
                "15. Open Services in Browser",
                "16. Build Frontend",
                "0. Exit"
            ]
            
            for item in menu_items:
                self._print(f"  {item}")
            
            if HAS_RICH:
                choice = Prompt.ask("\nSelect option", default="1")
            else:
                choice = input("\nSelect option [1]: ").strip() or "1"
            
            if choice == "0":
                self._print("Exiting...", style="yellow")
                self.stop_all_services()
                break
            elif choice == "1":
                self.show_status()
            elif choice == "2":
                self.install_dependencies(install_cuda=False)
            elif choice == "3":
                # Install CUDA dependencies (reinstall packages, don't recreate venv)
                self.install_dependencies(install_cuda=True, recreate_venv=False)
            elif choice == "4":
                self.install_chatterbox()
            elif choice == "5":
                self.start_service("backend")
            elif choice == "6":
                self.start_service("frontend")
            elif choice == "7":
                self.start_service("chatterbox")
            elif choice == "8":
                self.start_all_services()
            elif choice == "9":
                self.stop_service("backend")
            elif choice == "10":
                self.stop_service("frontend")
            elif choice == "11":
                self.stop_service("chatterbox")
            elif choice == "12":
                self.stop_all_services()
            elif choice == "13":
                test_type = Prompt.ask("Test type", choices=["all", "quick", "api", "llm"], default="all") if HAS_RICH else input("Test type [all]: ").strip() or "all"
                self.run_tests(test_type)
            elif choice == "14":
                self.health_check_all()
            elif choice == "15":
                self.open_services_in_browser()
            elif choice == "16":
                self.build_frontend()
            else:
                self._print("Invalid option", style="red")
            
            if choice != "0":
                input("\nPress Enter to continue...")
    
    def start_all_services(self):
        """Start all services."""
        self._print_panel("Starting All Services", "Starting backend, frontend, and Chatterbox TTS...")
        
        # Start backend first
        self.start_service("backend", background=True)
        time.sleep(3)
        
        # Start Chatterbox
        self.start_service("chatterbox", background=True)
        time.sleep(2)
        
        # Start frontend last
        self.start_service("frontend", background=True)
        
        self._print_panel("Services Started", "All services are starting. Check status to verify they're running.")
    
    def stop_all_services(self):
        """Stop all services."""
        self._print("Stopping all services...", style="yellow")
        for service_id in list(self.processes.keys()):
            self.stop_service(service_id)
        self._print("[OK] All services stopped", style="green")
    
    def health_check_all(self):
        """Perform health check on all services."""
        self._print_panel("Health Check", "Checking all services...")
        
        for service_id, service in self.services.items():
            is_running, info = self.check_service_health(service_id)
            status_icon = "🟢" if is_running else "🔴"
            self._print(f"{status_icon} {service['name']}: {'Running' if is_running else 'Stopped'}")
            if is_running and "health_data" in info:
                health = info["health_data"]
                if "device" in health:
                    self._print(f"   Device: {health['device']}")
                if "status" in health:
                    self._print(f"   Status: {health['status']}")
    
    def open_services_in_browser(self):
        """Open all running services in browser."""
        for service_id, service in self.services.items():
            is_running, _ = self.check_service_health(service_id)
            if is_running:
                try:
                    webbrowser.open(service["url"])
                    time.sleep(0.5)  # Small delay between opens
                except Exception as e:
                    self._print(f"Failed to open {service['url']}: {e}", style="yellow")
    
    def build_frontend(self) -> bool:
        """Build frontend for production."""
        self._print("Building frontend for production...", style="yellow")
        frontend_dir = self.root_dir / "frontend-next"
        
        if not frontend_dir.exists():
            self._print("[ERROR] Frontend directory not found", style="red")
            return False
        
        node_ok, node_version = self.check_node()
        if not node_ok:
            self._print(f"[ERROR] {node_version}", style="red")
            return False
        
        if platform.system() == "Windows":
            npm_cmd = "npm.cmd"
        else:
            npm_cmd = "npm"
        
        # Install dependencies if needed
        if not (frontend_dir / "node_modules").exists():
            self._print("Installing frontend dependencies...", style="yellow")
            result = subprocess.run(
                [npm_cmd, "install"],
                cwd=str(frontend_dir),
                capture_output=False
            )
            if result.returncode != 0:
                self._print("[ERROR] Failed to install frontend dependencies", style="red")
                return False
        
        # Build
        self._print("Running production build...", style="yellow")
        result = subprocess.run(
            [npm_cmd, "run", "build"],
            cwd=str(frontend_dir),
            capture_output=False
        )
        
        if result.returncode == 0:
            self._print("[OK] Frontend built successfully", style="green")
            self._print("Output: frontend-next/.next", style="cyan")
            return True
        else:
            self._print("[ERROR] Frontend build failed", style="red")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Personal Assistant Unified Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manager.py                    # Interactive mode
  python manager.py --status           # Show status
  python manager.py --install          # Install dependencies
  python manager.py --install-cuda     # Install with CUDA support
  python manager.py --start backend    # Start backend service
  python manager.py --start all        # Start all services
  python manager.py --stop all         # Stop all services
  python manager.py --test             # Run tests
  python manager.py --health           # Health check
        """
    )
    
    parser.add_argument("--status", action="store_true", help="Show status of all services")
    parser.add_argument("--install", type=str, nargs="?", const="all", metavar="SERVICE", help="Install dependencies (all or specific service)")
    parser.add_argument("--install-cuda", action="store_true", help="Install dependencies with CUDA support")
    # parser.add_argument("--install-chatterbox", action="store_true", help="Install Chatterbox TTS API") # Deprecated
    parser.add_argument("--start", type=str, metavar="SERVICE", help="Start service (backend, frontend, chatterbox, all)")
    parser.add_argument("--stop", type=str, metavar="SERVICE", help="Stop service (backend, frontend, chatterbox, all)")
    parser.add_argument("--test", type=str, nargs="?", const="all", metavar="TYPE", help="Run tests (all, quick, api, llm)")
    parser.add_argument("--health", action="store_true", help="Perform health check")
    parser.add_argument("--open", action="store_true", help="Open services in browser")
    parser.add_argument("--build-frontend", action="store_true", help="Build frontend for production")
    
    args = parser.parse_args()
    
    manager = ServiceManager()
    
    # Non-interactive mode
    if args.status:
        manager.show_status()
    elif args.install:
        if args.install == "all":
            manager.install_dependencies(install_cuda=False)
        else:
            manager.install_service(args.install)
    elif args.install_cuda:
        manager.install_dependencies(install_cuda=True, recreate_venv=False)
    # elif args.install_chatterbox:
    #     manager.install_chatterbox()
    elif args.start:
        if args.start == "all":
            manager.start_all_services()
        else:
            manager.start_service(args.start)
    elif args.stop:
        if args.stop == "all":
            manager.stop_all_services()
        else:
            manager.stop_service(args.stop)
    elif args.test:
        manager.run_tests(args.test)
    elif args.health:
        manager.health_check_all()
    elif args.open:
        manager.open_services_in_browser()
    elif args.build_frontend:
        manager.build_frontend()
    else:
        # Interactive mode
        manager.interactive_menu()


if __name__ == "__main__":
    main()

