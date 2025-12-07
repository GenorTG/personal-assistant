import sys
import os
from pathlib import Path

# Add launcher directory to path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))

from manager import ServiceManager

def verify_llm_install():
    print("Initializing ServiceManager...")
    manager = ServiceManager(current_dir.parent)
    
    # Force delete core venv to ensure we test creation with Python 3.12
    core_venv = manager.services["llm"]["venv"]
    if core_venv.exists():
        print(f"Removing existing venv at {core_venv} to force recreation...")
        import shutil
        import time
        
        # Try shutil first
        try:
            shutil.rmtree(core_venv, ignore_errors=True)
        except Exception as e:
            print(f"shutil.rmtree failed: {e}")
            
        # Check if still exists
        if core_venv.exists():
            print("shutil failed, trying shell command...")
            os.system(f'rmdir /S /Q "{core_venv}"')
            time.sleep(1)
            
        if core_venv.exists():
            print("FATAL: Could not delete venv. It might be locked.")
            return
        else:
            print("Venv successfully deleted.")
    
    print("Testing LLM service installation logic...")
    # This will trigger the _install_python_service("llm") method
    # which now contains our new logic for prebuilt wheels
    try:
        # We call the internal method directly to test the logic
        # In a real run, this is called by install_service
        cmd = manager._install_python_service("llm")
        print(f"Installation command returned: {cmd}")
        
        # Verify if llama-cpp-python is installed and working
        print("\nVerifying llama-cpp-python installation...")
        venv_python = manager.services["llm"]["venv"] / ("Scripts" if sys.platform == "win32" else "bin") / "python"
        if sys.platform == "win32":
            venv_python = venv_python.with_suffix(".exe")
            
        if venv_python.exists():
            import subprocess
            verify_cmd = [
                str(venv_python), "-c", 
                "import llama_cpp; print(f'llama-cpp-python version: {llama_cpp.__version__}'); "
                "print(f'CUDA support: {hasattr(llama_cpp, \"llama_supports_gpu_offload\") or hasattr(llama_cpp, \"llama_gpu_offload\")}')"
            ]
            result = subprocess.run(verify_cmd, capture_output=True, text=True)
            print(result.stdout)
            print(result.stderr)
        else:
            print("Venv python not found!")
            
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_llm_install()
