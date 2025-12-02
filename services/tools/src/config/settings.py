"""Tool service settings and configuration."""
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Tool service settings."""
    
    # Application
    app_name: str = "Tool Service"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8006
    
    # Paths
    base_dir: Path = Path(__file__).parent.parent.parent.parent.parent
    data_dir: Path = base_dir / "data"
    db_path: Path = data_dir / "assistant.db"  # Shared database
    files_dir: Path = data_dir / "files"  # Centralized file storage
    
    # Tool Settings
    enable_code_execution: bool = True
    enable_file_access: bool = True
    enable_web_search: bool = True
    max_code_execution_time: int = 30  # seconds
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Ensure data directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.files_dir.mkdir(parents=True, exist_ok=True)

