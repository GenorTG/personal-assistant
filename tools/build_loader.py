import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """Check if PyInstaller is installed, install if not."""
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], check=True, capture_output=True)
        print("[INFO] PyInstaller is already installed.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[INFO] Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

def create_loader_script():
    """Create the shim script that loads the external launcher."""
    loader_code = """
import sys
import os
import importlib.util

def main():
    # Get the directory where the executable is located
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Add the current directory to sys.path so we can import 'launcher' package
    sys.path.insert(0, base_dir)
    
    print(f"[LOADER] Running from: {base_dir}")
    print(f"[LOADER] Loading launcher from source...")

    # Check if launcher/launcher.py exists
    launcher_path = os.path.join(base_dir, "launcher", "launcher.py")
    if not os.path.exists(launcher_path):
        # Try one level up if we are in a subfolder (e.g. dist/)
        base_dir = os.path.dirname(base_dir)
        sys.path.insert(0, base_dir)
        launcher_path = os.path.join(base_dir, "launcher", "launcher.py")
    
    if not os.path.exists(launcher_path):
        import tkinter.messagebox
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showerror("Error", f"Could not find launcher source code at:\\n{launcher_path}\\n\\nPlease ensure the 'launcher' folder is next to this executable.")
        return

    try:
        # Import launcher.launcher module dynamically
        # We use standard import because we added base_dir to sys.path
        import launcher.launcher
        launcher.launcher.main()
    except Exception as e:
        import traceback
        import tkinter.messagebox
        import tkinter
        err = traceback.format_exc()
        root = tkinter.Tk()
        root.withdraw()
        tkinter.messagebox.showerror("Critical Error", f"Failed to launch:\\n{e}\\n\\n{err}")

if __name__ == "__main__":
    main()
"""
    with open("loader_shim.py", "w") as f:
        f.write(loader_code)
    return "loader_shim.py"

def build_exe():
    """Run PyInstaller to build the loader."""
    check_pyinstaller()
    shim_file = create_loader_script()
    
    # Define hidden imports (dependencies that need to be bundled)
    hidden_imports = [
        "customtkinter",
        "rich",
        "psutil",
        "requests",
        "packaging",
        "PIL",
        "PIL.Image",
        "urllib",
        "socket",
        "logging",
        "threading",
        "subprocess",
        "webbrowser"
    ]
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",  # No console window
        "--name", "PersonalAssistant",
        "--clean",
    ]
    
    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])
        
    # Exclude the launcher package itself so it's NOT bundled
    cmd.extend(["--exclude-module", "launcher"])
    
    cmd.append(shim_file)
    
    print(f"[INFO] Building executable with command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    # Cleanup
    if os.path.exists(shim_file):
        os.remove(shim_file)
    if os.path.exists("PersonalAssistant.spec"):
        os.remove("PersonalAssistant.spec")
    if os.path.exists("build"):
        shutil.rmtree("build")

    print("\n[SUCCESS] Build complete!")
    print(f"[INFO] Your standalone executable is at: {os.path.abspath('dist/PersonalAssistant.exe')}")
    print("[INFO] You can move this .exe to the project root (next to 'launcher/' folder) and run it.")

if __name__ == "__main__":
    build_exe()
