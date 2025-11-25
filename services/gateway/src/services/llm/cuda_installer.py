"""Helper to install llama-cpp-python with CUDA support."""
import subprocess
import logging
import shutil
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def check_llama_cuda_support() -> Tuple[bool, Optional[str]]:
    """
    Check if llama-cpp-python has CUDA support.
    
    Returns:
        Tuple of (has_cuda, error_message)
    """
    try:
        from llama_cpp import llama_cpp
        has_cuda = (
            hasattr(llama_cpp, 'llama_supports_gpu_offload') or
            hasattr(llama_cpp, 'llama_gpu_offload') or
            hasattr(llama_cpp, 'llama_n_gpu_layers')
        )
        if has_cuda:
            return True, None
        else:
            return False, "llama-cpp-python was compiled without CUDA support"
    except ImportError:
        return False, "llama-cpp-python not installed"
    except Exception as e:
        return False, f"Error checking CUDA support: {e}"


def check_cuda_available() -> bool:
    """Check if CUDA GPU is available on the system."""
    # Check nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass
    
    # Check PyTorch CUDA
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except ImportError:
        pass
    
    return False


def install_llama_cuda(python_exe: Optional[str] = None) -> Tuple[bool, str]:
    """
    Install llama-cpp-python with CUDA support.
    
    Args:
        python_exe: Python executable path (None = use system python)
    
    Returns:
        Tuple of (success, message)
    """
    if python_exe is None:
        python_exe = "python"
    
    # Check if CUDA is available
    if not check_cuda_available():
        return False, "No CUDA GPU detected. Cannot install CUDA-enabled llama-cpp-python."
    
    try:
        # Uninstall existing version
        logger.info("Uninstalling existing llama-cpp-python...")
        uninstall_cmd = [python_exe, "-m", "pip", "uninstall", "llama-cpp-python", "-y"]
        subprocess.run(uninstall_cmd, capture_output=True, timeout=60, check=False)
        
        # Install with CUDA support
        logger.info("Installing llama-cpp-python with CUDA support...")
        install_cmd = [python_exe, "-m", "pip", "install", "llama-cpp-python[cuda]"]
        result = subprocess.run(
            install_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes for compilation
        )
        
        if result.returncode == 0:
            # Verify installation
            has_cuda, error = check_llama_cuda_support()
            if has_cuda:
                return True, "llama-cpp-python with CUDA support installed successfully"
            else:
                return False, f"Installation completed but CUDA support not verified: {error}"
        else:
            error_msg = result.stderr[:500] if result.stderr else result.stdout[:500]
            return False, f"Installation failed: {error_msg}"
    except subprocess.TimeoutExpired:
        return False, "Installation timed out (may still be in progress)"
    except Exception as e:
        return False, f"Installation error: {str(e)}"


