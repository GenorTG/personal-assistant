"""Installation checking utilities for Chatterbox service."""

import subprocess
from pathlib import Path
from typing import Optional


def check_installation(base_dir: Path) -> bool:
    """Check if Chatterbox TTS API is installed."""
    if not base_dir.exists():
        return False
    # Check for various entry point files
    return (
        (base_dir / "api.py").exists() or 
        (base_dir / "main.py").exists() or
        (base_dir / "src" / "main.py").exists()
    )


def check_dependencies_installed(venv_python: Optional[str]) -> bool:
    """Check if dependencies are installed in service venv."""
    try:
        if not venv_python:
            return False
        
        # Check for key packages needed by chatterbox server (uvicorn, fastapi)
        cmd = [venv_python, "-c", "import uvicorn, fastapi; print('OK')"]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        return result.returncode == 0 and "OK" in result.stdout
    except Exception:
        return False

