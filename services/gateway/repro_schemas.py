import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

try:
    from src.api.schemas import AISettings
    print("Successfully imported AISettings")
except Exception as e:
    print(f"Failed to import AISettings: {e}")
    import traceback
    traceback.print_exc()
