# Personal Assistant

A privacy-focused, local AI assistant with modular microservices architecture. Features local LLM inference via OpenAI-compatible server, speech-to-text, text-to-speech, memory management, and tool execution capabilities.

## Features

- **Local LLM Inference**: Run large language models locally using OpenAI-compatible server (llama-cpp-python)
- **Tool Calling**: Native support for function calling with built-in tools (calendar, web search, file access, etc.)
- **Speech-to-Text**: Whisper-based STT service
- **Text-to-Speech**: Multiple TTS options (Piper, Kokoro, Chatterbox)
- **Memory System**: Vector-based memory with ChromaDB for conversation context
- **Tool Execution**: Extensible tool system for code execution, web search, file access, and more
- **Web Interface**: Modern Next.js frontend for chat and settings management
- **Service Management**: GUI launcher for easy service installation and management

## Architecture

The application uses a microservices architecture with the following services:

### Core Services (Shared Virtual Environment)

These services share a single Python virtual environment (`services/.core_venv`):

- **Gateway** (Port 8000): Main API gateway that integrates:
  - **LLM Management**: Manages OpenAI-compatible server (port 8001) that starts automatically when a model is loaded
  - **Memory System**: Direct integration for vector-based memory storage and retrieval using ChromaDB
  - **Tools System**: Direct integration for tool execution and tool registry management
  - Handles routing, database, chat logic, and coordinates optional services

### Optional Services

- **Frontend** (Port 8002): Next.js web interface (uses npm, no Python venv)
- **Whisper STT** (Port 8003): Speech-to-text using Faster-Whisper (uses `.core_venv`)
- **Piper TTS** (Port 8004): Lightweight text-to-speech (uses `.core_venv`)
- **Kokoro TTS** (Port 8880): High-quality ONNX-based TTS (uses `.core_venv`)
- **Chatterbox TTS** (Port 4123): Advanced TTS with voice cloning (uses own `.venv`, Python 3.11 required)

## LLM Architecture

The LLM system uses an OpenAI-compatible server architecture:

1. **Model Loading**: When a model is loaded via the Gateway API, the Gateway automatically starts an OpenAI-compatible server (llama-cpp-python) on port 8001
2. **Generation**: All text generation requests are sent to the OpenAI-compatible server via HTTP requests to `/v1/chat/completions`
3. **Tool Calling**: Tool calling works natively through the OpenAI-compatible API format
4. **Server Lifecycle**: The server starts when a model is loaded and stops when the model is unloaded

This architecture provides:
- Standard OpenAI-compatible API for all generation
- Native tool calling support
- Single, consistent generation path
- Easy debugging and maintenance

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ (for frontend)
- Git (for external services)
- GTK4 and python-gobject (for launcher on Linux)
  - Install via: `sudo pacman -S gtk4 python-gobject` (Arch/Garuda)
- CUDA Toolkit (optional, for GPU acceleration)

### Installation

1. **Install System Dependencies** (Linux/Garuda):
   - **Required**: Install GTK4 and python-gobject: `sudo pacman -S gtk4 python-gobject`
   - This is necessary for the launcher GUI to work

2. **Install GTK4 Launcher**:
   - Run `cd launcher-gtk4 && ./install.sh`
   - Or install Python dependencies manually: `pip install --user -r launcher-gtk4/requirements.txt`
   - Launch from application menu (double-click `Personal-Assistant`) or run `./start.sh` from project root

3. **Install Services**:
   - Services are installed automatically when first started
   - Core services use shared virtual environment (`services/.core_venv`)
   - Chatterbox uses its own venv (Python 3.11)

4. **Start Services**:
   - Use the GTK4 launcher to start/stop services
   - Or start manually:
     - Gateway: `cd services/gateway && source ../.core_venv/bin/activate && python -m uvicorn src.main:app --port 8000`
     - Frontend: `cd services/frontend && npm run dev`
   - Access the web interface at `http://localhost:8002`

## Project Structure

```
personal-assistant/
├── launcher-gtk4/         # GTK4 launcher (Linux/Garuda)
│   ├── main.py           # Application entry point
│   ├── service_manager.py # Service process management
│   └── ui/               # GTK4 UI components
├── legacy-python-launcher/ # Old Python launcher (deprecated)
├── services/              # All microservices
│   ├── .core_venv/       # Shared venv for gateway, whisper, piper, kokoro
│   ├── gateway/          # API Gateway (main backend, includes LLM/memory/tools/STT/TTS)
│   ├── frontend/         # Next.js frontend
│   ├── tts-chatterbox/   # Chatterbox TTS (optional HTTP service)
│   └── data/             # Shared data directory
```

## Service Details

### Gateway Service

Main API server that integrates all core functionality:

- **LLM Management**: 
  - Manages OpenAI-compatible server (port 8001) that starts automatically when a model is loaded
  - Auto-detects model capabilities (tool calling support)
  - Supports MoE (Mixture of Experts) models
  - Configurable sampler settings (temperature, top_p, DRY, XTC, Mirostat, etc.)
  - CUDA/GPU support when available
  - All generation goes through the OpenAI-compatible server API
- **Memory System**: Direct integration for vector-based memory
  - Stores conversation context
  - Semantic search capabilities
  - ChromaDB backend
- **Tools System**: Direct integration for tool execution
  - Built-in tools: web search, code execution, file access, calendar, memory
  - Sandboxed execution environment
  - Tool registry for dynamic tool management
- Coordinates optional services (STT, TTS)
- Settings management
- Model management

## Configuration

### Virtual Environments

- **`.core_venv`** (`services/.core_venv`): Shared by Gateway, Whisper, Piper, and Kokoro
  - Reduces disk space usage
  - Ensures package compatibility
  - Speeds up installation
- **Chatterbox venv** (`services/tts-chatterbox/.venv`): Exclusive to Chatterbox (Python 3.11 required)
- **Frontend**: Uses npm/node_modules (no Python venv)

### Service Ports

- **Gateway**: 8000 (includes LLM, Memory, Tools - all integrated)
- **LLM Server**: 8001 (OpenAI-compatible server, started automatically by Gateway when model loads)
- **Frontend**: 8002
- **Whisper STT**: 8003 (optional)
- **Piper TTS**: 8004 (optional)
- **Kokoro TTS**: 8880 (optional)
- **Chatterbox TTS**: 4123 (optional)

## Usage

### GTK4 Launcher (Linux/Garuda)

The GTK4 launcher provides:
- Service start/stop/restart controls
- Real-time status indicators
- Service logs viewing (separate tabs for Gateway, Frontend, Chatterbox)
- Resource monitoring
- Clean, native Linux interface

### Web Interface

Access the web UI at `http://localhost:8002` to:
- Chat with the AI assistant
- Load and manage LLM models (server starts automatically when model loads)
- Configure sampler settings
- Manage memory settings
- Configure tools
- Monitor service status

## Development

### Adding a New Service

1. Create service directory in `services/`
2. Add service configuration to `launcher-gtk4/config.py`:
   - Add to SERVICES dictionary
   - Define port, directory, venv, and start command
   - Set `venv: core_venv` to use shared venv, or specify own venv path
3. Update launcher UI if needed

### Service Requirements

- Each service should have a `requirements.txt`
- Gateway, Whisper, Piper, and Kokoro share `services/.core_venv`
- Chatterbox uses its own `.venv` (Python 3.11)
- Services should expose a `/health` endpoint
- Gateway integrates LLM (via OpenAI-compatible server), Memory, and Tools

## Troubleshooting

### Services Won't Start

- Check if ports are already in use: `lsof -i :8000` (or respective port)
- Verify services are installed (check venv exists)
- Check service logs in the launcher or terminal output
- Ensure virtual environments are created: `python3 -m venv services/.core_venv`

### Missing Dependencies

- Install dependencies: `source services/.core_venv/bin/activate && pip install -r services/gateway/requirements.txt`
- Check that Python 3.10+ is installed
- Verify virtual environments are created correctly

### Port Conflicts

- Check for processes using ports: `lsof -i :PORT` or `netstat -tulpn | grep PORT`
- Stop other processes using the ports or change port configuration in `launcher-gtk4/config.py`

### CUDA/GPU Issues

- CUDA detection is handled by the Gateway's LLM manager
- If CUDA is not available, services will use CPU mode
- Install CUDA toolkit and rebuild llama-cpp-python for GPU support

### LLM Server Issues

- The OpenAI-compatible server (port 8001) starts automatically when a model is loaded
- If the server fails to start, check Gateway logs for error messages
- Ensure llama-cpp-python is installed: `pip install llama-cpp-python`
- For GPU support: `pip install llama-cpp-python[cuda]`

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
