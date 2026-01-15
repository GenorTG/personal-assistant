"""Configuration for GTK4 launcher."""
from pathlib import Path

# Project root (parent of launcher-gtk4)
PROJECT_ROOT = Path(__file__).parent.parent

# Service configurations
SERVICES = {
    "gateway": {
        "name": "Gateway",
        "port": 8000,
        "directory": PROJECT_ROOT / "services" / "gateway",
        "venv": PROJECT_ROOT / "services" / ".core_venv",
        "start_command": None,  # Will be generated
        "description": "Main API Gateway (includes LLM, Memory, Tools, STT, TTS)"
    },
    "frontend": {
        "name": "Frontend",
        "port": 8002,
        "directory": PROJECT_ROOT / "services" / "frontend",
        "venv": None,  # Uses Node.js
        "start_command": None,  # Will be generated
        "description": "Next.js web interface"
    },
    "chatterbox": {
        "name": "Chatterbox TTS",
        "port": 8004,
        "directory": PROJECT_ROOT / "services" / "tts-chatterbox",
        "venv": PROJECT_ROOT / "services" / "tts-chatterbox" / "venv",  # Install script creates 'venv' in the directory
        "start_command": None,  # Will be generated
        "description": "Optional TTS service (Python 3.11)"
    }
}

