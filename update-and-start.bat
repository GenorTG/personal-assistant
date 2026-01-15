@echo off
REM Personal Assistant - Windows Update and Launch Script

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Keep window open
if "%1"=="" (
    start "Personal Assistant - Update and Start" cmd /k "%~f0" keepopen
    exit /b
)

echo ==========================================
echo Personal Assistant - Update ^& Launch
echo ==========================================
echo.

REM Update from git (if git repository)
if exist ".git" (
    echo [1/6] Updating from git repository...
    git pull
    if %ERRORLEVEL% EQU 0 (
        echo Repository updated
    ) else (
        echo Warning: git pull failed. Continuing with installation...
    )
) else (
    echo [1/6] Skipping git update (not a git repository)
)

REM Check prerequisites
echo.
echo [2/6] Checking prerequisites...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found
    pause
    exit /b 1
)
python --version

node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Node.js not found
    pause
    exit /b 1
)
node --version

npm --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: npm not found
    pause
    exit /b 1
)
npm --version

REM Setup/Update Python virtual environment
echo.
echo [3/6] Setting up Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo Virtual environment created
) else (
    echo Virtual environment exists
)

call .venv\Scripts\activate.bat
echo Activated virtual environment

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

REM Reinstall Python dependencies
echo.
echo [4/6] Reinstalling Python dependencies...
echo This may take several minutes...

if exist "requirements.txt" (
    echo Installing main requirements...
    python -m pip install -r requirements.txt --upgrade
    echo Main requirements updated
)

if exist "services\gateway\requirements.txt" (
    echo Installing gateway requirements...
    python -m pip install -r services\gateway\requirements.txt --upgrade
    echo Gateway requirements updated
)

REM Reinstall frontend dependencies
echo.
echo [5/6] Reinstalling and rebuilding frontend...
cd services\frontend
echo Removing old node_modules and build...
if exist "node_modules" rmdir /s /q node_modules
if exist ".next" rmdir /s /q .next
echo Installing frontend dependencies (this may take a while)...
call npm install
echo Frontend dependencies reinstalled
echo Building frontend (this may take a while)...
call npm run build
echo Frontend rebuilt
cd ..\..

REM Reinstall Electron dependencies
echo.
echo [6/6] Reinstalling Electron dependencies...
cd electron-app
echo Removing old node_modules...
if exist "node_modules" rmdir /s /q node_modules
echo Installing Electron dependencies...
call npm install
echo Electron dependencies reinstalled
cd ..

echo.
echo ==========================================
echo Update complete! Launching application...
echo ==========================================
echo.

REM Launch the application
cd electron-app
call npm start
