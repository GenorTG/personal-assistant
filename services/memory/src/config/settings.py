"""Memory service settings and configuration."""
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Memory service settings."""
    
    # Application
    app_name: str = "Memory Service"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8005
    
    # Paths - use shared database in data/assistant.db
    base_dir: Path = Path(__file__).parent.parent.parent.parent.parent
    data_dir: Path = base_dir / "data"
    db_path: Path = data_dir / "assistant.db"  # Shared database
    vector_store_dir: Path = data_dir / "vector_store"
    
    # Memory Settings
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_store_type: str = "chromadb"  # "chromadb" or "faiss"
    context_retrieval_top_k: int = 5
    context_similarity_threshold: float = 0.7
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Ensure data directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.vector_store_dir.mkdir(parents=True, exist_ok=True)

