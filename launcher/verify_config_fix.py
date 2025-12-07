
import json
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(r"d:\Github Personal\personal-assistant\data\models\DavidAU\Llama-3.2-4X3B-MOE-Hell-California-Uncensored-10B-GGUF\server_config.json")
TEMP_CONFIG = Path(r"d:\Github Personal\personal-assistant\launcher\temp_config.json")
PYTHON_EXE = Path(r"d:\Github Personal\personal-assistant\services\.core_venv\Scripts\python.exe")

def test_config():
    if not CONFIG_PATH.exists():
        print(f"❌ Config not found: {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    # REMOVE weak parameter
    for model in config.get("models", []):
        if "num_experts_to_use" in model:
            print(f"Removing num_experts_to_use: {model['num_experts_to_use']}")
            del model["num_experts_to_use"]

    with open(TEMP_CONFIG, 'w') as f:
        json.dump(config, f, indent=2)

    print("Running server with cleaned config...")
    cmd = [str(PYTHON_EXE), "-m", "llama_cpp.server", "--config_file", str(TEMP_CONFIG)]
    
    # Run for 5 seconds then kill, just to see if it starts
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            outs, errs = proc.communicate(timeout=10)
        except subprocess.TimeoutError:
            print("✅ Server started successfully (timed out as expected)")
            proc.kill()
            return
        
        if proc.returncode != 0:
            print(f"❌ Server failed with code {proc.returncode}")
            print(outs.decode())
            print(errs.decode())
        else:
            print("✅ Server exited cleanly (unexpected but ok)")

    except Exception as e:
        print(f"❌ Execution failed: {e}")

if __name__ == "__main__":
    test_config()
