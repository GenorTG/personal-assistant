"""Service configuration definitions."""

from pathlib import Path
from typing import Dict, Any, Callable


def create_service_configs(root_dir: Path, service_manager) -> Dict[str, Dict[str, Any]]:
    """Create service configuration dictionary."""
    core_venv = root_dir / "services" / ".core_venv"
    
    return {
        "memory": {
            "name": "Core: Memory Service",
            "port": 8005,
            "url": "http://localhost:8005",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_python_service_start_cmd("memory", "main:app", 8005),
            "install_cmd": lambda: service_manager._install_python_service("memory"),
            "dir": root_dir / "services" / "memory",
            "venv": core_venv,
            "optional": False,
            "is_core": True
        },
        "tools": {
            "name": "Core: Tool Service",
            "port": 8006,
            "url": "http://localhost:8006",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_python_service_start_cmd("tools", "main:app", 8006),
            "install_cmd": lambda: service_manager._install_python_service("tools"),
            "dir": root_dir / "services" / "tools",
            "venv": core_venv,
            "optional": True,
            "is_core": True
        },
        "gateway": {
            "name": "Core: API Gateway",
            "port": 8000,
            "url": "http://localhost:8000",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_python_service_start_cmd("gateway", "main:app", 8000),
            "install_cmd": lambda: service_manager._install_python_service("gateway"),
            "dir": root_dir / "services" / "gateway",
            "venv": core_venv,
            "optional": False,
            "is_core": True
        },
        "llm": {
            "name": "Core: LLM Service",
            "port": 8001,
            "url": "http://localhost:8001",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_python_service_start_cmd("llm", "main:app", 8001),
            "install_cmd": lambda: service_manager._install_python_service("llm"),
            "dir": root_dir / "services" / "llm",
            "venv": core_venv,
            "optional": False,
            "is_core": True,
            "is_gateway_managed": True  # LLM is managed by Gateway
        },
        "whisper": {
            "name": "Whisper Service (STT)",
            "port": 8003,
            "url": "http://localhost:8003",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_whisper_start_cmd(),
            "install_cmd": lambda: service_manager._get_whisper_install_cmd(),
            "dir": root_dir / "services" / "stt-whisper",
            "venv": root_dir / "services" / "stt-whisper" / ".venv",
            "optional": True,
            "is_core": False
        },
        "piper": {
            "name": "Piper Service (TTS)",
            "port": 8004,
            "url": "http://localhost:8004",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_piper_start_cmd(),
            "install_cmd": lambda: service_manager._get_piper_install_cmd(),
            "dir": root_dir / "services" / "tts-piper",
            "venv": root_dir / "services" / "tts-piper" / ".venv",
            "optional": True,
            "is_core": False
        },
        "chatterbox": {
            "name": "Chatterbox Service (TTS)",
            "port": 4123,
            "url": "http://localhost:4123",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_chatterbox_start_cmd(),
            "install_cmd": lambda: service_manager._get_chatterbox_install_cmd(),
            "dir": root_dir / "external_services" / "chatterbox-tts-api",
            "venv": root_dir / "external_services" / "chatterbox-tts-api" / ".venv",
            "repo_url": "https://github.com/travisvn/chatterbox-tts-api",
            "is_external": True,
            "optional": True,
            "is_core": False
        },
        "kokoro": {
            "name": "Kokoro Service (TTS)",
            "port": 8880,
            "url": "http://localhost:8880",
            "health_endpoint": "/health",
            "start_cmd": lambda: service_manager._get_kokoro_start_cmd(),
            "install_cmd": lambda: service_manager._get_kokoro_install_cmd(),
            "dir": root_dir / "services" / "tts-kokoro",
            "venv": root_dir / "services" / "tts-kokoro" / ".venv",
            "optional": True,
            "is_core": False
        },
        "frontend": {
            "name": "Frontend",
            "port": 8002,
            "url": "http://localhost:8002",
            "health_endpoint": None,  # Frontend doesn't have a health endpoint
            "start_cmd": lambda: service_manager._get_frontend_start_cmd(),
            "install_cmd": lambda: service_manager._get_frontend_install_cmd(),
            "dir": root_dir / "services" / "frontend",
            "venv": None,  # Frontend uses npm, not Python venv
            "optional": False,
            "is_core": False
        }
    }


