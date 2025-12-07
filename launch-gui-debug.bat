@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "LAUNCHER_DIR=%PROJECT_ROOT%launcher"
set "VENV_DIR=%PROJECT_ROOT%.launcher_venv"
set "REQUIREMENTS=%LAUNCHER_DIR%\requirements.txt"
set "PYTHON_EXE=python"

echo ========================================
echo Personal Assistant Launcher (Debug Mode)
echo ========================================
echo.

:: Check if Python is installed
echo [1/5] Checking Python installation...
where %PYTHON_EXE% >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Python version
echo [2/5] Checking Python version...
for /f "tokens=2" %%i in ('%PYTHON_EXE% --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python version: %PYTHON_VERSION%

:: Check if venv exists and is valid
echo [3/5] Checking virtual environment...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating...
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
    
    echo [4/5] Installing launcher dependencies...
    "%VENV_DIR%\Scripts\pip" install -r "%REQUIREMENTS%"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        echo Check the error messages above for details.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Virtual environment found
    echo [4/5] Checking dependencies...
    "%VENV_DIR%\Scripts\pip" show customtkinter >nul 2>nul
    if %errorlevel% neq 0 (
        echo [INFO] Installing missing dependencies...
        "%VENV_DIR%\Scripts\pip" install -r "%REQUIREMENTS%"
        if %errorlevel% neq 0 (
            echo [ERROR] Failed to install dependencies.
            pause
            exit /b 1
        )
    )
    echo [OK] Dependencies OK
)

:: Check for error logs
echo [5/6] Checking for previous errors...
if exist "%LAUNCHER_DIR%\launcher_error.log" (
    echo [WARNING] Previous error log found. Contents:
    echo ----------------------------------------
    type "%LAUNCHER_DIR%\launcher_error.log"
    echo ----------------------------------------
    echo.
    echo This may be from an old version. Delete it? (Y/N)
    choice /C YN /N /M "Press Y to delete, N to keep: "
    if errorlevel 2 goto :keep_error_log
    if errorlevel 1 (
        del "%LAUNCHER_DIR%\launcher_error.log"
        echo [OK] Old error log deleted.
    )
    :keep_error_log
    echo.
)
if exist "%LAUNCHER_DIR%\launcher_import_error.log" (
    echo [WARNING] Previous import error log found. Contents:
    echo ----------------------------------------
    type "%LAUNCHER_DIR%\launcher_import_error.log"
    echo ----------------------------------------
    echo.
    echo This may be from an old version. Delete it? (Y/N)
    choice /C YN /N /M "Press Y to delete, N to keep: "
    if errorlevel 2 goto :keep_import_log
    if errorlevel 1 (
        del "%LAUNCHER_DIR%\launcher_import_error.log"
        echo [OK] Old import error log deleted.
    )
    :keep_import_log
    echo.
)

:: Test imports
echo [6/6] Testing launcher imports...
"%VENV_DIR%\Scripts\python.exe" "%LAUNCHER_DIR%\test_imports.py"
if %errorlevel% neq 0 (
    echo [ERROR] Import test failed! Check errors above.
    pause
    exit /b 1
)
echo [OK] All imports successful

:: Run the launcher with visible console (for debugging)
echo.
echo ========================================
echo Starting launcher...
echo ========================================
echo.
echo If the launcher window doesn't appear, check for errors above.
echo This window will stay open to show any errors.
echo.

"%VENV_DIR%\Scripts\python.exe" "%LAUNCHER_DIR%\launcher.py"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher exited with error code: %errorlevel%
    echo.
    if exist "%LAUNCHER_DIR%\launcher_error.log" (
        echo Error log contents:
        echo ----------------------------------------
        type "%LAUNCHER_DIR%\launcher_error.log"
        echo ----------------------------------------
    )
    pause
    exit /b %errorlevel%
)

echo.
echo Launcher closed normally.
pause

