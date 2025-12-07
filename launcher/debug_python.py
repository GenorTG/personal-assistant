import sys
import os
from pathlib import Path

# Add launcher directory to path
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))

from manager import ServiceManager

def debug_python_detection():
    print("Initializing ServiceManager...")
    manager = ServiceManager(current_dir.parent)
    
    print("Testing find_latest_python...")
    python_exe = manager.find_latest_python(max_major=3, max_minor=12)
    print(f"Found python: {python_exe}")

if __name__ == "__main__":
    debug_python_detection()
