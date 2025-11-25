# Personal AI Assistant (Microservices)

A modular, privacy-focused AI assistant featuring local LLM inference, Speech-to-Text, and Text-to-Speech capabilities. Refactored into a microservices architecture for stability and scalability.

## 🏗️ Architecture

The system consists of **6 independent services**:

| Service | Port | Role | Tech Stack |
|---------|------|------|------------|
| **Gateway** | `8000` | **App Server & Router**. Handles DB, Chat Logic, and routes requests. | FastAPI, SQLite |
| **LLM Service** | `8001` | **Text Generation**. Runs `llama-cpp-python` server. | Python, Llama.cpp |
| **Audio Client** | `8002` | **Audio Client**. Listens to Mic, detects Wake Word, plays Audio. | PyAudio, Porcupine |
| **Whisper Service** | `8003` | **Speech-to-Text**. Faster-Whisper. | Faster-Whisper |
| **Piper Service** | `8004` | **Lightweight TTS**. Piper TTS. | Piper |
| **Chatterbox Service** | `4123` | **Advanced TTS**. Resemble AI's Chatterbox TTS API. | PyTorch, FastAPI |
| **Kokoro Service** | `8880` | **High-Quality TTS**. Kokoro ONNX implementation. | Kokoro-ONNX |

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- CUDA Toolkit (optional, for GPU acceleration)
- Visual Studio Build Tools (for compiling some dependencies)

### Installation & Running

1.  **Run the Launcher**:
    Double-click `launch-gui.bat` or run:
    ```bash
    python launcher.py
    ```

2.  **Install Services**:
    In the launcher, click **"Install All"**. This will create isolated virtual environments for each service and install dependencies.

3.  **Start Services**:
    Click **"Start All"**. The launcher will start all services in the correct order.

## 📁 Directory Structure

- `gateway/`: Main API Gateway and application logic.
- `llm-service/`: LLM inference service.
- `audio-client/`: Microphone and Speaker handler.
- `whisper-service/`: Whisper STT service.
- `piper-service/`: Piper TTS service.
- `chatterbox-service/`: Chatterbox TTS API.
- `kokoro-service/`: Kokoro TTS service.
- `frontend-next/`: Next.js Frontend.
- `data/`: Shared data directory (models, memory, vector store).
