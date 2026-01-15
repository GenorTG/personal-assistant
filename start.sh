#!/bin/bash
# Personal Assistant - Launch Script
# This script simply launches the Electron application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/electron-app"

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "⚠ Electron dependencies not found. Running installation..."
    cd "$SCRIPT_DIR"
    ./install.sh
    cd "$SCRIPT_DIR/electron-app"
fi

# Check if frontend is built
if [ ! -d "../services/frontend/.next" ]; then
    echo "⚠ Frontend not built. Building now..."
    cd "$SCRIPT_DIR/services/frontend"
    if [ ! -d "node_modules" ]; then
        npm install --silent
    fi
    npm run build --silent
    cd "$SCRIPT_DIR/electron-app"
fi

# Start the app
echo "Launching Personal Assistant..."
npm start
