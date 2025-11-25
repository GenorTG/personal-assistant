import sys
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from backend.src.services.external.llm_server_service import LLMServerService

async def test_config_generation():
    service = LLMServerService()
    service.venv_python = "python" # Mock python path
    
    # Mock subprocess to avoid starting actual server
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_exec.return_value = mock_process
        
        # Mock wait_for_server to return True immediately
        service._wait_for_server = MagicMock(return_value=asyncio.Future())
        service._wait_for_server.return_value.set_result(True)
        
        # Mock log monitoring
        service._monitor_logs = MagicMock()
        
        # Test parameters
        model_path = "test_model.gguf"
        n_cpu_moe = 4
        cache_type_k = "f16"
        cache_type_v = "q8_0"
        
        print(f"Testing start_server with n_cpu_moe={n_cpu_moe}, cache_k={cache_type_k}, cache_v={cache_type_v}...")
        
        # Create a dummy model file so path check passes (if any)
        # Actually start_server doesn't check existence, but config writing uses parent dir
        Path(model_path).touch()
        
        try:
            await service.start_server(
                model_path=model_path,
                n_gpu_layers=33,
                n_ctx=4096,
                n_batch=512,
                n_cpu_moe=n_cpu_moe,
                cache_type_k=cache_type_k,
                cache_type_v=cache_type_v
            )
            
            # Check if config file was created
            config_path = Path(model_path).parent / "server_config.json"
            if config_path.exists():
                print("Config file created!")
                with open(config_path, "r") as f:
                    config = json.load(f)
                    print("Config content:", json.dumps(config, indent=2))
                    
                    # Verify n_cpu_moe
                    model_config = config["models"][0]
                    
                    success = True
                    if model_config.get("n_cpu_moe") != n_cpu_moe:
                        print(f"FAILURE: n_cpu_moe is {model_config.get('n_cpu_moe')}, expected {n_cpu_moe}")
                        success = False
                        
                    if model_config.get("cache_type_k") != cache_type_k:
                        print(f"FAILURE: cache_type_k is {model_config.get('cache_type_k')}, expected {cache_type_k}")
                        success = False
                        
                    if model_config.get("cache_type_v") != cache_type_v:
                        print(f"FAILURE: cache_type_v is {model_config.get('cache_type_v')}, expected {cache_type_v}")
                        success = False
                        
                    if success:
                        print("SUCCESS: All parameters correctly set in config!")
            else:
                print("FAILURE: Config file not found!")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # Cleanup
            if Path(model_path).exists():
                Path(model_path).unlink()
            if Path("server_config.json").exists():
                Path("server_config.json").unlink()

if __name__ == "__main__":
    asyncio.run(test_config_generation())
