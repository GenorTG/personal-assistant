# LLM Service (llama-cpp-python)

This service provides an OpenAI-compatible LLM inference server using `llama-cpp-python`.

## How It Works

**Important**: This service is managed by the Gateway, not the Launcher.

1. **Install** the LLM service via the Launcher (installs dependencies)
2. **Start** the Gateway service via the Launcher
3. **Load a model** via the Frontend's Model Browser
4. The Gateway automatically starts the llama-cpp-python server with your model

The "Start" button in the Launcher shows "READY" status - this means the service is installed and ready for the Gateway to use.

## Installation

The service is installed via the launcher. It will:
1. Create a virtual environment in `.venv/`
2. Install `llama-cpp-python` from PyPI
3. Install server dependencies (uvicorn, fastapi, etc.)

## GPU Support

The installer automatically detects:
- **CUDA** (NVIDIA GPUs) - Sets `CMAKE_ARGS="-DGGML_CUDA=on"`
- **Metal** (Apple Silicon) - Sets `CMAKE_ARGS="-DGGML_METAL=on"`

If GPU installation fails, it falls back to CPU-only.

## Manual Start (for testing)

You can start the server manually for testing:
```bash
.venv/Scripts/python -m llama_cpp.server --model path/to/model.gguf --port 8001
```

## API Endpoints

The server provides OpenAI-compatible endpoints:
- `GET /v1/models` - List loaded models
- `POST /v1/chat/completions` - Chat completions (streaming supported)
- `POST /v1/completions` - Text completions
- `POST /v1/embeddings` - Text embeddings

## Configuration

Models are stored in `data/models/` and loaded via the Gateway API.

