@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "LAUNCHER_DIR=%PROJECT_ROOT%launcher"
set "VENV_DIR=%PROJECT_ROOT%.launcher_venv"
set "REQUIREMENTS=%LAUNCHER_DIR%\requirements.txt"
set "PYTHON_EXE=python"

:: Check if Python is installed
where %PYTHON_EXE% >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

:: Check if venv exists and is valid
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating launcher environment...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    
    echo [INFO] Installing launcher dependencies...
    "%VENV_DIR%\Scripts\pip" install -r "%REQUIREMENTS%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: Run the launcher using pythonw.exe (no console window)
:: The launcher handles single-instance and error logging internally
:: Use 'start' to launch in background and allow batch file to exit immediately
start "" "%VENV_DIR%\Scripts\pythonw.exe" "%LAUNCHER_DIR%\launcher.py"

exit /b 0
