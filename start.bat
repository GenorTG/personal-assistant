@echo off
REM Personal Assistant - Windows Launch Script

setlocal
cd /d "%~dp0"

cd electron-app

REM Check if dependencies are installed
if not exist "node_modules" (
    echo Electron dependencies not found. Running installation...
    cd ..
    call install.bat
    cd electron-app
)

REM Check if frontend is built
if not exist "..\services\frontend\.next" (
    echo Frontend not built. Building now...
    cd ..\services\frontend
    if not exist "node_modules" (
        call npm install --silent
    )
    call npm run build --silent
    cd ..\..\electron-app
)

REM Start the app
echo Launching Personal Assistant...
call npm start
