#!/bin/bash
# Install script for services on Arch/Garuda Linux

set -e

echo "=========================================="
echo "Installing Personal Assistant Services"
echo "=========================================="
echo ""

# Check for Python 3.12 (required for prebuilt wheels)
echo "[1/3] Checking Python 3.12 availability..."
REQUIRED_PYTHON="3.12"
PYTHON_312=""

# Try to find python3.12
if command -v python3.12 &> /dev/null; then
    PYTHON_312="python3.12"
    PYTHON_312_VERSION=$(python3.12 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
    if [ "$PYTHON_312_VERSION" = "$REQUIRED_PYTHON" ]; then
        echo "✅ Python 3.12 found: $(which python3.12)"
    else
        echo "⚠️  python3.12 found but version is $PYTHON_312_VERSION, not $REQUIRED_PYTHON"
        PYTHON_312=""
    fi
fi

if [ -z "$PYTHON_312" ]; then
    echo "ERROR: Python 3.12 is required for prebuilt wheel support."
    echo "       Please install Python 3.12:"
    echo "       - Arch/Garuda: sudo pacman -S python312"
    echo "       - Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    exit 1
fi
echo ""

# Check and recreate virtual environment if needed
CORE_VENV="../services/.core_venv"
VENV_PYTHON=""

if [ -d "$CORE_VENV" ]; then
    # Check if venv exists and what Python version it uses
    VENV_PYTHON_BIN="$CORE_VENV/bin/python"
    if [ -f "$VENV_PYTHON_BIN" ]; then
        VENV_VERSION=$("$VENV_PYTHON_BIN" --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        if [ "$VENV_VERSION" != "$REQUIRED_PYTHON" ]; then
            echo "[2/3] Existing venv uses Python $VENV_VERSION, but Python $REQUIRED_PYTHON is required."
            echo "      Deleting incompatible venv..."
            rm -rf "$CORE_VENV"
            echo "      ✅ Incompatible venv deleted."
        else
            echo "[2/3] Existing venv uses Python $REQUIRED_PYTHON - compatible!"
            VENV_PYTHON="$VENV_PYTHON_BIN"
        fi
    else
        echo "[2/3] Venv directory exists but Python binary not found, recreating..."
        rm -rf "$CORE_VENV"
    fi
fi

# Create virtual environment if it doesn't exist or was deleted
if [ ! -d "$CORE_VENV" ]; then
    echo "[2/3] Creating core virtual environment with Python 3.12..."
    "$PYTHON_312" -m venv "$CORE_VENV"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment with Python 3.12"
        exit 1
    fi
    echo "✅ Virtual environment created with Python 3.12."
    VENV_PYTHON="$CORE_VENV/bin/python"
fi
echo ""

# Install Python dependencies
echo "[3/3] Installing Python dependencies..."
echo "This may take a moment..."

# Activate venv
source "$CORE_VENV/bin/activate"
echo "Using Python from venv: $(which python)"
echo "Python version: $(python --version)"
echo ""

# Check if uv is available and set pip command accordingly
if command -v uv &> /dev/null; then
    echo "✅ Using uv for faster package installation..."
    PIP_CMD="uv pip"
else
    echo "⚠️  Using pip (consider installing 'uv' for faster dependency resolution)..."
    echo "   Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    PIP_CMD="python -m pip"
fi
echo ""

# Upgrade pip (or ensure uv is up to date)
if [ "$PIP_CMD" = "uv pip" ]; then
    # uv doesn't need upgrading, but we can sync pip if needed
    $PIP_CMD install --upgrade pip 2>/dev/null || true
else
    $PIP_CMD install --upgrade pip
fi

# Detect CUDA and install PyTorch with CUDA support first
echo ""
echo "Detecting CUDA availability..."
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "CUDA detected! Installing PyTorch with latest CUDA support..."
    echo "This may take a moment..."
    # Try CUDA 12.8 first (latest stable CUDA version)
    # Using official PyTorch command: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    echo "Trying CUDA 12.8 (latest stable version)..."
    $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ PyTorch with CUDA 12.8 installed successfully."
    else
        echo "⚠️  CUDA 12.8 not available, trying CUDA 13.0..."
        $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "✅ PyTorch with CUDA 13.0 installed successfully."
        else
            echo "⚠️  CUDA 13.0 not available, trying CUDA 12.6..."
            $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126 2>/dev/null
            if [ $? -eq 0 ]; then
                echo "✅ PyTorch with CUDA 12.6 installed successfully."
            else
                echo "⚠️  CUDA 12.6 not available, trying CUDA 12.4..."
                $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
                if [ $? -eq 0 ]; then
                    echo "✅ PyTorch with CUDA 12.4 installed successfully."
                else
                    echo "⚠️  CUDA 12.4 install failed, trying CUDA 12.1..."
                    $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
                    if [ $? -eq 0 ]; then
                        echo "✅ PyTorch with CUDA 12.1 installed successfully."
                    else
                        echo "⚠️  CUDA 12.1 install failed, trying CUDA 11.8..."
                        $PIP_CMD install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
                        if [ $? -eq 0 ]; then
                            echo "✅ PyTorch with CUDA 11.8 installed successfully."
                        else
                            echo "⚠️  All CUDA installs failed, falling back to CPU-only..."
                            $PIP_CMD install torch torchvision torchaudio
                        fi
                    fi
                fi
            fi
        fi
    fi
else
    echo "CUDA not detected, installing CPU-only PyTorch..."
    $PIP_CMD install torch torchvision torchaudio
fi

# Install other dependencies
# NOTE: requirements.txt has torch/torchaudio commented out to avoid conflicts
echo ""
echo "Installing other dependencies..."
echo "This may take several minutes..."

# Use uv if available (already detected above)
if [ "$PIP_CMD" = "uv pip" ]; then
    echo "✅ Using uv for faster dependency resolution..."
    # Handle llama-cpp-python CUDA separately before using uv
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        echo "CUDA detected! Installing llama-cpp-python with CUDA support in gateway venv..."
        echo "Using Python: $(which python)"
        PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        echo "Python version: $PYTHON_VERSION (should be 3.12 for prebuilt wheels)"
        
        # Uninstall any existing CPU-only version
        $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
        
        # Step 1: Try to install using ONLY prebuilt wheels from PyPI (no building, no cache)
        echo "Checking for prebuilt wheel from PyPI (no build required)..."
        if $PIP_CMD install llama-cpp-python[server] --only-binary :all: --no-cache-dir 2>/dev/null; then
            echo "✅ Prebuilt wheel from PyPI installed! No build needed."
            # Check CUDA support
            CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
            if [ "$CUDA_AVAILABLE" = "True" ]; then
                echo "✅ Prebuilt wheel has CUDA support! Installation complete."
            else
                echo "⚠️  Prebuilt wheel doesn't have CUDA support, checking cache..."
                $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
                CUDA_AVAILABLE="False"  # Check cache or build below
            fi
        else
            echo "⚠️  No prebuilt wheel available for Python $PYTHON_VERSION"
            if [ "$PYTHON_VERSION" = "3.13" ]; then
                echo "   Python 3.13 requires building from source (prebuilt wheels not available yet)"
            fi
            CUDA_AVAILABLE="False"  # Check cache or build below
        fi
        
        # Step 2: If no prebuilt wheel, try installing from pip cache (previously built wheel)
        if [ "$CUDA_AVAILABLE" != "True" ]; then
            echo "Checking pip cache for previously built wheel..."
            # Try installing normally (will use cache if available, or build if not)
            # NOTE: Not using --no-cache-dir so we can use cached wheels!
            if $PIP_CMD install llama-cpp-python[server] 2>/dev/null; then
                echo "✅ Installed from cache or using cached wheel!"
                # Check if CUDA support is available
                CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
                if [ "$CUDA_AVAILABLE" = "True" ]; then
                    echo "✅ Cached wheel has CUDA support! No rebuild needed."
                else
                    echo "⚠️  Cached wheel doesn't have CUDA support, clearing cache and rebuilding..."
                    $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
                    # Clear the cached wheel so we don't reuse the CPU-only version
                    $PIP_CMD cache purge llama-cpp-python 2>/dev/null || true
                    echo "🗑️  Cleared CPU-only wheel from cache"
                fi
            else
                echo "⚠️  No cached wheel found, will build from source..."
            fi
        fi
        
        # Step 3: Build from source if needed (and cache the result for next time)
        if [ "$CUDA_AVAILABLE" != "True" ]; then
            echo "Building llama-cpp-python from source with CUDA support..."
            # Detect number of CPU cores for parallel build
            if command -v nproc &> /dev/null; then
                CORES=$(nproc)
            elif [ -f /proc/cpuinfo ]; then
                CORES=$(grep -c processor /proc/cpuinfo)
            else
                CORES=4  # Fallback to 4 cores
            fi
            echo "⚡ Using $CORES CPU cores for parallel build..."
            echo "💾 Wheel will be cached for future installations (no rebuild needed next time)..."
            
            $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
            # Clear any cached wheels to force a fresh CUDA build
            echo "🗑️  Clearing cached wheels to force fresh CUDA build..."
            $PIP_CMD cache purge llama-cpp-python 2>/dev/null || true
            # Also try to clear the entire cache if the specific package purge didn't work
            $PIP_CMD cache purge 2>/dev/null || true
            
            # Set CMAKE_ARGS with CUDA and parallel build
            export CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_BUILD_PARALLEL_LEVEL=$CORES"
            export FORCE_CMAKE=1
            export CMAKE_BUILD_PARALLEL_LEVEL=$CORES
            # Use regular pip for CUDA source builds (uv pip may not properly pass CMAKE_ARGS)
            # Use --no-binary to force building from source (ignore any cached wheels)
            # The built wheel will be automatically cached by pip for next time
            echo "🔧 Building with regular pip to ensure CMAKE_ARGS are respected..."
            python -m pip install llama-cpp-python[server] --no-binary llama-cpp-python --force-reinstall || {
                echo "⚠️  CUDA build failed, trying CPU-only version..."
                unset CMAKE_ARGS
                unset FORCE_CMAKE
                unset CMAKE_BUILD_PARALLEL_LEVEL
                python -m pip install llama-cpp-python[server] || exit 1
            }
            # Verify the CUDA wheel was built and installed correctly
            CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
            if [ "$CUDA_AVAILABLE" = "True" ]; then
                echo "✅ CUDA wheel built successfully! Wheel is cached for future installations."
            else
                echo "⚠️  Warning: CUDA support not detected after build"
            fi
            unset CMAKE_ARGS
            unset FORCE_CMAKE
            unset CMAKE_BUILD_PARALLEL_LEVEL
            unset CMAKE_ARGS
            unset FORCE_CMAKE
            unset CMAKE_BUILD_PARALLEL_LEVEL
        fi
        
        # Verify CUDA support
        echo "Verifying CUDA support in llama-cpp-python (in gateway venv)..."
        python -c 'from llama_cpp import llama_supports_gpu_offload; print("GPU offload supported:", llama_supports_gpu_offload())' 2>/dev/null || {
            echo "⚠️  CUDA support verification failed, but installation may still work"
        }
    fi
    # Install all requirements with uv (llama-cpp-python will be skipped if already installed)
    uv pip install -r "../services/gateway/requirements.txt"
    INSTALL_SUCCESS=$?
else
    echo "Installing in smaller batches to avoid resolution-too-deep errors..."
    echo "Note: PyTorch already installed with CUDA, skipping torch/torchaudio from requirements.txt"
    
    # Upgrade pip first
    $PIP_CMD install --upgrade pip setuptools wheel
    
    # Install in logical batches to reduce dependency resolution complexity
    echo "[1/5] Installing web framework dependencies..."
    $PIP_CMD install fastapi uvicorn[standard] httpx aiohttp python-multipart websockets pydantic pydantic-settings python-dotenv aiofiles || exit 1
    
    echo "[2/5] Installing database and core dependencies..."
    # Pin numpy to <2.0.0 to avoid ChromaDB compatibility issues
    # First check if numpy 2.x is installed and downgrade if needed
    echo "Checking NumPy version..."
    if python -c "import numpy; exit(0 if numpy.__version__.startswith('1.') else 1)" 2>/dev/null; then
        echo "✅ NumPy version OK"
    else
        echo "⚠️  NumPy 2.x detected, downgrading to <2.0.0 for ChromaDB compatibility..."
        $PIP_CMD uninstall -y numpy 2>/dev/null || true
        $PIP_CMD install "numpy>=1.22.0,<2.0.0" || exit 1
    fi
    $PIP_CMD install aiosqlite "numpy>=1.22.0,<2.0.0" sympy || exit 1
    # Verify numpy version is correct
    python -c "import numpy; assert numpy.__version__.startswith('1.'), f'ERROR: NumPy {numpy.__version__} installed, but ChromaDB requires <2.0.0'" || {
        echo "ERROR: Failed to fix NumPy version. Please run manually:"
        echo "  pip install 'numpy>=1.22.0,<2.0.0' --force-reinstall"
        exit 1
    }
    echo "✅ NumPy version verified: $(python -c 'import numpy; print(numpy.__version__)')"
    
    echo "[3/5] Installing ML/AI dependencies..."
    $PIP_CMD install sentence-transformers chromadb || exit 1
    
    echo "[4/5] Installing LLM dependencies..."
    echo "Installing to gateway venv: $CORE_VENV"
    echo "Using Python: $(which python)"
    # Check for CUDA and install llama-cpp-python with CUDA support if available
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        echo "CUDA detected! Installing llama-cpp-python with CUDA support in gateway venv..."
        # Uninstall any existing CPU-only version
        $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
        
        # Check Python version
        PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        echo "Python version: $PYTHON_VERSION"
        
        # First, try to install using ONLY prebuilt wheels (no building)
        echo "Checking for prebuilt wheel (no build required)..."
        if $PIP_CMD install llama-cpp-python[server] --only-binary :all: --no-cache-dir 2>/dev/null; then
            echo "✅ Prebuilt wheel found and installed! No build needed."
            # Check if CUDA support is available
            echo "Checking CUDA support in prebuilt wheel..."
            CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
            if [ "$CUDA_AVAILABLE" != "True" ]; then
                echo "⚠️  Prebuilt wheel doesn't have CUDA support, need to build from source..."
                $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
                # Fall through to build section below
            else
                echo "✅ Prebuilt wheel has CUDA support! Installation complete."
            fi
        else
            echo "⚠️  No prebuilt wheel available for Python $PYTHON_VERSION"
            if [ "$PYTHON_VERSION" != "3.12" ]; then
                echo "   Python $PYTHON_VERSION detected - prebuilt wheels may not be available"
                echo "   Python 3.12 is recommended for best prebuilt wheel support"
            fi
            CUDA_AVAILABLE="False"  # Force build
        fi
        
        # Step 2: If no prebuilt wheel, try installing from pip cache (previously built wheel)
        if [ "$CUDA_AVAILABLE" != "True" ]; then
            echo "Checking pip cache for previously built wheel..."
            # Try installing normally (will use cache if available, or build if not)
            # NOTE: Not using --no-cache-dir so we can use cached wheels!
            if $PIP_CMD install llama-cpp-python[server] 2>/dev/null; then
                echo "✅ Installed from cache or using cached wheel!"
                # Check if CUDA support is available
                CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
                if [ "$CUDA_AVAILABLE" = "True" ]; then
                    echo "✅ Cached wheel has CUDA support! No rebuild needed."
                else
                    echo "⚠️  Cached wheel doesn't have CUDA support, clearing cache and rebuilding..."
                    $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
                    # Clear the cached wheel so we don't reuse the CPU-only version
                    $PIP_CMD cache purge llama-cpp-python 2>/dev/null || true
                    echo "🗑️  Cleared CPU-only wheel from cache"
                fi
            else
                echo "⚠️  No cached wheel found, will build from source..."
            fi
        fi
        
        # Step 3: Build from source if needed (and cache the result for next time)
        if [ "$CUDA_AVAILABLE" != "True" ]; then
            echo "Building llama-cpp-python from source with CUDA support..."
            # Detect number of CPU cores for parallel build
            if command -v nproc &> /dev/null; then
                CORES=$(nproc)
            elif [ -f /proc/cpuinfo ]; then
                CORES=$(grep -c processor /proc/cpuinfo)
            else
                CORES=4  # Fallback to 4 cores
            fi
            echo "⚡ Using $CORES CPU cores for parallel build..."
            echo "💾 Wheel will be cached for future installations (no rebuild needed next time)..."
            
            $PIP_CMD uninstall -y llama-cpp-python 2>/dev/null || true
            # Clear any cached wheels to force a fresh CUDA build
            echo "🗑️  Clearing cached wheels to force fresh CUDA build..."
            $PIP_CMD cache purge llama-cpp-python 2>/dev/null || true
            # Also try to clear the entire cache if the specific package purge didn't work
            $PIP_CMD cache purge 2>/dev/null || true
            
            # Set CMAKE_ARGS with CUDA and parallel build
            export CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_BUILD_PARALLEL_LEVEL=$CORES"
            export FORCE_CMAKE=1
            export CMAKE_BUILD_PARALLEL_LEVEL=$CORES
            # Use regular pip for CUDA source builds (uv pip may not properly pass CMAKE_ARGS)
            # Use --no-binary to force building from source (ignore any cached wheels)
            # The built wheel will be automatically cached by pip for next time
            echo "🔧 Building with regular pip to ensure CMAKE_ARGS are respected..."
            python -m pip install llama-cpp-python[server] --no-binary llama-cpp-python --force-reinstall || {
                echo "⚠️  CUDA build failed, trying CPU-only version..."
                unset CMAKE_ARGS
                unset FORCE_CMAKE
                unset CMAKE_BUILD_PARALLEL_LEVEL
                python -m pip install llama-cpp-python[server] || exit 1
            }
            # Verify the CUDA wheel was built and installed correctly
            CUDA_AVAILABLE=$(python -c 'from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())' 2>/dev/null || echo "False")
            if [ "$CUDA_AVAILABLE" = "True" ]; then
                echo "✅ CUDA wheel built successfully! Wheel is cached for future installations."
            else
                echo "⚠️  Warning: CUDA support not detected after build"
            fi
            unset CMAKE_ARGS
            unset FORCE_CMAKE
            unset CMAKE_BUILD_PARALLEL_LEVEL
            unset CMAKE_ARGS
            unset FORCE_CMAKE
            unset CMAKE_BUILD_PARALLEL_LEVEL
        fi
        
        # Verify CUDA support
        echo "Verifying CUDA support in llama-cpp-python (in gateway venv)..."
        python -c 'from llama_cpp import llama_supports_gpu_offload; print("GPU offload supported:", llama_supports_gpu_offload())' 2>/dev/null || {
            echo "⚠️  CUDA support verification failed, but installation may still work"
        }
    else
        echo "CUDA not detected, installing CPU-only llama-cpp-python in gateway venv..."
        $PIP_CMD install llama-cpp-python[server] || exit 1
    fi
    $PIP_CMD install openai gguf Pillow || exit 1
    
    echo "[5/5] Installing STT/TTS and utilities..."
    $PIP_CMD install faster-whisper piper-tts soundfile jsonschema huggingface_hub psutil nvidia-ml-py cryptography pyttsx3 || exit 1
    # Install kokoro-onnx with --no-deps to prevent numpy upgrade (kokoro-onnx requires numpy>=2.0.2, but may work with 1.x)
    echo "Installing kokoro-onnx (bypassing numpy requirement to keep compatibility with ChromaDB)..."
    $PIP_CMD install kokoro-onnx --no-deps || exit 1
    # Install kokoro-onnx dependencies (excluding numpy)
    $PIP_CMD install colorlog espeakng-loader phonemizer-fork || exit 1
    # Re-verify and re-pin numpy to <2.0.0 after all installs
    echo "Final NumPy version check and pin..."
    python -c "import numpy; version = numpy.__version__; exit(0 if version.startswith('1.') else 1)" 2>/dev/null || {
        echo "⚠️  NumPy was upgraded, re-pinning to <2.0.0..."
        $PIP_CMD install "numpy>=1.22.0,<2.0.0" --force-reinstall --no-deps || exit 1
    }
    # Final verification
    python -c "import numpy; assert numpy.__version__.startswith('1.'), f'ERROR: NumPy {numpy.__version__} installed, but ChromaDB requires <2.0.0'" || {
        echo "ERROR: Failed to maintain NumPy <2.0.0. ChromaDB will not work!"
        exit 1
    }
    echo "✅ NumPy version verified: $(python -c 'import numpy; print(numpy.__version__)')"
    
    INSTALL_SUCCESS=$?
fi

if [ $INSTALL_SUCCESS -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install dependencies"
    echo ""
    echo "Troubleshooting tips:"
    echo "  1. Install 'uv' for better dependency resolution:"
    echo "     curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  2. Clear pip cache: python -m pip cache purge"
    echo "  3. Try installing packages individually from requirements.txt"
    exit 1
fi

echo "Dependencies installed successfully."
echo ""

echo "=========================================="
echo "Installation complete!"
echo "=========================================="
echo ""

# Final verification of CUDA support in gateway venv
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "Verifying CUDA installation in gateway venv..."
    echo "Using Python: $(which python)"
    # Check PyTorch CUDA
    python -c 'import torch; print("PyTorch CUDA available:", torch.cuda.is_available()); count = torch.cuda.device_count() if torch.cuda.is_available() else 0; print("PyTorch CUDA device count:", count)' 2>/dev/null || echo "⚠️  Could not verify PyTorch CUDA"
    # Check llama-cpp-python CUDA
    python -c 'from llama_cpp import llama_supports_gpu_offload; print("llama-cpp-python GPU offload:", llama_supports_gpu_offload())' 2>/dev/null || echo "⚠️  Could not verify llama-cpp-python CUDA (may be CPU-only)"
    echo ""
fi

echo "The Gateway service is now ready to run."
echo ""

