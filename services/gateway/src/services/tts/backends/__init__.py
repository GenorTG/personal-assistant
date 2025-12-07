"""TTS backend implementations."""
from .base import TTSBackend
from .chatterbox import ChatterboxBackend
from .kokoro import KokoroBackend
from .coqui import CoquiBackend
from .pyttsx3_backend import Pyttsx3Backend
from .piper import PiperBackend

__all__ = [
    'TTSBackend',
    'ChatterboxBackend',
    'KokoroBackend',
    'CoquiBackend',
    'Pyttsx3Backend',
    'PiperBackend'
]


