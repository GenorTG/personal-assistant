"""Model catalog with hardcoded information about available models."""
from typing import List, Dict, Any

# Whisper model sizes and information
WHISPER_MODELS = [
    {
        "id": "tiny",
        "name": "Whisper Tiny",
        "size_mb": 39,
        "memory_mb": 150,
        "description": "Fastest, lowest accuracy. Good for real-time transcription.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-tiny",
            "manual_command": None
        }
    },
    {
        "id": "base",
        "name": "Whisper Base",
        "size_mb": 74,
        "memory_mb": 250,
        "description": "Good balance of speed and accuracy. Recommended for most use cases.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-base",
            "manual_command": None
        }
    },
    {
        "id": "small",
        "name": "Whisper Small",
        "size_mb": 244,
        "memory_mb": 500,
        "description": "Better accuracy, moderate speed. Good for high-quality transcription.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-small",
            "manual_command": None
        }
    },
    {
        "id": "medium",
        "name": "Whisper Medium",
        "size_mb": 769,
        "memory_mb": 1200,
        "description": "High accuracy, slower speed. Best for offline transcription.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-medium",
            "manual_command": None
        }
    },
    {
        "id": "large",
        "name": "Whisper Large",
        "size_mb": 1550,
        "memory_mb": 2500,
        "description": "Highest accuracy, slowest speed. Requires significant memory.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-large",
            "manual_command": None
        }
    },
    {
        "id": "large-v2",
        "name": "Whisper Large v2",
        "size_mb": 1550,
        "memory_mb": 2500,
        "description": "Improved version of Large model with better accuracy.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-large-v2",
            "manual_command": None
        }
    },
    {
        "id": "large-v3",
        "name": "Whisper Large v3",
        "size_mb": 1550,
        "memory_mb": 2500,
        "description": "Latest version of Large model with best accuracy.",
        "download_info": {
            "method": "auto",
            "description": "Automatically downloaded by faster-whisper on first use",
            "cache_location": "~/.cache/huggingface/hub/models--guillaumekln--faster-whisper-large-v3",
            "manual_command": None
        }
    }
]

# Popular Piper voices
PIPER_VOICES = [
    {
        "id": "en_US-amy-medium",
        "name": "Amy (US English, Medium)",
        "size_mb": 15,
        "memory_mb": 50,
        "description": "Clear, professional female voice",
        "download_info": {
            "method": "manual",
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
            "wget_command": "wget -O en_US-amy-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
            "curl_command": "curl -L -o en_US-amy-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx"
        }
    },
    {
        "id": "en_US-lessac-medium",
        "name": "Lessac (US English, Medium)",
        "size_mb": 15,
        "memory_mb": 50,
        "description": "Natural, expressive male voice",
        "download_info": {
            "method": "manual",
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
            "wget_command": "wget -O en_US-lessac-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "curl_command": "curl -L -o en_US-lessac-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
        }
    },
    {
        "id": "en_GB-alba-medium",
        "name": "Alba (British English, Medium)",
        "size_mb": 15,
        "memory_mb": 50,
        "description": "British English female voice",
        "download_info": {
            "method": "manual",
            "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
            "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json",
            "wget_command": "wget -O en_GB-alba-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alba/medium/en_GB-alba-medium.onnx",
            "curl_command": "curl -L -o en_GB-alba-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alba/medium/en_GB-alba-medium.onnx"
        }
    }
]

# Kokoro model information
KOKORO_MODEL = {
    "id": "kokoro-v1.0",
    "name": "Kokoro TTS v1.0",
    "size_mb": 150,
    "memory_mb": 300,
    "description": "High-quality multilingual TTS model",
    "files": [
        {
            "name": "kokoro-v1.0.onnx",
            "size_mb": 100,
            "url": "https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/kokoro-v1.0.onnx",
            "wget_command": "wget -O kokoro-v1.0.onnx https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/kokoro-v1.0.onnx",
            "curl_command": "curl -L -o kokoro-v1.0.onnx https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/kokoro-v1.0.onnx"
        },
        {
            "name": "voices-v1.0.bin",
            "size_mb": 50,
            "url": "https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/voices-v1.0.bin",
            "wget_command": "wget -O voices-v1.0.bin https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/voices-v1.0.bin",
            "curl_command": "curl -L -o voices-v1.0.bin https://github.com/hexgrad/kokoro-82M/releases/download/v1.0/voices-v1.0.bin"
        }
    ],
    "download_info": {
        "method": "manual",
        "description": "Download both model files to the models directory",
        "instructions": "Download kokoro-v1.0.onnx and voices-v1.0.bin to your models directory"
    }
}


def get_whisper_models() -> List[Dict[str, Any]]:
    """Get list of available Whisper models."""
    return WHISPER_MODELS.copy()


def get_piper_voices() -> List[Dict[str, Any]]:
    """Get list of available Piper voices."""
    return PIPER_VOICES.copy()


def get_kokoro_model() -> Dict[str, Any]:
    """Get Kokoro model information."""
    return KOKORO_MODEL.copy()

