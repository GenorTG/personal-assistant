from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Piper TTS Service"
    host: str = "0.0.0.0"
    port: int = 8004  # Fixed: Piper uses port 8004, not 8003 (which is Whisper)
    
    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent
    data_dir: Path = base_dir / "data"
    models_dir: Path = data_dir / "models"
    
    # TTS Settings
    tts_model_path: str = "" # Path to Piper model
    
    class Config:
        env_file = ".env"

settings = Settings()
