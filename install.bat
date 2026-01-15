@echo off
REM Personal Assistant - Windows Installation Script

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Keep window open
if "%1"=="" (
    start "Personal Assistant - Installation" cmd /k "%~f0" keepopen
    exit /b
)

echo ==========================================
echo Personal Assistant - Installation
echo ==========================================
echo.

REM Check prerequisites
echo [1/6] Checking prerequisites...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found. Please install Python 3.8+ first.
    pause
    exit /b 1
)
python --version

node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Node.js not found. Please install Node.js first.
    pause
    exit /b 1
)
node --version

npm --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: npm not found. Please install Node.js first.
    pause
    exit /b 1
)
npm --version

REM Setup Python virtual environment
echo.
echo [2/6] Setting up Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo Virtual environment created
) else (
    echo Virtual environment already exists
)

call .venv\Scripts\activate.bat
echo Activated virtual environment

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

REM Install Python dependencies
echo.
echo [3/6] Installing Python dependencies...
echo This may take several minutes...

if exist "requirements.txt" (
    echo Installing main requirements...
    python -m pip install -r requirements.txt
    echo Main requirements installed
)

if exist "services\gateway\requirements.txt" (
    echo Installing gateway requirements...
    python -m pip install -r services\gateway\requirements.txt
    echo Gateway requirements installed
)

REM Install frontend dependencies
echo.
echo [4/6] Installing frontend dependencies...
cd services\frontend
if not exist "node_modules" (
    echo Installing frontend dependencies (this may take a while)...
    call npm install
    echo Frontend dependencies installed
) else (
    echo Frontend dependencies already installed
)
cd ..\..

REM Build frontend
echo.
echo [5/6] Building frontend...
cd services\frontend
echo Building frontend (this may take a while)...
call npm run build
echo Frontend built successfully
cd ..\..

REM Install Electron dependencies
echo.
echo [6/6] Installing Electron dependencies...
cd electron-app
if not exist "node_modules" (
    echo Installing Electron dependencies...
    call npm install
    echo Electron dependencies installed
) else (
    echo Electron dependencies already installed
)
cd ..

echo.
echo ==========================================
echo Installation complete!
echo ==========================================
echo.
echo You can now:
echo   - Run 'start.bat' to start the application
echo   - Run 'update-and-start.bat' to update and launch
echo.
pause
