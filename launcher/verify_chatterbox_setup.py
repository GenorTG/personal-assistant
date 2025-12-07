import sys
import os
from pathlib import Path

# Add launcher directory to path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))

from manager import ServiceManager

def verify_chatterbox_setup():
    print("Initializing ServiceManager...")
    manager = ServiceManager(current_dir.parent)
    
    print("Checking Chatterbox service configuration...")
    chatterbox = manager.services["chatterbox"]
    print(f"Service: {chatterbox['name']}")
    print(f"Requested Python Version: {chatterbox.get('python_version', 'Not Set')}")
    
    print("\nTesting find_latest_python for Chatterbox...")
    # Simulate what _install_python_service does
    target_minor = 12
    if "python_version" in chatterbox:
        ver_str = str(chatterbox["python_version"])
        if "." in ver_str:
            target_minor = int(ver_str.split(".")[1])
    
    print(f"Target Minor Version: {target_minor}")
    python_exe = manager.find_latest_python(max_major=3, max_minor=target_minor)
    print(f"Found Python Executable: {python_exe}")
    
    # Verify the version of the found executable
    import subprocess
    result = subprocess.run([python_exe, "--version"], capture_output=True, text=True)
    print(f"Actual Version: {result.stdout.strip()}")

if __name__ == "__main__":
    verify_chatterbox_setup()
