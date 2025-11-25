"""
Memory calculator for LLM models.

Estimates VRAM/RAM requirements based on:
- Model size (parameters × bytes per parameter)
- KV cache (context-dependent)
- Activations
- Overhead
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MemoryCalculator:
    """Calculate memory requirements for LLM models."""
    
    # Quantization bytes per parameter
    QUANT_BYTES = {
        "F32": 4.0,
        "F16": 2.0,
        "BF16": 2.0,
        "Q8_0": 1.125,
        "Q6_K": 0.6875,
        "Q5_K_M": 0.625,
        "Q5_K_S": 0.5625,
        "Q5_0": 0.5625,
        "Q4_K_M": 0.58,
        "Q4_K_S": 0.55,
        "Q4_0": 0.55,
        "Q3_K_M": 0.48,
        "Q3_K_S": 0.44,
        "Q2_K": 0.35,
        "IQ4_XS": 0.52,
        "IQ3_M": 0.44,
        "IQ2_XS": 0.31,
    }
    
    def __init__(self):
        self.overhead_gb = 0.5  # General overhead
    
    def _detect_quantization(self, model_name: str) -> str:
        """Detect quantization from model name."""
        model_upper = model_name.upper()
        
        # Check for quantization in name
        for quant in self.QUANT_BYTES.keys():
            if quant in model_upper:
                return quant
        
        # Default to F16 if not specified
        return "F16"
    
    def _get_bytes_per_param(self, quantization: str) -> float:
        """Get bytes per parameter for quantization type."""
        return self.QUANT_BYTES.get(quantization, 2.0)
    
    def calculate_model_size(
        self,
        num_parameters: float,
        quantization: str = "F16"
    ) -> float:
        """
        Calculate model weight size in GB.
        
        Args:
            num_parameters: Number of parameters (e.g., 7e9 for 7B)
            quantization: Quantization type
            
        Returns:
            Model size in GB
        """
        bytes_per_param = self._get_bytes_per_param(quantization)
        size_bytes = num_parameters * bytes_per_param
        return size_bytes / (1024 ** 3)  # Convert to GB
    
    def calculate_kv_cache(
        self,
        num_layers: int,
        hidden_size: int,
        context_length: int,
        batch_size: int = 1,
        precision_bytes: int = 2  # FP16
    ) -> float:
        """
        Calculate KV cache size in GB.
        
        Formula: 2 (K+V) × layers × hidden_size × context × batch × precision
        
        Args:
            num_layers: Number of transformer layers
            hidden_size: Hidden dimension size
            context_length: Context window size
            batch_size: Batch size
            precision_bytes: Bytes per value (2 for FP16)
            
        Returns:
            KV cache size in GB
        """
        kv_cache_bytes = (
            2 *  # K and V
            num_layers *
            hidden_size *
            context_length *
            batch_size *
            precision_bytes
        )
        return kv_cache_bytes / (1024 ** 3)
    
    def calculate_activations(
        self,
        hidden_size: int,
        context_length: int,
        batch_size: int = 1,
        precision_bytes: int = 4  # FP32 for activations
    ) -> float:
        """
        Calculate activation memory in GB (rough estimate).
        
        Args:
            hidden_size: Hidden dimension size
            context_length: Context window size
            batch_size: Batch size
            precision_bytes: Bytes per activation
            
        Returns:
            Activation size in GB
        """
        activation_bytes = (
            hidden_size *
            context_length *
            batch_size *
            precision_bytes
        )
        return activation_bytes / (1024 ** 3)
    
    def estimate_total_memory(
        self,
        model_params: Dict[str, Any],
        context_length: int = 2048,
        batch_size: int = 1
    ) -> Dict[str, Any]:
        """
        Estimate total memory requirement.
        
        Args:
            model_params: Dict with model parameters:
                - num_parameters: Total parameters
                - num_layers: Number of layers
                - hidden_size: Hidden dimension
                - quantization: Quantization type (optional)
                - model_name: Model name (optional, for quant detection)
            context_length: Context window size
            batch_size: Batch size
            
        Returns:
            Dict with memory breakdown and total
        """
        num_parameters = model_params.get("num_parameters", 0)
        num_layers = model_params.get("num_layers", 32)
        hidden_size = model_params.get("hidden_size", 4096)
        
        # Detect quantization
        quantization = model_params.get("quantization")
        if not quantization and "model_name" in model_params:
            quantization = self._detect_quantization(model_params["model_name"])
        if not quantization:
            quantization = "F16"
        
        # Calculate components
        model_size = self.calculate_model_size(num_parameters, quantization)
        kv_cache = self.calculate_kv_cache(
            num_layers, hidden_size, context_length, batch_size
        )
        activations = self.calculate_activations(
            hidden_size, context_length, batch_size
        )
        
        total = model_size + kv_cache + activations + self.overhead_gb
        
        return {
            "model_size_gb": round(model_size, 2),
            "kv_cache_gb": round(kv_cache, 2),
            "activations_gb": round(activations, 2),
            "overhead_gb": round(self.overhead_gb, 2),
            "total_gb": round(total, 2),
            "quantization": quantization,
            "context_length": context_length,
            "batch_size": batch_size,
            "breakdown": {
                "weights": round(model_size, 2),
                "kv_cache": round(kv_cache, 2),
                "activations": round(activations, 2),
                "overhead": round(self.overhead_gb, 2)
            }
        }
    
    def get_recommended_vram(self, total_gb: float) -> int:
        """
        Get recommended VRAM based on estimated usage.
        Adds 20% buffer for safety.
        
        Args:
            total_gb: Estimated total memory in GB
            
        Returns:
            Recommended VRAM in GB (rounded up to common sizes)
        """
        with_buffer = total_gb * 1.2
        
        # Round up to common VRAM sizes
        common_sizes = [4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80]
        for size in common_sizes:
            if with_buffer <= size:
                return size
        
        return int(with_buffer) + 1


# Global instance
memory_calculator = MemoryCalculator()
