"""Application settings and configuration."""
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "Personal AI Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Paths
    # settings.py is at: services/gateway/src/config/settings.py
    # Need to go up 5 levels to reach project root: config -> src -> gateway -> services -> root
    base_dir: Path = Path(__file__).parent.parent.parent.parent.parent
    data_dir: Path = base_dir / "data"
    models_dir: Path = data_dir / "models"
    memory_dir: Path = data_dir / "memory"
    vector_store_dir: Path = data_dir / "vector_store"
    db_path: Path = data_dir / "assistant.db"  # Shared database
    
    # LLM Settings
    default_llm_model: Optional[str] = None
    llm_context_size: int = 4096
    llm_n_threads: int = 4
    llm_n_gpu_layers: int = 0  # 0 = CPU only, set > 0 for GPU (auto-detected if available)
    
    # Sampler Settings
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    
    # Service URLs
    llm_service_url: str = "http://127.0.0.1:8001"  # llama-cpp-python server
    whisper_service_url: str = "http://localhost:8003"
    piper_service_url: str = "http://localhost:8004"
    chatterbox_service_url: str = "http://localhost:4123"  # Chatterbox TTS
    kokoro_service_url: str = "http://localhost:8880"
    audio_client_url: str = "http://localhost:8002"
    
    # Memory Settings
    embedding_model: str = "all-MiniLM-L6-v2"
    vector_store_type: str = "chromadb"  # "chromadb" or "faiss"
    context_retrieval_top_k: int = 5
    context_similarity_threshold: float = 0.7
    
    # STT Settings
    stt_provider: str = "faster-whisper"  # "faster-whisper" or "vosk"
    stt_model_size: str = "base"  # For faster-whisper: tiny, base, small, medium, large
    stt_language: str = "en"
    
    # TTS Settings
    tts_provider: str = "kokoro"
    tts_voice: Optional[str] = None
    
    # Tool Settings
    enable_tools: bool = True
    max_tool_calls_per_turn: int = 5
    
    # System Prompt
    default_system_prompt: str = """You are a helpful, friendly, and knowledgeable AI assistant. 
You have access to your conversation history and can remember important information from past conversations.
You can use tools to perform actions when needed.
Be conversational, helpful, and accurate in your responses."""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Ensure data directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
settings.memory_dir.mkdir(parents=True, exist_ok=True)
settings.vector_store_dir.mkdir(parents=True, exist_ok=True)
