# Kokoro TTS Service

## Overview
Kokoro TTS is implemented as a separate microservice to resolve dependency conflicts between NumPy 2.x (required by Kokoro) and ChromaDB (requires NumPy 1.x).

## Architecture
- **Port**: 8880
- **Communication**: HTTP API
- **Environment**: Dedicated virtual environment (`kokoro-tts-service/.venv`)
- **Model**: Kokoro v1.0 ONNX (82M parameters)

## Management
The service can be managed via:
1. **Web UI**: Settings -> Service Status panel
2. **Launcher**: "Kokoro TTS" service card
3. **Scripts**: `start.bat` in `kokoro-tts-service` folder

## API Endpoints
- `GET /health`: Check service status
- `GET /voices`: List available voices
- `POST /synthesize`: Generate audio

## Troubleshooting
If the service fails to start:
1. Check logs in `kokoro-tts-service` directory (if any)
2. Ensure port 8880 is free
3. Run `install.bat` to reinstall dependencies
4. Run `download_models.py` to ensure model files exist
