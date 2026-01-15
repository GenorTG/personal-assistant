"""CUDA detection and PyTorch installation command generation for Chatterbox."""

import subprocess
import shutil
import logging
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


def detect_cuda_and_get_pytorch_cmd(venv_python: str) -> Tuple[bool, Optional[List[str]]]:
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
                
                # Try nvcc for more accurate CUDA version
                nvcc = shutil.which("nvcc")
                cuda_index = "https://download.pytorch.org/whl/cu126"  # Default to CUDA 12.6
                
                if nvcc:
                    nvcc_result = subprocess.run(
                        [nvcc, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if nvcc_result.returncode == 0:
                        import re
                        for line in nvcc_result.stdout.split('\n'):
                            if 'release' in line.lower():
                                match = re.search(r'release\s+(\d+)\.(\d+)', line, re.IGNORECASE)
                                if match:
                                    major, minor = match.groups()
                                    # Use cu126 for CUDA 12.6+ (recommended), cu124 for CUDA 12.4-12.5, cu121 for CUDA 12.1-12.3
                                    if major == "12" and int(minor) >= 6:
                                        cuda_index = "https://download.pytorch.org/whl/cu126"
                                        logger.info("Detected CUDA version: %s.%s (using cu126 PyTorch build)", major, minor)
                                    elif major == "12" and int(minor) >= 4:
                                        cuda_index = "https://download.pytorch.org/whl/cu124"
                                        logger.info("Detected CUDA version: %s.%s (using cu124 PyTorch build)", major, minor)
                                    elif major == "12":
                                        cuda_index = "https://download.pytorch.org/whl/cu121"
                                        logger.info("Detected CUDA version: %s.%s (using cu121 PyTorch build)", major, minor)
                                    elif major == "11" and minor == "8":
                                        cuda_index = "https://download.pytorch.org/whl/cu118"
                                        logger.info("Detected CUDA version: %s.%s (using cu118 PyTorch build)", major, minor)
                                    break
                
                # Chatterbox requires torch==2.6.0 and torchaudio==2.6.0 (exact versions)
                pytorch_cmd = [
                    venv_python, "-m", "pip", "install",
                    "torch==2.6.0",
                    "torchaudio==2.6.0",
                    "--index-url", cuda_index,
                    "--no-cache-dir"
                ]
                
                return True, pytorch_cmd
        
        # No CUDA detected
        return False, None
    except Exception as e:
        logger.warning("Error detecting CUDA: %s", str(e))
        return False, None


def check_device_info(venv_python: Optional[str]) -> dict:
    """Check if CUDA is available in the venv."""
    device_info = {
        "device": "unknown",
        "cuda_available": False,
        "gpu_name": None,
        "pytorch_version": None
    }
    
    try:
        if not venv_python:
            return device_info
        
        # Check PyTorch CUDA availability
        check_cmd = [
            venv_python, "-c",
            "import torch; "
            "print('VERSION:', torch.__version__); "
            "print('CUDA_AVAILABLE:', torch.cuda.is_available()); "
            "print('CUDA_VERSION:', torch.version.cuda if torch.version.cuda else 'None'); "
            "print('DEVICE_COUNT:', torch.cuda.device_count() if torch.cuda.is_available() else 0); "
            "print('GPU_NAME:', torch.cuda.get_device_name(0) if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 'None')"
        ]
        
        result = subprocess.run(
            check_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            for line in output.split('\n'):
                if line.startswith('VERSION:'):
                    device_info["pytorch_version"] = line.split('VERSION:')[1].strip()
                elif line.startswith('CUDA_AVAILABLE:'):
                    cuda_available = line.split('CUDA_AVAILABLE:')[1].strip()
                    device_info["cuda_available"] = cuda_available == "True"
                elif line.startswith('CUDA_VERSION:'):
                    cuda_version = line.split('CUDA_VERSION:')[1].strip()
                    if cuda_version != "None":
                        device_info["cuda_version"] = cuda_version
                elif line.startswith('DEVICE_COUNT:'):
                    device_count = int(line.split('DEVICE_COUNT:')[1].strip())
                    device_info["device_count"] = device_count
                elif line.startswith('GPU_NAME:'):
                    gpu_name = line.split('GPU_NAME:')[1].strip()
                    if gpu_name != "None":
                        device_info["gpu_name"] = gpu_name
            
            # Determine device type
            if device_info["cuda_available"]:
                device_info["device"] = "cuda"
            else:
                device_info["device"] = "cpu"
    except Exception as e:
        logger.debug("Failed to check device info: %s", str(e))
    
    return device_info

