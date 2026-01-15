#!/bin/bash
# Setup virtual environment and install all dependencies for function calling implementation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "=========================================="
echo "Setting up Python Virtual Environment"
echo "=========================================="
echo ""

# Check Python version
echo "[1/4] Checking Python version..."
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Found: $PYTHON_CMD version $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
echo ""
echo "[2/4] Creating virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at: $VENV_DIR"
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "[3/4] Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "✓ Activated: $(which python)"
echo "Python version: $(python --version)"

# Upgrade pip
echo ""
echo "Upgrading pip..."
python -m pip install --upgrade pip setuptools wheel

# Install dependencies
echo ""
echo "[4/4] Installing dependencies..."
echo "This may take several minutes..."

# Install main requirements
echo "Installing main requirements from requirements.txt..."
python -m pip install -r "$PROJECT_ROOT/requirements.txt"

# Install gateway requirements
echo "Installing gateway requirements..."
python -m pip install -r "$PROJECT_ROOT/services/gateway/requirements.txt"

# Verify critical packages
echo ""
echo "Verifying critical packages..."
python -c "import huggingface_hub; print('✓ huggingface_hub:', huggingface_hub.__version__)" || echo "✗ huggingface_hub not installed"
python -c "import llama_cpp; print('✓ llama-cpp-python installed')" || echo "✗ llama-cpp-python not installed"
python -c "import pydantic_settings; print('✓ pydantic-settings installed')" || echo "✗ pydantic-settings not installed"
python -c "import fastapi; print('✓ fastapi:', fastapi.__version__)" || echo "✗ fastapi not installed"

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "To activate the virtual environment:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Virtual environment location: $VENV_DIR"
