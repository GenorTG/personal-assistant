"""
Model information extractor.

Extracts metadata from LLM models including:
- Architecture type
- Parameter count
- Context length
- Quantization
- MoE configuration
"""

from typing import Dict, Any, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class ModelInfoExtractor:
    """Extract metadata from LLM model files."""
    
    # Architecture name mappings
    ARCH_NAMES = {
        "llama": "LLaMA",
        "mistral": "Mistral",
        "mixtral": "Mixtral",
        "qwen": "Qwen",
        "phi": "Phi",
        "gemma": "Gemma",
        "yi": "Yi",
        "deepseek": "DeepSeek",
        "stablelm": "StableLM",
    }
    
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
    
    def _parse_param_count(self, model_name: str) -> Optional[str]:
        """Extract parameter count from model name (e.g., '7B', '13B')."""
        import re
        
        # Look for patterns like 7B, 13B, 70B, 8x7B
        patterns = [
            r'(\d+x\d+\.?\d*[BM])',  # MoE: 8x7B, 8x7.5B
            r'(\d+\.?\d*[BM])',  # Regular: 7B, 13B, 7.5B
        ]
        
        for pattern in patterns:
            match = re.search(pattern, model_name, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _detect_architecture(self, model_name: str, config: Dict = None) -> str:
        """Detect model architecture from name or config."""
        model_lower = model_name.lower()
        
        # Check config first if available
        if config:
            arch_type = config.get("model_type", "").lower()
            for key, name in self.ARCH_NAMES.items():
                if key in arch_type:
                    return name
        
        # Check model name
        for key, name in self.ARCH_NAMES.items():
            if key in model_lower:
                return name
        
        return "Unknown"
    
    def _detect_moe(self, config: Dict) -> Optional[Dict[str, Any]]:
        """Detect if model is MoE and extract expert configuration."""
        if not config:
            return None
        
        # Check for MoE indicators
        num_experts = config.get("num_local_experts") or config.get("num_experts")
        experts_per_tok = config.get("num_experts_per_tok")
        
        if num_experts and num_experts > 1:
            return {
                "is_moe": True,
                "num_experts": num_experts,
                "experts_per_token": experts_per_tok or 2,
                "router_aux_loss_coef": config.get("router_aux_loss_coef", 0.001)
            }
        
        return {"is_moe": False}
    
    def _get_context_length(self, config: Dict) -> int:
        """Extract max context length from config."""
        if not config:
            return 2048  # Default
        
        # Try various config keys
        context_keys = [
            "max_position_embeddings",
            "max_sequence_length",
            "n_positions",
            "seq_length",
        ]
        
        for key in context_keys:
            if key in config:
                return config[key]
        
        return 2048
    
    def _load_config(self, model_path: Path) -> Optional[Dict]:
        """Load config.json from model directory."""
        config_path = model_path / "config.json"
        
        if not config_path.exists():
            logger.warning(f"No config.json found for {model_path.name}")
            return None
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config.json: {e}")
            return None
    
    def _extract_gguf_metadata(self, model_path: Path) -> Dict[str, Any]:
        """Extract metadata directly from GGUF file."""
        try:
            import gguf
            reader = gguf.GGUFReader(str(model_path))
            
            # Extract key info
            info = {}
            
            # Architecture
            arch = "Unknown"
            if "general.architecture" in reader.fields:
                arch_key = reader.fields["general.architecture"].parts[-1].tobytes().decode("utf-8")
                arch = self.ARCH_NAMES.get(arch_key, arch_key.capitalize())
            info["architecture"] = arch
            
            # Context length
            ctx_len = 2048
            for key in ["llama.context_length", f"{arch_key}.context_length"]:
                if key in reader.fields:
                    ctx_len = int(reader.fields[key].parts[-1][0])
                    break
            info["context_length"] = ctx_len
            
            # Parameters (rough estimate from file size if not in metadata)
            # Some GGUFs have parameter count metadata
            if "general.parameter_count" in reader.fields:
                param_count = int(reader.fields["general.parameter_count"].parts[-1][0])
                info["num_parameters"] = param_count
                # Convert to readable string (e.g. 7B)
                if param_count > 1e9:
                    info["parameters"] = f"{param_count / 1e9:.1f}B"
                else:
                    info["parameters"] = f"{param_count / 1e6:.1f}M"
            
            # MoE Info
            moe_info = {"is_moe": False}
            expert_count_key = f"{arch_key}.expert_count"
            if expert_count_key in reader.fields:
                count = int(reader.fields[expert_count_key].parts[-1][0])
                if count > 1:
                    moe_info = {
                        "is_moe": True,
                        "num_experts": count,
                        "experts_per_token": 2 # Default, hard to extract sometimes
                    }
                    # Try to find experts used count
                    used_key = f"{arch_key}.expert_used_count"
                    if used_key in reader.fields:
                        moe_info["experts_per_token"] = int(reader.fields[used_key].parts[-1][0])
            info["moe"] = moe_info
            
            # Layer count
            layer_key = f"{arch_key}.block_count"
            if layer_key in reader.fields:
                info["num_layers"] = int(reader.fields[layer_key].parts[-1][0])
                
            # Hidden size
            embd_key = f"{arch_key}.embedding_length"
            if embd_key in reader.fields:
                info["hidden_size"] = int(reader.fields[embd_key].parts[-1][0])
                
            return info
            
        except ImportError:
            logger.warning("gguf library not installed, skipping GGUF metadata extraction")
            return {}
        except Exception as e:
            logger.error(f"Error reading GGUF metadata: {e}")
            return {}

    def extract_info(self, model_name: str) -> Dict[str, Any]:
        """
        Extract comprehensive model information.
        
        Args:
            model_name: Name of the model (folder name or file name)
            
        Returns:
            Dict with model metadata
        """
        model_path = self.models_dir / model_name
        
        # Load config if available (for HF models)
        config = None
        if model_path.is_dir():
            config = self._load_config(model_path)
            
        # Extract GGUF metadata if it's a GGUF file
        gguf_info = {}
        if model_path.is_file() and model_path.suffix.lower() == ".gguf":
            gguf_info = self._extract_gguf_metadata(model_path)
        
        # Extract information (prioritize GGUF info, fallback to config/name)
        architecture = gguf_info.get("architecture") or self._detect_architecture(model_name, config)
        param_count = gguf_info.get("parameters") or self._parse_param_count(model_name)
        moe_info = gguf_info.get("moe") or (self._detect_moe(config) if config else {"is_moe": False})
        context_length = gguf_info.get("context_length") or (self._get_context_length(config) if config else 2048)
        
        # Get model parameters
        num_parameters = gguf_info.get("num_parameters")
        num_layers = gguf_info.get("num_layers")
        hidden_size = gguf_info.get("hidden_size")
        
        if not num_parameters and config:
            num_layers = config.get("num_hidden_layers") or config.get("n_layer")
            hidden_size = config.get("hidden_size") or config.get("n_embd")
            
            # Estimate parameters if not in config
            if num_layers and hidden_size:
                # Rough estimate: 12 × layers × hidden_size²
                num_parameters = 12 * num_layers * (hidden_size ** 2)
        
        # Detect quantization from name
        quantization = self._detect_quantization(model_name)
        
        # Get file size if it's a file
        file_size_gb = None
        if model_path.is_file():
            file_size_gb = model_path.stat().st_size / (1024 ** 3)
        elif model_path.is_dir():
            # Sum all .bin, .safetensors, .gguf files
            total_size = 0
            for ext in ['*.bin', '*.safetensors', '*.gguf']:
                for file in model_path.glob(ext):
                    total_size += file.stat().st_size
            if total_size > 0:
                file_size_gb = total_size / (1024 ** 3)
        
        return {
            "name": model_name,
            "architecture": architecture,
            "parameters": param_count,
            "num_parameters": num_parameters,
            "num_layers": num_layers,
            "hidden_size": hidden_size,
            "quantization": quantization,
            "file_size_gb": round(file_size_gb, 2) if file_size_gb else None,
            "context": {
                "max_length": context_length,
                "recommended": min(context_length, 4096),  # Recommend 4K for most use cases
            },
            "moe": moe_info,
            "config": config
        }
    
    def _detect_quantization(self, model_name: str) -> Optional[str]:
        """Detect quantization type from model name."""
        quants = [
            "F32", "F16", "BF16",
            "Q8_0", "Q6_K", "Q5_K_M", "Q5_K_S", "Q5_0",
            "Q4_K_M", "Q4_K_S", "Q4_0",
            "Q3_K_M", "Q3_K_S", "Q2_K",
            "IQ4_XS", "IQ3_M", "IQ2_XS"
        ]
        
        model_upper = model_name.upper()
        for quant in quants:
            # Check for exact match or surrounded by non-alphanumeric
            if quant in model_upper:
                return quant
        
        return None
