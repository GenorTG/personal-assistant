"""Smooth Sampling implementation - quadratic/cubic probability distribution transformation.

This implements the same smooth sampling as SillyTavern, which applies a quadratic/cubic
transformation to adjust the probability distribution before sampling.

Formula: p_new = p^curve * (1 - smoothing_factor) + p * smoothing_factor

Lower smoothing_factor (0.2-0.3) = more creative
Higher smoothing_curve (1.0+) = steeper curve, punishes low probability choices more aggressively
1.0 curve is equivalent to only using smoothing_factor
"""
import math
import numpy as np
from typing import Tuple, Optional


def apply_smooth_sampling_to_logits(
    logits: np.ndarray,
    smoothing_factor: float,
    smoothing_curve: float
) -> np.ndarray:
    """Apply smooth sampling transformation to logits.
    
    This transforms the probability distribution using quadratic/cubic transformations
    before sampling, similar to SillyTavern's implementation.
    
    Args:
        logits: Raw logits from the model (numpy array)
        smoothing_factor: Smoothing factor (0.0-1.0). Lower = more creative (0.2-0.3 sweetspot)
        smoothing_curve: Curve value (1.0+). Higher = steeper curve, punishes low prob choices more
    
    Returns:
        Transformed logits
    """
    if smoothing_factor <= 0.0 or smoothing_curve <= 0.0:
        return logits
    
    # Convert logits to probabilities using softmax
    # Subtract max for numerical stability
    logits_max = np.max(logits)
    exp_logits = np.exp(logits - logits_max)
    probs = exp_logits / np.sum(exp_logits)
    
    # Apply smooth sampling transformation
    # Formula: p_new = p^curve * (1 - smoothing_factor) + p * smoothing_factor
    # This creates a blend between the original probability and the curve-transformed probability
    if smoothing_curve == 1.0:
        # When curve = 1.0, it's equivalent to only using smoothing_factor
        # p_new = p * (1 - smoothing_factor) + p * smoothing_factor = p (no transformation)
        # But we still apply smoothing_factor effect
        probs_smooth = probs * (1.0 - smoothing_factor) + probs * smoothing_factor
    else:
        # Apply curve transformation: p^curve
        # Add small epsilon to avoid numerical issues with very small probabilities
        epsilon = 1e-10
        probs_curved = np.power(np.maximum(probs, epsilon), smoothing_curve)
        # Renormalize curved probabilities
        probs_curved = probs_curved / np.sum(probs_curved)
        
        # Blend: p_new = p^curve * (1 - smoothing_factor) + p * smoothing_factor
        probs_smooth = probs_curved * (1.0 - smoothing_factor) + probs * smoothing_factor
    
    # Renormalize to ensure probabilities sum to 1
    probs_smooth = probs_smooth / np.sum(probs_smooth)
    
    # Convert back to logits (log space)
    # Add small epsilon to avoid log(0)
    epsilon = 1e-10
    logits_smooth = np.log(np.maximum(probs_smooth, epsilon))
    
    # Restore the original scale by adding back the max
    logits_smooth = logits_smooth + logits_max
    
    return logits_smooth


def calculate_smooth_sampling_adjustment(
    smoothing_factor: float,
    smoothing_curve: float
) -> Tuple[float, float]:
    """Calculate temperature and top_p adjustments to approximate smooth sampling.
    
    This is a fallback approximation when we can't access logits directly.
    Smooth sampling transforms the probability distribution using:
    p_new = p^curve * (1 - smoothing_factor) + p * smoothing_factor
    
    Since we can't access logits directly in llama-cpp-python's high-level API,
    we approximate this by adjusting temperature and top_p to achieve a similar
    distribution transformation effect.
    
    Args:
        smoothing_factor: Smoothing factor (0.0-1.0). Lower (0.2-0.3) = more creative
        smoothing_curve: Curve value (1.0+). Higher = steeper, punishes low prob choices more
    
    Returns:
        Tuple of (temperature_multiplier, top_p_multiplier)
    """
    if smoothing_factor <= 0.0:
        return (1.0, 1.0)  # No adjustment when disabled
    
    # The transformation p^curve makes the distribution sharper (more peaked)
    # Higher curve = sharper distribution = lower effective temperature
    # Smoothing factor controls how much of this transformation is applied
    
    # Temperature adjustment: sharper distribution = lower temperature
    # Formula: temp_adj = 1 - (smoothing_factor * (curve - 1) * 0.2)
    # This makes higher curves reduce temperature more significantly
    curve_effect = (smoothing_curve - 1.0) * smoothing_factor
    temp_multiplier = max(0.6, 1.0 - (curve_effect * 0.2))
    
    # Top_p adjustment: sharper distribution = more selective = lower top_p
    # Higher curve punishes low probability choices more = need lower top_p
    # Formula: top_p_adj = 1 - (smoothing_factor * (curve - 1) * 0.15)
    top_p_multiplier = max(0.7, 1.0 - (curve_effect * 0.15))
    
    return (temp_multiplier, top_p_multiplier)
