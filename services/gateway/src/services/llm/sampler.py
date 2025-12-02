"""Sampler settings for LLM generation with llama-cpp-python server.

These settings control text generation behavior and match the parameters
accepted by the llama-cpp-python server's OpenAI-compatible API.

See: https://llama-cpp-python.readthedocs.io/en/latest/api-reference/
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from .sampler_blocks import (
    RepetitionPenaltyBlock,
    DRYRepetitionPenaltyBlock,
    XTCBlock,
    MirostatBlock,
    BasicSamplingBlock,
    build_sampler_params
)


@dataclass
class SamplerSettings:
    """Complete sampler configuration for llama-cpp-python server.
    
    These parameters control text generation and are passed to the
    /v1/chat/completions or /v1/completions endpoints.
    """
    
    # Basic sampling parameters
    temperature: float = 0.7
    """Sampling temperature (0.0-2.0). Higher = more random, lower = more deterministic."""
    
    top_p: float = 0.9
    """Nucleus sampling: only consider tokens with cumulative probability > top_p (0.0-1.0)."""
    
    top_k: int = 40
    """Top-k sampling: only consider the top k tokens (0 = disabled)."""
    
    min_p: float = 0.0
    """Minimum probability threshold (0.0-1.0). Tokens below this are filtered out."""
    
    # Repetition control
    repeat_penalty: float = 1.1
    """Repetition penalty (1.0 = disabled, >1.0 = penalize repetition)."""
    
    presence_penalty: float = 0.0
    """OpenAI-style presence penalty (-2.0 to 2.0). Penalizes tokens that appear at all."""
    
    frequency_penalty: float = 0.0
    """OpenAI-style frequency penalty (-2.0 to 2.0). Penalizes tokens based on frequency."""
    
    repeat_last_n: int = 64
    """How many tokens back to look for repetition (0 = disabled, -1 = context size)."""
    
    # Advanced sampling methods
    typical_p: float = 1.0
    """Typical sampling probability (1.0 = disabled). Lower values = more typical text."""
    
    tfs_z: float = 1.0
    """Tail-free sampling z-value (1.0 = disabled). Lower values = remove unlikely tokens."""
    
    # Mirostat - entropy-based sampling
    mirostat_mode: int = 0
    """Mirostat mode: 0 = disabled, 1 = Mirostat, 2 = Mirostat 2.0."""
    
    mirostat_tau: float = 5.0
    """Mirostat target entropy (perplexity). Higher = more random."""
    
    mirostat_eta: float = 0.1
    """Mirostat learning rate. How quickly it adapts."""
    
    # Output control
    max_tokens: int = 512
    """Maximum number of tokens to generate (-1 = unlimited)."""
    
    stop: Optional[List[str]] = None
    """Stop sequences - generation stops when any of these are encountered."""
    
    # Reproducibility
    seed: int = -1
    """Random seed for reproducibility (-1 = random)."""
    
    # Streaming
    stream: bool = False
    """Whether to stream the response token by token."""
    
    # Grammar (for structured output)
    grammar: Optional[str] = None
    """GBNF grammar string for structured output (JSON, etc.)."""
    
    # Advanced parameters
    logit_bias: Optional[Dict[int, float]] = None
    """Bias specific token IDs (positive = more likely, negative = less likely)."""
    
    penalty_range: Optional[int] = None
    """Range of tokens to apply repetition penalty to."""
    
    penalty_alpha: Optional[float] = None
    """Contrastive search penalty alpha."""
    
    # DRY (Dynamic Repetition Penalty) - sequence-based repetition control
    dry_multiplier: float = 0.0
    """DRY multiplier: overall strength of penalty (0.0 = disabled). Higher = more aggressive."""
    
    dry_base: float = 1.0
    """DRY base: adjusts penalty based on sequence length. Higher = steeper penalty for longer sequences."""
    
    dry_allowed_length: int = 0
    """DRY allowed length: minimum sequence length to penalize. Shorter sequences are exempt."""
    
    n_probs: Optional[int] = None
    """Return top N token probabilities (for debugging)."""
    
    def __post_init__(self):
        """Initialize default stop sequences if not provided."""
        if self.stop is None:
            self.stop = []
    
    def to_api_params(self) -> Dict[str, Any]:
        """Convert to parameters for the llama-cpp-python API.
        
        Uses DRY blocks to avoid repetition. Only includes non-default values
        to keep requests clean.
        """
        # Build parameter blocks
        basic = BasicSamplingBlock(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            min_p=self.min_p
        )
        
        repetition = RepetitionPenaltyBlock(
            repeat_penalty=self.repeat_penalty,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            repeat_last_n=self.repeat_last_n,
            penalty_range=self.penalty_range
        )
        
        # DRY (Dynamic Repetition Penalty) - sequence-based repetition control
        dry = DRYRepetitionPenaltyBlock(
            dry_multiplier=self.dry_multiplier,
            dry_base=self.dry_base,
            dry_allowed_length=self.dry_allowed_length
        )
        
        xtc = XTCBlock(
            typical_p=self.typical_p,
            tfs_z=self.tfs_z
        )
        
        mirostat = MirostatBlock(
            mirostat_mode=self.mirostat_mode,
            mirostat_tau=self.mirostat_tau,
            mirostat_eta=self.mirostat_eta
        )
        
        # Build params using DRY blocks
        params = build_sampler_params(
            basic=basic,
            repetition=repetition,
            dry=dry,
            xtc=xtc,
            mirostat=mirostat,
            include_defaults=False
        )
        
        # Add non-block parameters
        params["max_tokens"] = self.max_tokens
        params["stream"] = self.stream
        
        # Stop sequences
        if self.stop:
            params["stop"] = self.stop
            
        # Seed
        if self.seed != -1:
            params["seed"] = self.seed
            
        # Grammar
        if self.grammar:
            params["grammar"] = self.grammar
            
        # Advanced parameters
        if self.logit_bias:
            params["logit_bias"] = self.logit_bias
        if self.penalty_alpha is not None:
            params["penalty_alpha"] = self.penalty_alpha
        if self.n_probs is not None:
            params["n_probs"] = self.n_probs
            
        return params
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        result = asdict(self)
        # Ensure stop is a list, not None
        if result["stop"] is None:
            result["stop"] = []
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SamplerSettings":
        """Create from dictionary, ignoring unknown fields."""
        valid_fields = {
            "temperature", "top_p", "top_k", "min_p",
            "repeat_penalty", "presence_penalty", "frequency_penalty", "repeat_last_n",
            "dry_multiplier", "dry_base", "dry_allowed_length",  # DRY repetition penalty
            "typical_p", "tfs_z",
            "mirostat_mode", "mirostat_tau", "mirostat_eta",
            "max_tokens", "stop", "seed", "stream", "grammar",
            "logit_bias", "penalty_range", "penalty_alpha", "n_probs"
        }
        filtered = {k: v for k, v in data.items() if k in valid_fields and v is not None}
        return cls(**filtered)


# Default presets for different use cases
SAMPLER_PRESETS = {
    "default": SamplerSettings(),
    
    "creative": SamplerSettings(
        temperature=1.0,
        top_p=0.95,
        top_k=100,
        repeat_penalty=1.15,
        typical_p=0.9,
    ),
    
    "precise": SamplerSettings(
        temperature=0.3,
        top_p=0.8,
        top_k=20,
        repeat_penalty=1.05,
    ),
    
    "chat": SamplerSettings(
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        repeat_penalty=1.1,
        presence_penalty=0.1,
    ),
    
    "deterministic": SamplerSettings(
        temperature=0.0,
        top_p=1.0,
        top_k=1,
        repeat_penalty=1.0,
    ),
    
    "mirostat": SamplerSettings(
        temperature=0.8,
        mirostat_mode=2,
        mirostat_tau=5.0,
        mirostat_eta=0.1,
    ),
}
