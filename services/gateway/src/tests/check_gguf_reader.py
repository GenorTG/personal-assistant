import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

try:
    from llama_cpp.gguf import GGUFReader
    print("GGUFReader is available!")
    
    # Check if we can read a model if one exists
    # I'll just print the help or attributes for now as I don't want to hardcode a path that might not exist
    print("GGUFReader attributes:", dir(GGUFReader))
    
except ImportError:
    print("GGUFReader NOT found in llama_cpp.gguf")
except Exception as e:
    print(f"Error: {e}")
