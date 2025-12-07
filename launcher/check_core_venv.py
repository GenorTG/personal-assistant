import sys
import os
import subprocess
from pathlib import Path

# Define paths
root_dir = Path(__file__).parent.parent.resolve()
core_venv_python = root_dir / "services" / ".core_venv" / "Scripts" / "python.exe"

def verify_core_venv():
    print(f"Checking core venv at: {core_venv_python}")
    if not core_venv_python.exists():
        print("FATAL: Core venv python not found!")
        return

    # Check python version
    print("\n--- Python Version ---")
    subprocess.run([str(core_venv_python), "--version"])

    # Check llama-cpp-python
    print("\n--- Checking llama-cpp-python ---")
    cmd = [
        str(core_venv_python), "-c", 
        "import llama_cpp; print(f'Version: {llama_cpp.__version__}'); "
        "print(f'CUDA Support: {hasattr(llama_cpp, \"llama_supports_gpu_offload\") or hasattr(llama_cpp, \"llama_gpu_offload\")}')"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print("Error checking llama-cpp-python:")
            print(result.stderr)
    except Exception as e:
        print(f"Failed to run check: {e}")

    # Check torch (just in case)
    print("\n--- Checking torch ---")
    cmd = [str(core_venv_python), "-m", "pip", "show", "torch"]
    subprocess.run(cmd)

if __name__ == "__main__":
    verify_core_venv()
