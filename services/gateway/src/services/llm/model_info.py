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
import time

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

logger = logging.getLogger(__name__)


class ModelInfoExtractor:
    """Extract metadata from LLM model files.
    
    Optimized with caching to avoid repeated file I/O and GGUF parsing.
    """
    
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
        # Cache for model info to avoid repeated extraction
        self._info_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 3600  # Cache for 1 hour
    
    def _parse_param_count(self, model_name: str) -> Optional[str]:
        """Extract parameter count from model name (e.g., '7B', '13B')."""
        import re
        
        # Look for patterns like 7B, 13B, 70B, 8x7B
        patterns = [
            r'(\d+x\d+[BM])',  # MoE: 8x7B
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
    
    def _detect_moe(self, config: Dict, model_name: str = "") -> Optional[Dict[str, Any]]:
        """Detect if model is MoE and extract expert configuration.
        
        Enhanced detection that checks:
        1. Config file (num_local_experts, num_experts)
        2. Model name patterns (8x7B, etc.)
        3. Architecture name (mixtral, etc.)
        
        Args:
            config: Model config dictionary
            model_name: Model name for pattern matching
            
        Returns:
            MoE info dictionary with is_moe, num_experts, experts_per_token
        """
        moe_info = {"is_moe": False}
        
        # Check config first (most reliable)
        if config:
            num_experts = config.get("num_local_experts") or config.get("num_experts")
            experts_per_tok = config.get("num_experts_per_tok")
            
            if num_experts and num_experts > 1:
                moe_info = {
                    "is_moe": True,
                    "num_experts": num_experts,
                    "experts_per_token": experts_per_tok or 2,
                    "router_aux_loss_coef": config.get("router_aux_loss_coef", 0.001)
                }
                return moe_info
        
        # Check model name for MoE patterns (e.g., 8x7B, mixtral)
        if model_name:
            import re
            model_lower = model_name.lower()
            
            # Check for MoE architecture names
            if "mixtral" in model_lower:
                # Mixtral is always MoE (8x7B typically)
                moe_info = {
                    "is_moe": True,
                    "num_experts": 8,  # Default for Mixtral
                    "experts_per_token": 2,
                    "router_aux_loss_coef": 0.001
                }
                # Try to extract actual expert count from name
                expert_match = re.search(r'(\d+)x(\d+)', model_name, re.IGNORECASE)
                if expert_match:
                    moe_info["num_experts"] = int(expert_match.group(1))
                return moe_info
            
            # Check for NxM pattern (e.g., 8x7B, 4x3B, 4X3B)
            # Match patterns like: 4x3B, 8x7B, 4X3B (case insensitive, with or without B/M suffix)
            expert_pattern = re.search(r'(\d+)[xX](\d+)', model_name, re.IGNORECASE)
            if expert_pattern:
                num_experts = int(expert_pattern.group(1))
                if num_experts > 1:
                    logger.debug(f"Detected MoE with {num_experts} experts from model name pattern: {model_name}")
                    moe_info = {
                        "is_moe": True,
                        "num_experts": num_experts,
                        "experts_per_token": 2,  # Default
                        "router_aux_loss_coef": 0.001
                    }
                    return moe_info
        
        return moe_info
    
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
    
    def _fetch_hf_config(self, repo_id: str) -> Optional[Dict]:
        """Fetch config.json from HuggingFace repository.
        
        Args:
            repo_id: HuggingFace repository ID (e.g., "DavidAU/Llama-3.2-4X3B-MOE-Hell-California-Uncensored-10B-GGUF")
            
        Returns:
            Config dictionary or None if not found/error
        """
        try:
            from huggingface_hub import hf_hub_download
            import tempfile
            
            # Download config.json to temp file
            with tempfile.TemporaryDirectory() as tmpdir:
                config_path = hf_hub_download(
                    repo_id=repo_id,
                    filename="config.json",
                    local_dir=tmpdir,
                    local_dir_use_symlinks=False
                )
                
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"Successfully fetched config.json from HuggingFace for {repo_id}")
                    # Log MoE info if found
                    num_experts = config.get("num_local_experts") or config.get("num_experts")
                    if num_experts:
                        logger.info(f"Found {num_experts} experts in HuggingFace config.json for {repo_id}")
                    return config
        except Exception as e:
            logger.debug(f"Could not fetch config.json from HuggingFace for {repo_id}: {e}")
            return None
    
    def _extract_gguf_metadata(self, model_path: Path) -> Dict[str, Any]:
        """Extract metadata directly from GGUF file."""
        try:
            import gguf
            try:
                reader = gguf.GGUFReader(str(model_path))
            except (ValueError, TypeError, AttributeError) as reader_error:
                # Handle unknown quantization types or other GGUF format issues
                error_msg = str(reader_error)
                if "GGMLQuantizationType" in error_msg or "quantization" in error_msg.lower():
                    logger.warning(f"GGUF file has unknown quantization type, attempting to read with error tolerance: {error_msg}")
                    # Try to read anyway - some fields might still be accessible
                    try:
                        reader = gguf.GGUFReader(str(model_path))
                    except Exception:
                        logger.error(f"Cannot read GGUF file due to format issue: {error_msg}")
                        return {}
                else:
                    raise
            
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
            
            # MoE Info - Enhanced detection from GGUF
            moe_info = {"is_moe": False}
            
            # Try multiple possible keys for expert count (different architectures use different keys)
            expert_count = None
            expert_count_keys = [
                f"{arch_key}.expert_count",  # Most common
                f"{arch_key}.num_experts",   # Alternative naming
                "llama.expert_count",        # Fallback for llama-based MoE
                "llama.num_experts",         # Fallback alternative
                "general.expert_count",      # Some models use general prefix
            ]
            
            for key in expert_count_keys:
                if key in reader.fields:
                    try:
                        expert_count = int(reader.fields[key].parts[-1][0])
                        if expert_count > 1:
                            logger.debug(f"Found expert count {expert_count} from key: {key}")
                            break
                    except (ValueError, IndexError, KeyError, TypeError):
                        continue
            
            # If not found, try searching all fields for expert-related keys
            if not expert_count:
                logger.debug(f"Expert count not found in standard keys, searching all GGUF fields...")
                for field_name in reader.fields.keys():
                    if "expert" in field_name.lower() and ("count" in field_name.lower() or "num" in field_name.lower()):
                        try:
                            field_value = reader.fields[field_name]
                            # Try to extract integer value
                            if hasattr(field_value, 'parts') and field_value.parts:
                                value = field_value.parts[-1]
                                if isinstance(value, (list, tuple)) and len(value) > 0:
                                    expert_count = int(value[0])
                                elif isinstance(value, (int, float)):
                                    expert_count = int(value)
                                if expert_count and expert_count > 1:
                                    logger.debug(f"Found expert count {expert_count} from field: {field_name}")
                                    break
                        except (ValueError, IndexError, KeyError, TypeError, AttributeError) as e:
                            logger.debug(f"Error extracting expert count from field {field_name}: {e}")
                            continue
            
            if expert_count and expert_count > 1:
                moe_info = {
                    "is_moe": True,
                    "num_experts": expert_count,
                    "experts_per_token": 2  # Default, hard to extract sometimes
                }
                # Try to find experts used count (multiple possible keys)
                experts_per_token_keys = [
                    f"{arch_key}.expert_used_count",
                    f"{arch_key}.num_experts_to_use",
                    "llama.expert_used_count",
                    "llama.num_experts_to_use",
                ]
                for used_key in experts_per_token_keys:
                    if used_key in reader.fields:
                        try:
                            moe_info["experts_per_token"] = int(reader.fields[used_key].parts[-1][0])
                            break
                        except (ValueError, IndexError, KeyError):
                            continue
            else:
                # Fallback: check architecture name for MoE models
                if "mixtral" in arch_key.lower():
                    moe_info = {
                        "is_moe": True,
                        "num_experts": 8,  # Default for Mixtral
                        "experts_per_token": 2
                    }
                elif "moe" in arch_key.lower() or "mixture" in arch_key.lower():
                    # Generic MoE model but couldn't extract count - mark as MoE but require manual entry
                    moe_info = {
                        "is_moe": True,
                        "num_experts": None,  # Unknown - will require manual entry
                        "experts_per_token": 2
                    }
            info["moe"] = moe_info
            
            # Layer count
            layer_key = f"{arch_key}.block_count"
            if layer_key in reader.fields:
                info["num_layers"] = int(reader.fields[layer_key].parts[-1][0])
                
            # Hidden size
            embd_key = f"{arch_key}.embedding_length"
            if embd_key in reader.fields:
                info["hidden_size"] = int(reader.fields[embd_key].parts[-1][0])
            
            # Extract chat template from GGUF metadata
            # Try multiple possible keys for chat template
            chat_template_keys = [
                "tokenizer.chat_template",
                "tokenizer.chat.template",
                "general.chat_template",
                "chat_template",
            ]
            
            chat_template = None
            for key in chat_template_keys:
                if key in reader.fields:
                    logger.debug(f"Found chat_template key: {key}")
                    try:
                        field_value = reader.fields[key]
                        logger.debug(f"Field value type: {type(field_value)}")
                        # Extract string value from GGUF field
                        # GGUF fields can have different structures
                        if hasattr(field_value, 'parts') and field_value.parts:
                            # Get the last part (usually contains the actual data)
                            last_part = field_value.parts[-1]
                            logger.debug(f"Last part type: {type(last_part)}, hasattr numpy: {HAS_NUMPY}")
                            if HAS_NUMPY:
                                logger.debug(f"Is numpy array: {isinstance(last_part, np.ndarray)}")
                                if isinstance(last_part, np.ndarray):
                                    logger.debug(f"  dtype: {last_part.dtype}, shape: {last_part.shape}")
                            
                            # Handle different data types
                            if isinstance(last_part, bytes):
                                chat_template = last_part.decode("utf-8")
                            elif isinstance(last_part, str):
                                chat_template = last_part
                            else:
                                # Try to handle numpy arrays, memmaps, lists, tuples
                                try:
                                    if HAS_NUMPY:
                                        # Check if it's a numpy array (including memmap)
                                        # memmap is a subclass of ndarray, so this should work
                                        if isinstance(last_part, np.ndarray):
                                            logger.debug(f"Found numpy array for {key}: dtype={last_part.dtype}, shape={last_part.shape}")
                                            # Convert numpy array to bytes
                                            if last_part.dtype == np.uint8:
                                                chat_template = bytes(last_part).decode("utf-8")
                                            else:
                                                # Convert to uint8 first
                                                chat_template = bytes(last_part.astype(np.uint8)).decode("utf-8")
                                        elif isinstance(last_part, (list, tuple)) and len(last_part) > 0:
                                            # List/tuple of bytes or ints
                                            if isinstance(last_part[0], bytes):
                                                chat_template = b''.join(last_part).decode("utf-8")
                                            elif isinstance(last_part[0], (int, np.integer)):
                                                chat_template = bytes(last_part).decode("utf-8")
                                            else:
                                                # Try to decode as bytes anyway
                                                chat_template = bytes(last_part).decode("utf-8")
                                    else:
                                        # No numpy - try to handle as list/tuple
                                        if isinstance(last_part, (list, tuple)) and len(last_part) > 0:
                                            if isinstance(last_part[0], bytes):
                                                chat_template = b''.join(last_part).decode("utf-8")
                                            elif isinstance(last_part[0], int):
                                                chat_template = bytes(last_part).decode("utf-8")
                                            else:
                                                chat_template = ''.join(str(x) for x in last_part)
                                except (ValueError, UnicodeDecodeError, TypeError, AttributeError) as e:
                                    logger.debug(f"Error decoding array field {key}: {e}")
                                    # Try alternative: convert to string
                                    try:
                                        chat_template = ''.join(str(x) for x in last_part) if hasattr(last_part, '__iter__') else str(last_part)
                                    except:
                                        pass
                            
                            if chat_template:
                                logger.debug(f"Extracted chat template from GGUF key: {key} (length: {len(chat_template)})")
                                break
                    except (ValueError, IndexError, KeyError, TypeError, AttributeError, UnicodeDecodeError) as e:
                        logger.debug(f"Error extracting chat template from key {key}: {e}")
                        continue
            
            if chat_template:
                info["chat_template"] = chat_template
                
            return info
            
        except ImportError:
            logger.warning("gguf library not installed, skipping GGUF metadata extraction")
            return {}
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            # Handle specific GGUF format errors gracefully
            error_msg = str(e)
            if "GGMLQuantizationType" in error_msg or "quantization" in error_msg.lower():
                logger.warning(f"GGUF file has unsupported quantization type, will use fallback methods: {error_msg}")
            else:
                logger.warning(f"Error reading some GGUF metadata fields (will use fallbacks): {error_msg}")
            # Return empty dict - fallback methods (config.json, name parsing) will be used
            return {}
        except Exception as e:
            logger.error(f"Unexpected error reading GGUF metadata: {e}")
            # Still return empty dict so fallback methods can be used
            return {}

    def extract_info(self, model_name: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Extract comprehensive model information.
        
        Optimized with caching to avoid repeated file I/O.
        
        Args:
            model_name: Name of the model (folder name or file name)
            use_cache: Whether to use cached results (default: True)
            
        Returns:
            Dict with model metadata
        """
        # Check cache first
        if use_cache and model_name in self._info_cache:
            cache_time = self._cache_timestamps.get(model_name, 0)
            if time.time() - cache_time < self._cache_ttl:
                logger.debug(f"Using cached model info for {model_name}")
                return self._info_cache[model_name].copy()
        
        model_path = self.models_dir / model_name
        
        # If model_path doesn't exist, try to find it recursively
        if not model_path.exists():
            # Search for the file recursively in models_dir
            found_files = list(self.models_dir.glob(f"**/{model_name}"))
            if found_files:
                model_path = found_files[0]
                logger.debug(f"Found model file at: {model_path}")
        
        # Check for cached metadata in model_info.json first
        metadata_file = model_path.parent / "model_info.json" if model_path.is_file() else model_path / "model_info.json"
        cached_tool_calling = None
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    cached_metadata = json.load(f)
                    cached_tool_calling = cached_metadata.get("tool_calling")
                    if cached_tool_calling:
                        logger.debug(f"Found cached tool calling info in {metadata_file}")
            except Exception as e:
                logger.debug(f"Could not read cached metadata: {e}")
        
        # Load config if available (for HF models)
        config = None
        if model_path.is_dir():
            config = self._load_config(model_path)
        
        
        # Extract GGUF metadata if it's a GGUF file
        gguf_info = {}
        if model_path.is_file() and model_path.suffix.lower() == ".gguf":
            gguf_info = self._extract_gguf_metadata(model_path)
            
        # Try to fetch config.json from HuggingFace if we have repo_id in metadata
        # Only fetch if we didn't get info from GGUF and don't have local config
        hf_config = None
        if not config and not gguf_info:
            # Check for model_info.json to get repo_id (already loaded above)
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        repo_id = metadata.get("repo_id")
                        if repo_id:
                            logger.debug(f"Found repo_id {repo_id} in metadata, fetching config.json from HuggingFace...")
                            hf_config = self._fetch_hf_config(repo_id)
                            if hf_config:
                                logger.debug(f"Successfully fetched config.json from HuggingFace for {repo_id}")
                                # Use HF config if local config not available
                                config = hf_config
                except Exception as e:
                    logger.debug(f"Could not read metadata or fetch HF config: {e}")
        
        # Extract information (prioritize GGUF info, fallback to config/name)
        architecture = gguf_info.get("architecture") or self._detect_architecture(model_name, config)
        param_count = gguf_info.get("parameters") or self._parse_param_count(model_name)
        
        # Enhanced MoE detection (checks config, GGUF, and name patterns)
        # Priority: GGUF > HuggingFace config.json > name pattern
        moe_info = gguf_info.get("moe")
        if not moe_info or not moe_info.get("is_moe"):
            moe_info = self._detect_moe(config, model_name)
        elif moe_info.get("is_moe") and not moe_info.get("num_experts"):
            # GGUF detected MoE but didn't find expert count - try config and name-based parsing
            # First try config (from HuggingFace or local)
            if config:
                config_moe = self._detect_moe(config, model_name)
                if config_moe.get("is_moe") and config_moe.get("num_experts"):
                    moe_info["num_experts"] = config_moe["num_experts"]
                    logger.debug(f"Extracted expert count {moe_info['num_experts']} from config.json")
            # Fallback to name-based parsing
            if not moe_info.get("num_experts"):
                name_based_moe = self._detect_moe(None, model_name)
                if name_based_moe.get("is_moe") and name_based_moe.get("num_experts"):
                    moe_info["num_experts"] = name_based_moe["num_experts"]
                    logger.debug(f"Extracted expert count {moe_info['num_experts']} from model name: {model_name}")
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
        
        # Detect tool calling support - use cached if available, otherwise detect
        tool_calling_info = cached_tool_calling
        if not tool_calling_info:
            chat_template = gguf_info.get("chat_template")
            if chat_template:
                from .tool_calling_detector import detect_tool_calling_from_chat_template
                supports, suggested_format = detect_tool_calling_from_chat_template(chat_template)
                tool_calling_info = {
                    "supports_tool_calling": supports,
                    "suggested_chat_format": suggested_format,
                    "detection_method": "chat_template",
                    "chat_template_length": len(chat_template)
                }
            else:
                # Fallback to pattern matching if no chat template
                from .tool_calling_detector import detect_tool_calling_from_metadata
                supports, suggested_format = detect_tool_calling_from_metadata(
                    model_id=str(model_path),
                    model_name=model_name,
                    architecture=architecture,
                    tags=None,
                    repo_id=None,
                    remote_fetch=False,
                    chat_template=None
                )
                tool_calling_info = {
                    "supports_tool_calling": supports,
                    "suggested_chat_format": suggested_format,
                    "detection_method": "pattern_matching"
                }
            
            # Save tool calling info to model_info.json for future use
            if tool_calling_info and model_path.is_file():
                try:
                    if metadata_file.exists():
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    else:
                        metadata = {}
                    
                    metadata["tool_calling"] = tool_calling_info
                    
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                    
                    logger.debug(f"Saved tool calling info to {metadata_file}")
                except Exception as e:
                    logger.debug(f"Could not save tool calling info to {metadata_file}: {e}")
        
        # Store chat_template in result for potential saving
        result = {
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
            "config": config,
            "chat_template": gguf_info.get("chat_template"),  # Chat template from GGUF metadata
            "tool_calling": tool_calling_info  # Tool calling detection results
        }
        
        # Cache the result
        if use_cache:
            self._info_cache[model_name] = result.copy()
            self._cache_timestamps[model_name] = time.time()
        
        return result
    
    def extract_and_save_template(self, model_name: str, force: bool = False, repo_id: Optional[str] = None) -> Optional[Path]:
        """Extract chat template from GGUF and save as .jinja file.
        
        If template is not found in GGUF metadata, attempts to fetch from HuggingFace
        using the get_chat_template utility.
        
        Args:
            model_name: Name of the model (folder name or file name)
            force: If True, overwrite existing template file
            repo_id: Optional HuggingFace repo ID to fetch template from (if not in GGUF)
            
        Returns:
            Path to saved template file, or None if extraction/saving failed
        """
        # Extract model info (this includes chat_template)
        model_info = self.extract_info(model_name, use_cache=True)
        chat_template = model_info.get("chat_template")
        
        # If no template found in GGUF, try fetching from HuggingFace
        if not chat_template:
            logger.debug(f"No chat template found in GGUF metadata for {model_name}, attempting to fetch from HuggingFace...")
            
            # Get repo_id from parameter or try to find it in metadata
            if not repo_id:
                model_path = self.models_dir / model_name
                if not model_path.exists():
                    found_files = list(self.models_dir.glob(f"**/{model_name}"))
                    if found_files:
                        model_path = found_files[0]
                
                metadata_file = model_path.parent / "model_info.json" if model_path.is_file() else model_path / "model_info.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            repo_id = metadata.get("repo_id")
                            if repo_id:
                                logger.debug(f"Found repo_id {repo_id} in metadata, fetching template from HuggingFace...")
                    except Exception as e:
                        logger.debug(f"Could not read metadata to get repo_id: {e}")
            
            # Try to fetch template from HuggingFace
            if repo_id:
                try:
                    from ...utils.get_chat_template import get_chat_template
                    chat_template = get_chat_template(repo_id)
                    logger.info(f"✓ Successfully fetched chat template from HuggingFace for {repo_id}")
                except Exception as e:
                    logger.warning(f"Failed to fetch chat template from HuggingFace for {repo_id}: {e}")
                    return None
            else:
                logger.debug(f"No repo_id available to fetch template from HuggingFace for {model_name}")
            return None
        
        # Determine model path and template file path
        model_path = self.models_dir / model_name
        if not model_path.exists():
            found_files = list(self.models_dir.glob(f"**/{model_name}"))
            if found_files:
                model_path = found_files[0]
            else:
                logger.warning(f"Model path not found: {model_name}")
                return None
        
        # Template file should be in the same directory as the model
        if model_path.is_file():
            template_dir = model_path.parent
            template_filename = model_path.stem + ".jinja"
        else:
            template_dir = model_path
            template_filename = model_name + ".jinja"
        
        template_file = template_dir / template_filename
        
        # Check if template file already exists
        if template_file.exists() and not force:
            logger.debug(f"Template file already exists: {template_file}")
            return template_file
        
        # Save template to file
        try:
            template_file.parent.mkdir(parents=True, exist_ok=True)
            with open(template_file, 'w', encoding='utf-8') as f:
                f.write(chat_template)
            logger.info(f"✓ Saved chat template to: {template_file}")
            return template_file
        except Exception as e:
            logger.error(f"Failed to save chat template to {template_file}: {e}")
            return None
    
    def clear_cache(self, model_name: Optional[str] = None):
        """Clear model info cache.
        
        Args:
            model_name: Specific model to clear, or None to clear all
        """
        if model_name:
            self._info_cache.pop(model_name, None)
            self._cache_timestamps.pop(model_name, None)
        else:
            self._info_cache.clear()
            self._cache_timestamps.clear()
    
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
            if quant in model_upper:
                return quant
        
        return None
