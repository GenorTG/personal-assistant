"""Chatterbox CUDA installation module."""

import platform
import subprocess
import shutil
import re
import threading
from pathlib import Path
from typing import Optional


class ChatterboxCudaInstaller:
    """Handles CUDA installation for Chatterbox TTS."""
    
    def __init__(self, app, service_manager):
        self.app = app
        self.service_manager = service_manager
    
    def install(self):
        """Install PyTorch with CUDA support for Chatterbox TTS."""
        def _run():
            service_name = "chatterbox"
            self.app.ui_logger.log_to_launcher(f"\n--- Installing CUDA Support for {service_name} ---")
            
            # Disable button during installation
            if service_name in self.app.services_ui:
                install_cuda_btn = self.app.services_ui[service_name].get("install_cuda_btn")
                if install_cuda_btn:
                    install_cuda_btn.configure(state="disabled")
            
            try:
                creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                
                # Check for CUDA GPU
                if not self._check_cuda_gpu(service_name, creation_flags):
                    return
                
                # Get Python executable
                python_exe = self._get_python_exe(service_name, creation_flags)
                if not python_exe:
                    return
                
                # Ensure pip is available
                if not self._ensure_pip(service_name, python_exe, creation_flags):
                    return
                
                # Check current PyTorch
                pytorch_has_cuda = self._check_pytorch_cuda(service_name, python_exe, creation_flags)
                if pytorch_has_cuda:
                    return
                
                # Determine CUDA version and index
                cuda_index = self._detect_cuda_index(service_name, creation_flags)
                
                # Uninstall CPU-only PyTorch
                if not pytorch_has_cuda:
                    self._uninstall_pytorch(service_name, python_exe, creation_flags)
                
                # Install PyTorch with CUDA
                if not self._install_pytorch_cuda(service_name, python_exe, cuda_index, creation_flags):
                    return
                
                # Verify installation
                self._verify_installation(service_name, python_exe, creation_flags)
                
            except Exception as e:
                import traceback
                error_msg = f"Error installing CUDA support: {str(e)}"
                self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
                self.app.ui_logger.log_to_service(service_name, traceback.format_exc())
                self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            finally:
                # Re-enable button
                if service_name in self.app.services_ui:
                    install_cuda_btn = self.app.services_ui[service_name].get("install_cuda_btn")
                    if install_cuda_btn:
                        install_cuda_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()
    
    def _check_cuda_gpu(self, service_name: str, creation_flags: int) -> bool:
        """Check for CUDA GPU availability."""
        self.app.ui_logger.log_to_service(service_name, "Checking for CUDA GPU...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Checking for NVIDIA GPU...")
        
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            error_msg = "nvidia-smi not found. Please install NVIDIA drivers first."
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            return False
        
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            error_msg = "No NVIDIA GPU detected. CUDA installation cannot proceed."
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            return False
        
        gpu_name = result.stdout.strip().split('\n')[0]
        self.app.ui_logger.log_to_service(service_name, f"Detected GPU: {gpu_name}")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Detected GPU: {gpu_name}")
        return True
    
    def _get_python_exe(self, service_name: str, creation_flags: int) -> Optional[Path]:
        """Get Python executable for Chatterbox venv."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            error_msg = f"Service {service_name} not found"
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            return None
        
        venv_dir = svc_info.get("venv")
        if not venv_dir or not venv_dir.exists():
            error_msg = f"Chatterbox venv not found at {venv_dir}. Please install Chatterbox first."
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            return None
        
        if platform.system() == "Windows":
            python_exe = venv_dir / "Scripts" / "python.exe"
        else:
            python_exe = venv_dir / "bin" / "python"
        
        if not python_exe.exists():
            error_msg = f"Python executable not found at {python_exe}"
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            return None
        
        self.app.ui_logger.log_to_service(service_name, f"Using Python: {python_exe}")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Using Python: {python_exe}")
        return python_exe
    
    def _ensure_pip(self, service_name: str, python_exe: Path, creation_flags: int) -> bool:
        """Ensure pip is available in the venv."""
        self.app.ui_logger.log_to_service(service_name, "Checking if pip is available...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Checking if pip is available...")
        
        check_pip_cmd = [str(python_exe), "-m", "pip", "--version"]
        pip_check_result = subprocess.run(
            check_pip_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creation_flags
        )
        
        if pip_check_result.returncode != 0:
            self.app.ui_logger.log_to_service(service_name, "pip not found. Installing pip...")
            self.app.ui_logger.log_to_launcher(f"[CUDA] pip not found. Installing pip using ensurepip...")
            
            ensurepip_cmd = [str(python_exe), "-m", "ensurepip", "--upgrade"]
            ensurepip_process = subprocess.Popen(
                ensurepip_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=creation_flags,
                encoding='utf-8',
                errors='replace'
            )
            
            for line in iter(ensurepip_process.stdout.readline, ''):
                if line:
                    clean_line = line.rstrip()
                    if clean_line:
                        self.app.ui_logger.log_to_service(service_name, clean_line)
                        if any(keyword in clean_line.lower() for keyword in ['installing', 'successfully', 'error', 'warning']):
                            self.app.ui_logger.log_to_launcher(f"[CUDA] {clean_line}")
            
            ensurepip_returncode = ensurepip_process.wait()
            
            if ensurepip_returncode != 0:
                error_msg = f"Failed to install pip (exit code: {ensurepip_returncode})"
                self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
                self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
                return False
            
            # Verify pip is now available
            pip_check_result = subprocess.run(
                check_pip_cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creation_flags
            )
            
            if pip_check_result.returncode != 0:
                error_msg = "pip installation completed but pip is still not available"
                self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
                self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
                return False
            
            self.app.ui_logger.log_to_service(service_name, "pip installed successfully")
            self.app.ui_logger.log_to_launcher(f"[CUDA] pip installed successfully")
        else:
            pip_version = pip_check_result.stdout.strip().split('\n')[0] if pip_check_result.stdout else "unknown"
            self.app.ui_logger.log_to_service(service_name, f"pip is available: {pip_version}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] pip is available: {pip_version}")
        
        return True
    
    def _check_pytorch_cuda(self, service_name: str, python_exe: Path, creation_flags: int) -> bool:
        """Check if PyTorch with CUDA is already installed."""
        self.app.ui_logger.log_to_service(service_name, "Checking current PyTorch installation...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Checking current PyTorch installation...")
        
        check_cmd = [str(python_exe), "-c", "import torch; print('VERSION:', torch.__version__); print('CUDA:', torch.cuda.is_available())"]
        
        result = subprocess.run(
            check_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creation_flags
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if "CUDA: True" in output:
                version_line = [line for line in output.split('\n') if 'VERSION:' in line]
                if version_line:
                    version = version_line[0].split('VERSION:')[1].strip()
                    self.app.ui_logger.log_to_service(service_name, f"PyTorch {version} already has CUDA support!")
                    self.app.ui_logger.log_to_launcher(f"[CUDA] PyTorch {version} already has CUDA support!")
                    return True
            else:
                self.app.ui_logger.log_to_service(service_name, "PyTorch found but CUDA is not available")
                self.app.ui_logger.log_to_launcher(f"[CUDA] PyTorch found but CUDA is not available - will upgrade")
        
        return False
    
    def _detect_cuda_index(self, service_name: str, creation_flags: int) -> str:
        """Detect CUDA version and return appropriate PyTorch index URL."""
        cuda_index = "https://download.pytorch.org/whl/cu121"  # Default
        
        nvcc = shutil.which("nvcc")
        if nvcc:
            nvcc_result = subprocess.run(
                [nvcc, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if nvcc_result.returncode == 0:
                for line in nvcc_result.stdout.split('\n'):
                    if 'release' in line.lower():
                        match = re.search(r'release\s+(\d+)\.(\d+)', line, re.IGNORECASE)
                        if match:
                            major, minor = match.groups()
                            if major == "12" and int(minor) >= 4:
                                cuda_index = "https://download.pytorch.org/whl/cu124"
                                self.app.ui_logger.log_to_service(service_name, f"Detected CUDA version: {major}.{minor} (using cu124 PyTorch build)")
                                self.app.ui_logger.log_to_launcher(f"[CUDA] Detected CUDA version: {major}.{minor} (using cu124 PyTorch build)")
                            elif major == "12":
                                cuda_index = "https://download.pytorch.org/whl/cu121"
                                self.app.ui_logger.log_to_service(service_name, f"Detected CUDA version: {major}.{minor} (using cu121 PyTorch build)")
                                self.app.ui_logger.log_to_launcher(f"[CUDA] Detected CUDA version: {major}.{minor} (using cu121 PyTorch build)")
                            elif major == "11" and minor == "8":
                                cuda_index = "https://download.pytorch.org/whl/cu118"
                                self.app.ui_logger.log_to_service(service_name, f"Detected CUDA version: {major}.{minor} (using cu118 PyTorch build)")
                                self.app.ui_logger.log_to_launcher(f"[CUDA] Detected CUDA version: {major}.{minor} (using cu118 PyTorch build)")
                            else:
                                cuda_index = "https://download.pytorch.org/whl/cu124"
                                self.app.ui_logger.log_to_service(service_name, f"Detected CUDA version: {major}.{minor} (using default cu124)")
                                self.app.ui_logger.log_to_launcher(f"[CUDA] Detected CUDA version: {major}.{minor} (using default cu124)")
                            break
        
        return cuda_index
    
    def _uninstall_pytorch(self, service_name: str, python_exe: Path, creation_flags: int):
        """Uninstall CPU-only PyTorch."""
        self.app.ui_logger.log_to_service(service_name, "Uninstalling CPU-only PyTorch...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Uninstalling CPU-only PyTorch...")
        
        uninstall_cmd = [str(python_exe), "-m", "pip", "uninstall", "torch", "torchaudio", "-y"]
        uninstall_process = subprocess.Popen(
            uninstall_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=creation_flags,
            encoding='utf-8',
            errors='replace'
        )
        
        for line in iter(uninstall_process.stdout.readline, ''):
            if line:
                clean_line = line.rstrip()
                if clean_line:
                    self.app.ui_logger.log_to_service(service_name, clean_line)
                    if any(keyword in clean_line.lower() for keyword in ['uninstalling', 'successfully', 'warning', 'error']):
                        self.app.ui_logger.log_to_launcher(f"[CUDA] {clean_line}")
        
        uninstall_returncode = uninstall_process.wait()
        
        if uninstall_returncode != 0:
            self.app.ui_logger.log_to_service(service_name, f"Warning: Uninstall completed with exit code {uninstall_returncode}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] Warning: Uninstall completed with exit code {uninstall_returncode} (may be normal if packages weren't installed)")
    
    def _install_pytorch_cuda(self, service_name: str, python_exe: Path, cuda_index: str, creation_flags: int) -> bool:
        """Install PyTorch with CUDA support."""
        self.app.ui_logger.log_to_service(service_name, f"Installing PyTorch with CUDA support from {cuda_index}...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Installing PyTorch with CUDA support (this may take several minutes)...")
        
        install_cmd = [
            str(python_exe), "-m", "pip", "install",
            "torch==2.6.0",
            "torchaudio==2.6.0",
            "--index-url", cuda_index,
            "--no-cache-dir"
        ]
        
        process = subprocess.Popen(
            install_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=creation_flags,
            encoding='utf-8',
            errors='replace'
        )
        
        for line in iter(process.stdout.readline, ''):
            if line:
                clean_line = line.rstrip()
                if clean_line:
                    self.app.ui_logger.log_to_service(service_name, clean_line)
                    line_lower = clean_line.lower()
                    if any(keyword in line_lower for keyword in [
                        'error', 'warning', 'success', 'installing', 'downloading',
                        'collecting', 'using cached', 'building wheel', 'running setup',
                        'requirement already satisfied', 'found existing installation',
                        'uninstalling', 'successfully installed', 'failed', 'exception'
                    ]):
                        self.app.ui_logger.log_to_launcher(f"[CUDA] {clean_line}")
        
        return_code = process.wait()
        
        if return_code != 0:
            error_msg = f"PyTorch CUDA installation failed (exit code: {return_code})"
            self.app.ui_logger.log_to_service(service_name, f"\nERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] Check the 'chatterbox' tab in Console Output for full installation details")
            return False
        
        return True
    
    def _verify_installation(self, service_name: str, python_exe: Path, creation_flags: int):
        """Verify CUDA installation."""
        self.app.ui_logger.log_to_service(service_name, "Verifying CUDA installation...")
        self.app.ui_logger.log_to_launcher(f"[CUDA] Verifying CUDA installation...")
        
        verify_cmd = [str(python_exe), "-c", "import torch; print('CUDA:', torch.cuda.is_available()); print('CUDA_VERSION:', torch.version.cuda if torch.version.cuda else 'None'); print('GPU_NAME:', torch.cuda.get_device_name(0) if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 'None')"]
        
        result = subprocess.run(
            verify_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creation_flags
        )
        
        if result.returncode == 0 and "CUDA: True" in result.stdout:
            self.app.ui_logger.log_to_service(service_name, "✓ CUDA installation verified successfully!")
            self.app.ui_logger.log_to_launcher(f"[CUDA] SUCCESS: PyTorch with CUDA support installed and verified!")
            
            for line in result.stdout.split('\n'):
                if 'GPU_NAME:' in line:
                    gpu_name = line.split('GPU_NAME:')[1].strip()
                    if gpu_name != 'None':
                        self.app.ui_logger.log_to_launcher(f"[CUDA] GPU: {gpu_name}")
                elif 'CUDA_VERSION:' in line:
                    cuda_version = line.split('CUDA_VERSION:')[1].strip()
                    if cuda_version != 'None':
                        self.app.ui_logger.log_to_launcher(f"[CUDA] CUDA Version: {cuda_version}")
            
            self.app.ui_logger.log_to_launcher(f"[CUDA] Restart Chatterbox service to use GPU inference")
        else:
            error_msg = "CUDA installation completed but verification failed. Check logs for details."
            self.app.ui_logger.log_to_service(service_name, f"ERROR: {error_msg}")
            self.app.ui_logger.log_to_launcher(f"[CUDA] ERROR: {error_msg}")
            if result.stdout:
                self.app.ui_logger.log_to_service(service_name, result.stdout)


