# LLM Service CUDA Installation Script
# This script creates a fresh venv and installs llama-cpp-python with CUDA support

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LLM Service - CUDA Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check CUDA
$nvcc = Get-Command nvcc -ErrorAction SilentlyContinue
if (-not $nvcc) {
    Write-Host "ERROR: CUDA Toolkit not found. Please install CUDA Toolkit first." -ForegroundColor Red
    exit 1
}
$cudaVersion = (nvcc --version | Select-String "release").ToString()
Write-Host "  CUDA: $cudaVersion" -ForegroundColor Green

# Check Python
$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python not found." -ForegroundColor Red
    exit 1
}
Write-Host "  Python: Available" -ForegroundColor Green

# Check CMake  
$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) {
    Write-Host "WARNING: CMake not found. Installing via pip..." -ForegroundColor Yellow
}

# Check Visual Studio Build Tools
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vsWhere) {
    $vsPath = & $vsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($vsPath) {
        Write-Host "  Visual Studio: Found" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Visual Studio Build Tools not found. Build may fail." -ForegroundColor Yellow
    }
}

Write-Host ""

# Remove old venv if exists
$venvPath = Join-Path $PSScriptRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "Removing old virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

# Create new venv with Python 3.10
Write-Host "Creating virtual environment with Python 3.10..." -ForegroundColor Yellow
py -3.10 -m venv $venvPath

# Activate venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
. $activateScript

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip wheel setuptools cmake

# Set CMAKE_ARGS for CUDA build
Write-Host ""
Write-Host "Building llama-cpp-python with CUDA support..." -ForegroundColor Cyan
Write-Host "This may take 10-20 minutes..." -ForegroundColor Yellow
Write-Host ""

$env:CMAKE_ARGS = "-DGGML_CUDA=on"
$env:FORCE_CMAKE = "1"

# Install llama-cpp-python with CUDA
pip install llama-cpp-python[server] --no-cache-dir --force-reinstall

# Install other requirements
Write-Host ""
Write-Host "Installing other dependencies..." -ForegroundColor Yellow
pip install fastapi uvicorn[standard] pydantic httpx aiohttp python-dotenv

# Verify installation
Write-Host ""
Write-Host "Verifying CUDA support..." -ForegroundColor Yellow
$result = python -c "from llama_cpp import llama_supports_gpu_offload; print('GPU offload supported:', llama_supports_gpu_offload())"
Write-Host $result

if ($result -match "True") {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Installation Complete - CUDA Enabled!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  WARNING: CUDA not detected!" -ForegroundColor Red
    Write-Host "  Model will run on CPU only." -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
}

