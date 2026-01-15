#!/bin/bash
# Personal Assistant - Initial Installation Script
# Run this script after cloning the repository to set up all dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Keep terminal window open on errors
trap 'echo ""; echo "Press Enter to exit..."; read' ERR

echo "=========================================="
echo "Personal Assistant - Installation"
echo "=========================================="
echo ""

# Check prerequisites
echo "[1/6] Checking prerequisites..."
MISSING_DEPS=0

if ! command -v python3 &> /dev/null; then
    echo "✗ python3 not found"
    MISSING_DEPS=1
else
    echo "✓ python3: $(python3 --version)"
fi

if ! command -v node &> /dev/null; then
    echo "✗ node not found"
    MISSING_DEPS=1
else
    echo "✓ node: $(node --version)"
fi

if ! command -v npm &> /dev/null; then
    echo "✗ npm not found"
    MISSING_DEPS=1
else
    echo "✓ npm: $(npm --version)"
fi

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "ERROR: Missing required dependencies. Please install them first."
    exit 1
fi

# Setup Python virtual environment
echo ""
echo "[2/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

source .venv/bin/activate
echo "✓ Activated virtual environment"

# Upgrade pip
echo ""
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

# Install Python dependencies
echo ""
echo "[3/6] Installing Python dependencies..."
echo "This may take several minutes..."

if [ -f "requirements.txt" ]; then
    python -m pip install -r requirements.txt || {
        echo "⚠ Some packages failed, continuing with core packages..."
        python -m pip install faster-whisper==1.0.3 pyttsx3==2.90 soundfile>=0.13.0 "numpy>=1.22.0,<2.0.0" aiofiles==24.1.0 python-multipart>=0.0.13 httpx==0.27.0 python-dotenv==1.0.1 jsonschema==4.23.0 psutil==5.9.8 "rich>=13.0.0" "requests>=2.28.0" "pydub>=0.25.1" sse-starlette>=3.0.2 || true
    }
    echo "✓ Main requirements installed"
fi

# Try PyGObject separately (may fail on some systems)
echo "Installing PyGObject (optional, may fail on systems without GTK)..."
python -m pip install "PyGObject>=3.40.0" || echo "⚠ PyGObject installation failed (launcher may not work)"

if [ -f "services/gateway/requirements.txt" ]; then
    python -m pip install -r services/gateway/requirements.txt || {
        echo "⚠ Installing gateway requirements individually..."
        python -m pip install fastapi uvicorn[standard] httpx aiohttp python-multipart websockets pydantic pydantic-settings python-dotenv aiofiles aiosqlite sentence-transformers chromadb sympy "numpy>=1.22.0,<2.0.0" openai gguf Pillow faster-whisper piper-tts kokoro-onnx soundfile jsonschema huggingface_hub psutil nvidia-ml-py cryptography pyttsx3 || true
    }
    echo "✓ Gateway requirements installed"
fi

# Install llama-cpp-python (may take time)
echo ""
echo "Installing llama-cpp-python (this may take a while)..."
if command -v nvidia-smi &> /dev/null; then
    echo "CUDA detected - installing with GPU support..."
    python -m pip install llama-cpp-python[server] || {
        echo "⚠ Attempting CPU-only installation..."
        python -m pip install llama-cpp-python[server] --no-cache-dir || true
    }
else
    echo "Installing CPU-only version..."
    python -m pip install llama-cpp-python[server] || true
fi
echo "✓ llama-cpp-python installation attempted"

# Install frontend dependencies
echo ""
echo "[4/6] Installing frontend dependencies..."
cd services/frontend
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies (this may take a while)..."
    npm install
    echo "✓ Frontend dependencies installed"
else
    echo "✓ Frontend dependencies already installed"
fi
cd "$SCRIPT_DIR"

# Build frontend
echo ""
echo "[5/6] Building frontend..."
cd services/frontend
echo "Building frontend (this may take a while)..."
npm run build
echo "✓ Frontend built successfully"
cd "$SCRIPT_DIR"

# Install Electron dependencies
echo ""
echo "[6/6] Installing Electron dependencies..."
cd electron-app
if [ ! -d "node_modules" ]; then
    echo "Installing Electron dependencies..."
    npm install
    echo "✓ Electron dependencies installed"
else
    echo "✓ Electron dependencies already installed"
fi
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""
echo "You can now:"
echo "  - Run './start.sh' to start the application"
echo "  - Run './update-and-start.sh' to update and launch"
echo ""
echo "To activate the Python virtual environment manually:"
echo "  source .venv/bin/activate"
echo ""
