"""DRY sampler parameter blocks for LLM generation.

This module provides reusable parameter blocks to avoid repetition
when building sampler configurations for different use cases.

Includes:
- DRY (Dynamic Repetition Penalty) sampler for sequence-based repetition control
- XTC (eXponential Typicality Criterion) sampler
- Mirostat entropy-based sampling
- Basic sampling parameters
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RepetitionPenaltyBlock:
    """Repetition penalty parameter block.
    
    Controls how the model handles repetition in generated text.
    """
    repeat_penalty: float = 1.1
    """Repetition penalty (1.0 = disabled, >1.0 = penalize repetition)."""
    
    presence_penalty: float = 0.0
    """OpenAI-style presence penalty (-2.0 to 2.0). Penalizes tokens that appear at all."""
    
    frequency_penalty: float = 0.0
    """OpenAI-style frequency penalty (-2.0 to 2.0). Penalizes tokens based on frequency."""
    
    repeat_last_n: int = 64
    """How many tokens back to look for repetition (0 = disabled, -1 = context size)."""
    
    penalty_range: Optional[int] = None
    """Range of tokens to apply repetition penalty to."""
    
    def to_params(self, include_defaults: bool = False) -> Dict[str, Any]:
        """Convert to API parameters.
        
        Args:
            include_defaults: If True, include all parameters even if default
            
        Returns:
            Dictionary of parameters for API
        """
        params = {}
        
        if include_defaults or self.repeat_penalty != 1.1:
            params["repeat_penalty"] = self.repeat_penalty
        if include_defaults or self.presence_penalty != 0.0:
            params["presence_penalty"] = self.presence_penalty
        if include_defaults or self.frequency_penalty != 0.0:
            params["frequency_penalty"] = self.frequency_penalty
        if include_defaults or self.repeat_last_n != 64:
            params["repeat_last_n"] = self.repeat_last_n
        if self.penalty_range is not None:
            params["penalty_range"] = self.penalty_range
            
        return params
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepetitionPenaltyBlock":
        """Create from dictionary."""
        return cls(
            repeat_penalty=data.get("repeat_penalty", 1.1),
            presence_penalty=data.get("presence_penalty", 0.0),
            frequency_penalty=data.get("frequency_penalty", 0.0),
            repeat_last_n=data.get("repeat_last_n", 64),
            penalty_range=data.get("penalty_range")
        )


@dataclass
class XTCBlock:
    """XTC (eXponential Typicality Criterion) / Typical Sampling block.
    
    Controls typical sampling which filters tokens based on typicality.
    """
    typical_p: float = 1.0
    """Typical sampling probability (1.0 = disabled). Lower values = more typical text."""
    
    tfs_z: float = 1.0
    """Tail-free sampling z-value (1.0 = disabled). Lower values = remove unlikely tokens."""
    
    def to_params(self, include_defaults: bool = False) -> Dict[str, Any]:
        """Convert to API parameters.
        
        Args:
            include_defaults: If True, include all parameters even if default
            
        Returns:
            Dictionary of parameters for API
        """
        params = {}
        
        if include_defaults or self.typical_p != 1.0:
            params["typical_p"] = self.typical_p
        if include_defaults or self.tfs_z != 1.0:
            params["tfs_z"] = self.tfs_z
            
        return params
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "XTCBlock":
        """Create from dictionary."""
        return cls(
            typical_p=data.get("typical_p", 1.0),
            tfs_z=data.get("tfs_z", 1.0)
        )


@dataclass
class MirostatBlock:
    """Mirostat entropy-based sampling block.
    
    Mirostat is an entropy-based sampling method that maintains
    a target entropy (perplexity) during generation.
    """
    mirostat_mode: int = 0
    """Mirostat mode: 0 = disabled, 1 = Mirostat, 2 = Mirostat 2.0."""
    
    mirostat_tau: float = 5.0
    """Mirostat target entropy (perplexity). Higher = more random."""
    
    mirostat_eta: float = 0.1
    """Mirostat learning rate. How quickly it adapts."""
    
    def to_params(self, include_defaults: bool = False) -> Dict[str, Any]:
        """Convert to API parameters.
        
        Args:
            include_defaults: If True, include all parameters even if default
            
        Returns:
            Dictionary of parameters for API
        """
        params = {}
        
        if include_defaults or self.mirostat_mode != 0:
            params["mirostat_mode"] = self.mirostat_mode
            params["mirostat_tau"] = self.mirostat_tau
            params["mirostat_eta"] = self.mirostat_eta
            
        return params
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MirostatBlock":
        """Create from dictionary."""
        return cls(
            mirostat_mode=data.get("mirostat_mode", 0),
            mirostat_tau=data.get("mirostat_tau", 5.0),
            mirostat_eta=data.get("mirostat_eta", 0.1)
        )


@dataclass
class DRYRepetitionPenaltyBlock:
    """DRY (Dynamic Repetition Penalty) sampler block.
    
    DRY repetition penalty provides sequence-based repetition control
    that dynamically adjusts penalties based on sequence patterns.
    """
    dry_multiplier: float = 0.0
    """DRY multiplier for repetition penalty (0.0 = disabled)."""
    
    dry_base: float = 1.0
    """DRY base value for repetition penalty calculation."""
    
    dry_allowed_length: int = 0
    """Allowed sequence length before applying DRY penalty (0 = disabled)."""
    
    def to_params(self, include_defaults: bool = False) -> Dict[str, Any]:
        """Convert to API parameters.
        
        Args:
            include_defaults: If True, include all parameters even if default
            
        Returns:
            Dictionary of parameters for API
        """
        params = {}
        
        if include_defaults or self.dry_multiplier != 0.0:
            params["dry_multiplier"] = self.dry_multiplier
        if include_defaults or self.dry_base != 1.0:
            params["dry_base"] = self.dry_base
        if include_defaults or self.dry_allowed_length != 0:
            params["dry_allowed_length"] = self.dry_allowed_length
            
        return params
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DRYRepetitionPenaltyBlock":
        """Create from dictionary."""
        return cls(
            dry_multiplier=data.get("dry_multiplier", 0.0),
            dry_base=data.get("dry_base", 1.0),
            dry_allowed_length=data.get("dry_allowed_length", 0)
        )


@dataclass
class BasicSamplingBlock:
    """Basic sampling parameters block.
    
    Core sampling parameters that control randomness and token selection.
    """
    temperature: float = 0.7
    """Sampling temperature (0.0-2.0). Higher = more random, lower = more deterministic."""
    
    top_p: float = 0.9
    """Nucleus sampling: only consider tokens with cumulative probability > top_p (0.0-1.0)."""
    
    top_k: int = 40
    """Top-k sampling: only consider the top k tokens (0 = disabled)."""
    
    min_p: float = 0.0
    """Minimum probability threshold (0.0-1.0). Tokens below this are filtered out."""
    
    def to_params(self, include_defaults: bool = False) -> Dict[str, Any]:
        """Convert to API parameters.
        
        Args:
            include_defaults: If True, include all parameters even if default
            
        Returns:
            Dictionary of parameters for API
        """
        params = {}
        
        # Always include basic params
        params["temperature"] = self.temperature
        params["top_p"] = self.top_p
        
        if include_defaults or self.top_k != 40:
            params["top_k"] = self.top_k
        if include_defaults or self.min_p > 0.0:
            params["min_p"] = self.min_p
            
        return params
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BasicSamplingBlock":
        """Create from dictionary."""
        return cls(
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 0.9),
            top_k=data.get("top_k", 40),
            min_p=data.get("min_p", 0.0)
        )


def build_sampler_params(
    basic: Optional[BasicSamplingBlock] = None,
    repetition: Optional[RepetitionPenaltyBlock] = None,
    dry: Optional[DRYRepetitionPenaltyBlock] = None,
    xtc: Optional[XTCBlock] = None,
    mirostat: Optional[MirostatBlock] = None,
    include_defaults: bool = False
) -> Dict[str, Any]:
    """Build complete sampler parameters from blocks.
    
    Args:
        basic: Basic sampling parameters
        repetition: Traditional repetition penalty parameters
        dry: DRY (Dynamic Repetition Penalty) parameters for sequence-based repetition control
        xtc: XTC/typical sampling parameters
        mirostat: Mirostat parameters
        include_defaults: Include default values in output
        
    Returns:
        Complete dictionary of sampler parameters
    """
    params = {}
    
    # Use defaults if not provided
    if basic is None:
        basic = BasicSamplingBlock()
    if repetition is None:
        repetition = RepetitionPenaltyBlock()
    if dry is None:
        dry = DRYRepetitionPenaltyBlock()
    if xtc is None:
        xtc = XTCBlock()
    if mirostat is None:
        mirostat = MirostatBlock()
    
    # Merge all blocks
    params.update(basic.to_params(include_defaults))
    params.update(repetition.to_params(include_defaults))
    params.update(dry.to_params(include_defaults))  # DRY repetition penalty
    params.update(xtc.to_params(include_defaults))
    params.update(mirostat.to_params(include_defaults))
    
    return params

