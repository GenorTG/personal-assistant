import sys
from pathlib import Path
import subprocess
import time
import os
import platform

# Add launcher dir to path
launcher_dir = Path("d:/Github Personal/personal-assistant/launcher").resolve()
sys.path.insert(0, str(launcher_dir))

# Mock some things if needed, but manager handles it
from manager import ServiceManager

def check_service(name, manager):
    print(f"\n{'='*40}")
    print(f"Checking {name}...")
    service = manager.services.get(name)
    if not service:
        print("Service not found")
        return

    if name == "frontend":
        print("Frontend check (skipping python checks)")
        dir_path = service.get("dir")
        print(f"Dir: {dir_path}")
        if dir_path:
            node_modules = dir_path / "node_modules"
            print(f"node_modules exists: {node_modules.exists()}")
        return

    # 1. Check venv path
    venv_path = service.get("venv")
    if not venv_path:
        print("No venv path")
        return

    print(f"Venv path: {venv_path}")
    if not venv_path.exists():
        print("Venv path does not exist!")
        return

    # 2. Check python executable
    if platform.system() == "Windows":
        python_exe = venv_path / "Scripts" / "python.exe"
    else:
        python_exe = venv_path / "bin" / "python"
    
    print(f"Python exe: {python_exe}")
    if not python_exe.exists():
        print("Python exe does not exist!")
        return

    # 3. Check python version
    try:
        start_time = time.time()
        print("Running python --version...")
        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW
            
        result = subprocess.run(
            [str(python_exe), "--version"],
            capture_output=True,
            timeout=5,
            text=True,
            creationflags=creation_flags
        )
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout.strip()}")
        print(f"Stderr: {result.stderr.strip()}")
        print(f"Time taken: {time.time() - start_time:.2f}s")
    except Exception as e:
        print(f"Error running python --version: {e}")

    # 4. Check dependencies (pip list)
    if service.get("is_core", False):
        try:
            start_time = time.time()
            print("Running pip list...")
            
            # Replicate env from launcher
            env = os.environ.copy()
            env["PYTHONWARNINGS"] = "ignore::DeprecationWarning:pkg_resources"
            
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "list", "--format=json"],
                capture_output=True,
                timeout=10,
                text=True,
                env=env,
                creationflags=creation_flags
            )
            print(f"Return code: {result.returncode}")
            print(f"Output length: {len(result.stdout)}")
            print(f"Time taken: {time.time() - start_time:.2f}s")
            
            if result.returncode != 0:
                print(f"Stderr: {result.stderr}")
            else:
                # Try to parse JSON to see if it's valid
                import json
                try:
                    # Filter output like launcher does
                    stdout_lines = result.stdout.split('\n')
                    json_lines = [line for line in stdout_lines if line.strip() and not line.strip().startswith('WARNING:') and 'pkg_resources' not in line]
                    stdout_clean = '\n'.join(json_lines)
                    data = json.loads(stdout_clean)
                    print(f"Parsed JSON successfully. Items: {len(data)}")
                except Exception as e:
                    print(f"JSON Parse Error: {e}")
                    print(f"Raw Output start: {result.stdout[:200]}")
        except Exception as e:
            print(f"Error running pip list: {e}")

if __name__ == "__main__":
    print(f"Root dir: {launcher_dir.parent}")
    mgr = ServiceManager(root_dir=launcher_dir.parent)
    print(f"Services found: {list(mgr.services.keys())}")
    
    for name in mgr.services:
        check_service(name, mgr)
