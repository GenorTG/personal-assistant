"""Sampler settings for LLM generation."""
from dataclasses import dataclass


@dataclass
class SamplerSettings:
    """Sampler configuration for LLM generation."""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    max_tokens: int = 512
