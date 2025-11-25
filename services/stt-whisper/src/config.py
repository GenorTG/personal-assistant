from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Speech Service"
    host: str = "0.0.0.0"
    port: int = 8003
    
    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent
    data_dir: Path = base_dir / "data"
    models_dir: Path = data_dir / "models"
    
    # STT Settings
    stt_provider: str = "faster-whisper"
    stt_model_size: str = "base"
    stt_language: str = "en"
    
    # TTS Settings
    tts_model_path: str = "" # Path to Piper model
    
    class Config:
        env_file = ".env"

settings = Settings()
