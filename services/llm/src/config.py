from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "LLM Service"
    host: str = "0.0.0.0"
    port: int = 8001
    
    # Paths
    # llm-service/src/config.py -> parent(src) -> parent(llm-service) -> parent(services) -> parent(root)
    base_dir: Path = Path(__file__).parent.parent.parent.parent
    data_dir: Path = base_dir / "data"
    models_dir: Path = data_dir / "models"
    
    # LLM Settings
    default_llm_model: str = ""
    llm_context_size: int = 4096
    llm_n_threads: int = 4
    llm_n_gpu_layers: int = -1 # Auto
    
    # Generation Settings
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    max_tokens: int = 2048
    default_system_prompt: str = "You are a helpful AI assistant."
    
    class Config:
        env_file = ".env"

settings = Settings()
