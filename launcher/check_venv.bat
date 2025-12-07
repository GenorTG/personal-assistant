@echo off
:: Quick script to check if launcher venv has customtkinter installed

set "PROJECT_ROOT=%~dp0.."
set "VENV_DIR=%PROJECT_ROOT%\.launcher_venv"

echo Checking launcher venv...
echo Venv directory: %VENV_DIR%

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [ERROR] Launcher venv does not exist!
    echo Please run launch-gui.bat to create it.
    pause
    exit /b 1
)

echo.
echo Testing customtkinter import...
"%VENV_DIR%\Scripts\python.exe" -c "import customtkinter; print('✓ customtkinter is installed')" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] customtkinter is NOT installed in the venv!
    echo Installing customtkinter...
    "%VENV_DIR%\Scripts\pip.exe" install customtkinter
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install customtkinter
        pause
        exit /b 1
    )
    echo [SUCCESS] customtkinter installed!
) else (
    echo [SUCCESS] customtkinter is installed!
)

echo.
echo Testing launcher imports...
"%VENV_DIR%\Scripts\python.exe" "%PROJECT_ROOT%\launcher\test_imports.py" 2>&1

pause

