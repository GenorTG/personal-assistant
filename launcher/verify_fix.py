
import os
import sys
import subprocess
import time
from pathlib import Path

# Add launcher directory to path to allow importing manager directly
# This avoids importing launcher.py (and thus customtkinter) by accident
launcher_dir = Path("d:/Github Personal/personal-assistant/launcher").resolve()
sys.path.insert(0, str(launcher_dir))

try:
    from manager import ServiceManager
except ImportError as e:
    print(f"Failed to import ServiceManager: {e}")
    sys.exit(1)

def verify_pip_show():
    print("Initializing ServiceManager to get paths...")
    # Initialize with the parent directory of launcher as root
    manager = ServiceManager(root_dir=launcher_dir.parent)
    
    services_to_check = ["memory", "tools", "gateway", "llm"]
    core_venv = manager.core_venv
    
    if sys.platform == "win32":
        python_exe = core_venv / "Scripts" / "python.exe"
    else:
        python_exe = core_venv / "bin" / "python"
        
    print(f"Core venv python: {python_exe}")
    if not python_exe.exists():
        print("Error: Core venv python not found!")
        return
        
    key_packages = {
        "memory": "chromadb",
        "tools": "Pillow",
        "gateway": "aiohttp", 
        "llm": "llama-cpp-python"
    }
    
    print("\nVerifying 'pip show' command for core services...")
    
    for service in services_to_check:
        pkg_name = key_packages.get(service)
        print(f"\nChecking {service} (package: {pkg_name})...")
        
        start_time = time.time()
        
        cmd = [str(python_exe), "-m", "pip", "show", pkg_name]
        
        # Set environment variable to suppress warnings
        env = os.environ.copy()
        env["PYTHONWARNINGS"] = "ignore"
        
        try:
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=creationflags,
                    env=env,
                    timeout=5
                )
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=5
                )
                
            elapsed = time.time() - start_time
            print(f"Time taken: {elapsed:.2f}s")
            print(f"Return code: {result.returncode}")
            
            if result.returncode == 0:
                print(f"✅ Status: INSTALLED")
            else:
                print(f"❌ Status: NOT INSTALLED")
                # Only show stderr if it failed
                if result.stderr:
                    print(f"Stderr: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_pip_show()
