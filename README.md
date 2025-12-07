# Personal Assistant

A privacy-focused, local AI assistant with modular microservices architecture. Features local LLM inference, speech-to-text, text-to-speech, memory management, and tool execution capabilities.

## Features

- **Local LLM Inference**: Run large language models locally using llama.cpp
- **Speech-to-Text**: Whisper-based STT service
- **Text-to-Speech**: Multiple TTS options (Piper, Kokoro, Chatterbox)
- **Memory System**: Vector-based memory with ChromaDB for conversation context
- **Tool Execution**: Extensible tool system for code execution, web search, file access, and more
- **Web Interface**: Modern Next.js frontend for chat and settings management
- **Service Management**: GUI launcher for easy service installation and management

## Architecture

The application uses a microservices architecture with the following services:

### Core Services (Shared Virtual Environment)

These services share a single Python virtual environment (`services/.core_venv`) and start simultaneously:

- **Gateway** (Port 8000): Main API gateway, handles routing, database, chat logic, and coordinates other services
- **LLM Service** (Port 8001): Manages LLM model loading and inference via llama-cpp-python server
- **Memory Service** (Port 8005): Handles vector-based memory storage and retrieval using ChromaDB
- **Tools Service** (Port 8006): Executes tools and manages tool registry

### Optional Services

Each optional service has its own virtual environment:

- **Frontend** (Port 8002): Next.js web interface
- **Whisper STT** (Port 8003): Speech-to-text using Faster-Whisper
- **Piper TTS** (Port 8004): Lightweight text-to-speech
- **Kokoro TTS** (Port 8880): High-quality ONNX-based TTS
- **Chatterbox TTS** (Port 4123): Advanced TTS with voice cloning (external service)

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ (for frontend)
- Git (for external services)
- CUDA Toolkit (optional, for GPU acceleration)

### Installation

1. **Launch the GUI Launcher**:
   - **Windows**: Double-click `launch-gui.vbs` (recommended) or `launch-gui.bat`
   - **Linux/Mac**: Run `python launcher/launcher.py`

2. **Install Services**:
   - In the launcher, check the services you want to install
   - Click "Install All" to install all checked services
   - Core services will be installed into a shared virtual environment
   - Optional services each get their own virtual environment

3. **Start Services**:
   - Check the services you want to run
   - Click "Start All" to start all checked services
   - Core services start simultaneously
   - Access the web interface at `http://localhost:8002`

## Project Structure

```
personal-assistant/
├── launcher/              # GUI launcher application
│   ├── launcher.py        # Main GUI (CustomTkinter)
│   ├── manager.py         # Service management logic
│   └── external_services_manager.py  # External service cloning
├── services/              # All microservices
│   ├── .core_venv/       # Shared venv for core services
│   ├── gateway/          # API Gateway (main backend)
│   ├── llm/              # LLM service
│   ├── memory/           # Memory service
│   ├── tools/            # Tools service
│   ├── frontend/         # Next.js frontend
│   ├── stt-whisper/      # Whisper STT
│   ├── tts-piper/        # Piper TTS
│   ├── tts-kokoro/       # Kokoro TTS
│   └── data/             # Shared data directory
├── external_services/     # External Git repositories
│   └── chatterbox-tts-api/  # Chatterbox TTS (auto-cloned)
├── launch-gui.bat        # Windows launcher entry point
└── launch-gui.vbs        # Windows hidden launcher wrapper
```

## Service Details

### Gateway Service

Main API server that coordinates all other services. Handles:
- Chat completions with LLM
- Memory storage and retrieval
- Tool execution coordination
- Settings management
- Model management

### LLM Service

Manages local LLM inference:
- Auto-detects model capabilities (tool calling support)
- Supports MoE (Mixture of Experts) models
- Configurable sampler settings (temperature, top_p, DRY, XTC, Mirostat, etc.)
- CUDA/GPU support when available

### Memory Service

Vector-based memory system:
- Stores conversation context
- Semantic search capabilities
- ChromaDB backend

### Tools Service

Extensible tool execution system:
- Built-in tools: web search, code execution, file access, calendar, memory
- Sandboxed execution environment
- Tool registry for dynamic tool management

## Configuration

### Core Services Shared Venv

Core services (memory, tools, gateway, llm) share a single virtual environment at `services/.core_venv`. This:
- Reduces disk space usage
- Ensures package compatibility
- Speeds up installation
- Allows simultaneous startup

### Service Ports

- Gateway: 8000
- LLM: 8001
- Whisper: 8003
- Piper: 8004
- Memory: 8005
- Tools: 8006
- Frontend: 8002
- Kokoro: 8880
- Chatterbox: 4123

## Usage

### Launcher GUI

The launcher provides:
- Service installation/uninstallation
- Service start/stop controls
- Real-time service logs
- Status monitoring
- Health checks

### Web Interface

Access the web UI at `http://localhost:8002` to:
- Chat with the AI assistant
- Load and manage LLM models
- Configure sampler settings
- Manage memory settings
- Configure tools
- Monitor service status

## Development

### Adding a New Service

1. Create service directory in `services/`
2. Add service configuration to `launcher/manager.py`:
   - Add to `self.services` dictionary
   - Define port, start command, install command
   - Set `is_core: True` if it should use shared venv
3. Update launcher UI if needed

### Service Requirements

- Each service should have a `requirements.txt`
- Core services share `services/.core_venv`
- Optional services use their own `.venv` in their directory
- Services should expose a `/health` endpoint

## Troubleshooting

### Services Won't Start

- Check if ports are already in use
- Verify services are installed (check install status in launcher)
- Check service logs in the launcher console

### Missing Dependencies

- Click "Reinstall All" in the launcher to force reinstall all packages
- Check that Python 3.10+ is installed
- Verify virtual environments are created correctly

### Port Conflicts

- The launcher will detect port conflicts and automatically kill stuck processes
- Stop other processes using the ports or change port configuration

### CUDA/GPU Issues

- CUDA detection is handled by the LLM service
- If CUDA is not available, services will use CPU mode
- Install CUDA toolkit and rebuild llama-cpp-python for GPU support

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

