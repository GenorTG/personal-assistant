#!/bin/bash

# Chatterbox TTS API Installation Script

set -e

echo "🚀 Installing Chatterbox TTS API..."

# Check for Python 3.11 specifically
if ! command -v python3.11 &> /dev/null; then
    echo "❌ Error: python3.11 is required but not found"
    echo "Please install Python 3.11: sudo pacman -S python311"
    exit 1
fi

python_version=$(python3.11 --version 2>&1 | grep -oP '(?<=Python )\d+\.\d+')
required_version="3.11"

if ! python3.11 -c "import sys; exit(0 if sys.version_info >= (3, 11) and sys.version_info < (3, 12) else 1)" 2>/dev/null; then
    echo "❌ Error: Python 3.11 is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version check passed: $python_version"

# Create virtual environment with Python 3.11
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment with Python 3.11..."
    python3.11 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating environment configuration..."
    if [ -f "env.example" ]; then
        cp env.example .env
        echo "📝 Please edit .env to customize your configuration"
    else
        echo "⚠️  Warning: env.example not found, skipping .env creation"
        echo "   You can create .env manually if needed"
    fi
fi

# Check if voice sample exists
if [ ! -f "voice-sample.mp3" ]; then
    echo "⚠️  Warning: voice-sample.mp3 not found"
    echo "   You can add your own voice sample or use the provided one"
fi

echo ""
echo "🎉 Installation complete!"
echo ""
echo "To start the API:"
echo "  source venv/bin/activate"
echo "  python api.py"
echo ""
echo "Alternative with uv (faster, better dependency resolution):"
echo "  uv sync && uv run api.py"
echo "  See docs/UV_MIGRATION.md for details"
echo ""
echo "Or with Docker:"
echo "  docker compose up -d"
echo ""
echo "Test the API:"
echo "  curl -X POST http://localhost:4123/v1/audio/speech \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"input\": \"Hello world!\"}' \\"
echo "    --output test.wav" 