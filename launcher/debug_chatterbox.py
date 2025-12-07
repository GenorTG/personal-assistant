import sys
import subprocess
import platform

def debug_chatterbox():
    print("Debugging Chatterbox installation...")
    
    # Simulate the torch install command from manager.py
    # We'll assume CUDA 12.4+ based on previous checks (CUDA 12.9 detected)
    cuda_index = "https://download.pytorch.org/whl/cu124"
    
    print(f"Attempting to install torch==2.6.0 from {cuda_index}...")
    
    # Use Python 3.12 explicitly
    python_exe = r"C:\Users\GS66 Stealth\AppData\Local\Programs\Python\Python312\python.exe"
    
    print(f"Attempting to install torch>=2.0.0,<2.7.0 from {cuda_index} using {python_exe}...")
    
    cmd = [
        python_exe, "-m", "pip", "install",
        "torch>=2.0.0,<2.7.0",
        "torchaudio>=2.0.0,<2.7.0",
        "--index-url", cuda_index,
        "--dry-run" # Dry run to check availability without installing
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            print("Installation check failed!")
            
            # Check available versions
            print("\nChecking available versions on the index...")
            cmd_index = [
                sys.executable, "-m", "pip", "index", "versions", "torch",
                "--index-url", cuda_index
            ]
            subprocess.run(cmd_index)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_chatterbox()
