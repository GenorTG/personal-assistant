#!/bin/bash
# Install all dependencies for function calling implementation
# Uses existing .core_venv or creates new one

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use existing core venv if available, otherwise create project venv
if [ -d "$PROJECT_ROOT/services/.core_venv" ]; then
    VENV_DIR="$PROJECT_ROOT/services/.core_venv"
    echo "Using existing core venv: $VENV_DIR"
elif [ -d "$PROJECT_ROOT/.venv" ]; then
    VENV_DIR="$PROJECT_ROOT/.venv"
    echo "Using existing project venv: $VENV_DIR"
else
    VENV_DIR="$PROJECT_ROOT/.venv"
    echo "Creating new venv: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"
echo "Python: $(which python)"
echo "Version: $(python --version)"
echo ""

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel --quiet

# Install main requirements (excluding PyGObject for now if it fails)
echo "Installing main requirements..."
python -m pip install -r "$PROJECT_ROOT/requirements.txt" || {
    echo "Warning: Some packages failed to install, continuing..."
    python -m pip install faster-whisper==1.0.3 pyttsx3==2.90 soundfile>=0.13.0 "numpy>=1.22.0,<2.0.0" aiofiles==24.1.0 python-multipart>=0.0.13 httpx==0.27.0 python-dotenv==1.0.1 jsonschema==4.23.0 psutil==5.9.8 "rich>=13.0.0" "requests>=2.28.0" "pydub>=0.25.1" sse-starlette>=3.0.2 || true
}

# Try PyGObject separately (may fail on some systems)
echo "Installing PyGObject (may fail on systems without GTK development libraries)..."
python -m pip install "PyGObject>=3.40.0" || echo "Warning: PyGObject installation failed (launcher may not work)"

# Install gateway requirements
echo ""
echo "Installing gateway requirements..."
python -m pip install -r "$PROJECT_ROOT/services/gateway/requirements.txt" || {
    echo "Installing gateway requirements individually..."
    python -m pip install fastapi uvicorn[standard] httpx aiohttp python-multipart websockets pydantic pydantic-settings python-dotenv aiofiles aiosqlite sentence-transformers chromadb sympy "numpy>=1.22.0,<2.0.0" openai gguf Pillow faster-whisper piper-tts kokoro-onnx soundfile jsonschema huggingface_hub psutil nvidia-ml-py cryptography pyttsx3 || true
}

# Install llama-cpp-python (may take time)
echo ""
echo "Installing llama-cpp-python (this may take a while)..."
if command -v nvidia-smi &> /dev/null; then
    echo "CUDA detected - installing with GPU support..."
    python -m pip install llama-cpp-python[server] || {
        echo "Attempting CPU-only installation..."
        python -m pip install llama-cpp-python[server] --no-cache-dir
    }
else
    echo "Installing CPU-only version..."
    python -m pip install llama-cpp-python[server]
fi

# Verify critical packages
echo ""
echo "Verifying installations..."
python -c "import huggingface_hub; print('✓ huggingface_hub:', huggingface_hub.__version__)" || echo "✗ huggingface_hub"
python -c "import llama_cpp; print('✓ llama-cpp-python')" || echo "✗ llama-cpp-python"
python -c "import pydantic_settings; print('✓ pydantic-settings')" || echo "✗ pydantic-settings"
python -c "import fastapi; print('✓ fastapi:', fastapi.__version__)" || echo "✗ fastapi"

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "Virtual environment: $VENV_DIR"
echo "To activate: source $VENV_DIR/bin/activate"
