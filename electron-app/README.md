# Personal Assistant Desktop App

Simple Electron wrapper for the Next.js frontend.

## Usage

1. Start the Next.js frontend: `cd services/frontend && npm run dev`
2. Run the Electron app: `cd electron-app && npm start`

## Build

- Linux: `npm run build:linux`
- Windows: `npm run build:win`
- macOS: `npm run build:mac`

The app simply loads http://localhost:8002 in an Electron window.

