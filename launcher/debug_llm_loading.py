
import sys
import os
import time
from pathlib import Path

# Define paths
ROOT_DIR = Path(r"d:\Github Personal\personal-assistant")
MODELS_DIR = ROOT_DIR / "data" / "models"
MODEL_REL_PATH = r"DavidAU\Llama-3.2-4X3B-MOE-Hell-California-Uncensored-10B-GGUF\Llama-3.2-4X3B-MOE-Hell-California-10B-D_AU-Q4_0_4_4.gguf"
MODEL_PATH = MODELS_DIR / MODEL_REL_PATH

def test_direct_load():
    print(f"\n{'='*50}")
    print("TEST 1: Direct llama-cpp-python load (Offline)")
    print(f"{'='*50}")
    
    model_path_to_use = MODEL_PATH
    if not model_path_to_use.exists():
        print(f"❌ Model file not found: {model_path_to_use}")
        # Try to find it
        print("Searching for GGUF files given the error logs...")
        found = list(MODELS_DIR.glob("**/*.gguf"))
        if found:
            print(f"Found {len(found)} GGUF files. Using first one for test:")
            print(f"  {found[0]}")
            model_path_to_use = found[0]
        else:
            print("No GGUF files found.")
            return

    print(f"Loading model: {model_path_to_use}")
    print("Initializing llama_cpp.Llama...")
    
    try:
        from llama_cpp import Llama
        
        start_time = time.time()
        # Minimal parameters for testing
        llm = Llama(
            model_path=str(model_path_to_use),
            n_ctx=2048,
            n_threads=4,
            verbose=False
        )
        print(f"✅ Model loaded successfully in {time.time() - start_time:.2f}s")
        
        output = llm("Q: Say hello.\nA:", max_tokens=10, stop=["\n"])
        print(f"Test Inference: {output['choices'][0]['text']}")
        
    except ImportError:
        print("❌ llama_cpp module not found. Are you running in the correct venv?")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        import traceback
        traceback.print_exc()

def test_metadata_extraction():
    print(f"\n{'='*50}")
    print("TEST 2: Metadata Extraction (HuggingFace Check)")
    print(f"{'='*50}")
    
    # Setup path to import gateway services
    gateway_src = ROOT_DIR / "services" / "gateway" / "src"
    sys.path.insert(0, str(gateway_src))
    
    try:
        # We need to mock the module structure if imports are relative
        # But ModelInfoExtractor is largely standalone
        # Let's try to import it by raw processing or careful import
        
        # Determine the path to model_info.py
        model_info_path = gateway_src / "services" / "llm" / "model_info.py"
        if not model_info_path.exists():
            print(f"❌ model_info.py not found at {model_info_path}")
            return
            
        import importlib.util
        spec = importlib.util.spec_from_file_location("model_info", model_info_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["model_info"] = module
        spec.loader.exec_module(module)
        
        print("Initialized ModelInfoExtractor...")
        extractor = module.ModelInfoExtractor(MODELS_DIR)
        
        print(f"Extracting info for: {MODEL_PATH.parent.name}")
        
        # This is where we expect it to hang/fail if it hits HF
        start_time = time.time()
        info = extractor.extract_info(MODEL_PATH.parent.name, use_cache=False)
        
        print(f"✅ Extraction complete in {time.time() - start_time:.2f}s")
        print(f"Is MoE: {info.get('moe', {}).get('is_moe')}")
        print(f"Repo ID found: {info.get('config', {}).get('_name_or_path', 'Not in config')}")
        
    except Exception as e:
        print(f"❌ Metadata extraction failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct_load()
    test_metadata_extraction()
