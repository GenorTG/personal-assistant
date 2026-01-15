"""Python executable finder for Chatterbox service."""

import os
import subprocess
import re
from pathlib import Path
from typing import Optional


def find_system_python() -> Optional[str]:
    """Find system Python executable (3.11+) for creating venv."""
    
    def check_python_version(python_exe: str) -> bool:
        """Check if Python executable is version 3.11+."""
        try:
            if python_exe.startswith("py "):
                # Handle py launcher format
                cmd = python_exe.split()
            else:
                cmd = [python_exe]
            result = subprocess.run(
                cmd + ["--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode != 0:
                return False
            version_str = result.stdout.strip()
            match = re.search(r'(\d+)\.(\d+)', version_str)
            if match:
                major, minor = int(match.group(1)), int(match.group(2))
                return (major == 3 and minor >= 11) or major > 3
        except Exception:
            pass
        return False
    
    # On Windows, check Python Launcher first
    if os.name == 'nt':
        for version in ["3.13", "3.12", "3.11"]:
            try:
                result = subprocess.run(
                    ["py", f"-{version}", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                if result.returncode == 0:
                    return f"py -{version}"
            except Exception:
                pass
    
    # Try system Python commands
    for cmd in ["python3.13", "python3.12", "python3.11", "python3", "python"]:
        try:
            if check_python_version(cmd):
                return cmd
        except Exception:
            pass
    
    # On Windows, check common installation locations
    if os.name == 'nt':
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        ]
        
        for base_path in common_paths:
            if not base_path.exists():
                continue
            try:
                for python_dir in base_path.iterdir():
                    if python_dir.is_dir() and "Python" in python_dir.name:
                        python_exe = python_dir / "python.exe"
                        if python_exe.exists() and check_python_version(str(python_exe)):
                            return str(python_exe)
            except Exception:
                continue
    
    return None


def get_venv_python(venv_dir: Path) -> Optional[str]:
    """Get Python executable from venv."""
    if os.name == 'nt':
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
    
    if venv_python.exists():
        return str(venv_python)
    return None


def find_python_exe(venv_dir: Path) -> Optional[str]:
    """Find Python executable for Chatterbox - prefer venv, fallback to system."""
    # First, try to use the venv Python
    venv_python = get_venv_python(venv_dir)
    if venv_python:
        return venv_python
    
    # Fallback to system Python (for creating venv)
    return find_system_python()

