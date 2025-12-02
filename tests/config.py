"""Test configuration and constants."""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ServiceConfig:
    """Configuration for a service."""
    name: str
    port: int
    health_endpoint: str
    base_url: str
    required: bool = True
    
    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"


# Service configurations - single source of truth
SERVICES: Dict[str, ServiceConfig] = {
    "memory": ServiceConfig(
        name="Memory Service",
        port=8005,
        health_endpoint="/health",
        base_url="http://localhost:8005",
        required=True
    ),
    "tools": ServiceConfig(
        name="Tool Service",
        port=8006,
        health_endpoint="/health",
        base_url="http://localhost:8006",
        required=False
    ),
    "gateway": ServiceConfig(
        name="API Gateway",
        port=8000,
        health_endpoint="/health",
        base_url="http://localhost:8000",
        required=True
    ),
    "llm": ServiceConfig(
        name="LLM Service",
        port=8001,
        health_endpoint="/health",
        base_url="http://localhost:8001",
        required=False  # Managed by gateway
    ),
    "whisper": ServiceConfig(
        name="Whisper STT",
        port=8003,
        health_endpoint="/health",
        base_url="http://localhost:8003",
        required=False
    ),
    "piper": ServiceConfig(
        name="Piper TTS",
        port=8004,
        health_endpoint="/health",
        base_url="http://localhost:8004",
        required=False
    ),
    "chatterbox": ServiceConfig(
        name="Chatterbox TTS",
        port=4123,
        health_endpoint="/health",
        base_url="http://localhost:4123",
        required=False
    ),
    "kokoro": ServiceConfig(
        name="Kokoro TTS",
        port=8880,
        health_endpoint="/health",
        base_url="http://localhost:8880",
        required=False
    ),
    "frontend": ServiceConfig(
        name="Frontend (Next.js)",
        port=3000,
        health_endpoint="/",
        base_url="http://localhost:3000",
        required=False  # User-started service, not auto-started by tests
    ),
}


# Timeout for requests (seconds)
REQUEST_TIMEOUT = 10
HEALTH_CHECK_TIMEOUT = 3

