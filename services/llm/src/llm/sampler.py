"""Sampler settings for LLM generation."""
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class SamplerSettings:
    """Sampler configuration for LLM generation."""
    # Basic sampling
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    max_tokens: int = 512
    
    # DRY (Dynamic Repetition Penalty)
    dry_alpha: Optional[float] = None  # Repetition penalty strength
    dry_eta: Optional[float] = None  # Decay factor
    dry_min_penalty: Optional[float] = None  # Minimum penalty
    
    # XTC (Extended Temperature Control)
    xtc_enabled: bool = False
    xtc_temperature_min: Optional[float] = None
    xtc_temperature_max: Optional[float] = None
    xtc_adaptation_rate: Optional[float] = None
    
    # Dynamic Temperature
    dynamic_temp_enabled: bool = False
    dynamic_temp_schedule: Optional[str] = None  # "linear", "exponential", "cosine"
    dynamic_temp_range: Optional[List[float]] = None  # [min, max]
    
    # Repetition Penalty Block
    rep_penalty_range: Optional[int] = None  # Token range to apply penalty
    rep_penalty_slope: Optional[float] = None
    rep_penalty_alpha: Optional[float] = None
