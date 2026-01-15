#!/bin/bash
# Personal Assistant - Update and Launch Script
# This script updates the repository, reinstalls dependencies, rebuilds frontend, and launches

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Keep terminal window open on errors
trap 'echo ""; echo "Press Enter to exit..."; read' ERR

echo "=========================================="
echo "Personal Assistant - Update & Launch"
echo "=========================================="
echo ""

# Check if git repository
if [ ! -d ".git" ]; then
    echo "⚠ Warning: Not a git repository. Skipping git pull."
    SKIP_GIT=1
else
    SKIP_GIT=0
fi

# Update from git
if [ $SKIP_GIT -eq 0 ]; then
    echo "[1/6] Updating from git repository..."
    if git pull; then
        echo "✓ Repository updated"
    else
        echo "⚠ Warning: git pull failed. Continuing with installation..."
    fi
else
    echo "[1/6] Skipping git update (not a git repository)"
fi

# Check prerequisites
echo ""
echo "[2/6] Checking prerequisites..."
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

# Setup/Update Python virtual environment
echo ""
echo "[3/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment exists"
fi

source .venv/bin/activate
echo "✓ Activated virtual environment"

# Upgrade pip
echo ""
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

# Reinstall Python dependencies
echo ""
echo "[4/6] Reinstalling Python dependencies..."
echo "This may take several minutes..."

if [ -f "requirements.txt" ]; then
    python -m pip install -r requirements.txt --upgrade || {
        echo "⚠ Some packages failed, continuing with core packages..."
        python -m pip install faster-whisper==1.0.3 pyttsx3==2.90 soundfile>=0.13.0 "numpy>=1.22.0,<2.0.0" aiofiles==24.1.0 python-multipart>=0.0.13 httpx==0.27.0 python-dotenv==1.0.1 jsonschema==4.23.0 psutil==5.9.8 "rich>=13.0.0" "requests>=2.28.0" "pydub>=0.25.1" sse-starlette>=3.0.2 --upgrade || true
    }
    echo "✓ Main requirements updated"
fi

# Try PyGObject separately (may fail on some systems)
python -m pip install "PyGObject>=3.40.0" --upgrade || echo "⚠ PyGObject update failed (optional)"

if [ -f "services/gateway/requirements.txt" ]; then
    python -m pip install -r services/gateway/requirements.txt --upgrade || {
        echo "⚠ Installing gateway requirements individually..."
        python -m pip install fastapi uvicorn[standard] httpx aiohttp python-multipart websockets pydantic pydantic-settings python-dotenv aiofiles aiosqlite sentence-transformers chromadb sympy "numpy>=1.22.0,<2.0.0" openai gguf Pillow faster-whisper piper-tts kokoro-onnx soundfile jsonschema huggingface_hub psutil nvidia-ml-py cryptography pyttsx3 --upgrade || true
    }
    echo "✓ Gateway requirements updated"
fi

# Update llama-cpp-python
echo ""
echo "Updating llama-cpp-python (this may take a while)..."
if command -v nvidia-smi &> /dev/null; then
    python -m pip install llama-cpp-python[server] --upgrade || {
        echo "⚠ Attempting CPU-only installation..."
        python -m pip install llama-cpp-python[server] --no-cache-dir --upgrade || true
    }
else
    python -m pip install llama-cpp-python[server] --upgrade || true
fi
echo "✓ llama-cpp-python update attempted"

# Reinstall frontend dependencies
echo ""
echo "[5/6] Reinstalling and rebuilding frontend..."
cd services/frontend
echo "Removing old node_modules and build..."
rm -rf node_modules .next
echo "Installing frontend dependencies (this may take a while)..."
npm install
echo "✓ Frontend dependencies reinstalled"
echo "Building frontend (this may take a while)..."
npm run build
echo "✓ Frontend rebuilt"
cd "$SCRIPT_DIR"

# Reinstall Electron dependencies
echo ""
echo "[6/6] Reinstalling Electron dependencies..."
cd electron-app
echo "Removing old node_modules..."
rm -rf node_modules
echo "Installing Electron dependencies..."
npm install
echo "✓ Electron dependencies reinstalled"
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "Update complete! Launching application..."
echo "=========================================="
echo ""

# Launch the application
cd electron-app
npm start
