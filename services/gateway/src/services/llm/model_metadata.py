"""Model metadata extraction and architecture detection."""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def detect_architecture(model_info) -> str:
    """Detect model architecture from model info.
    
    Args:
        model_info: HuggingFace model info object
        
    Returns:
        Architecture name (e.g., "Llama 3", "Mistral", "Qwen")
    """
    tags = list(getattr(model_info, 'tags', []))
    model_id = getattr(model_info, 'id', '').lower()
    
    # Check tags first
    for tag in tags:
        tag_lower = tag.lower()
        if 'llama-3' in tag_lower or 'llama3' in tag_lower:
            return "Llama 3"
        elif 'llama-2' in tag_lower or 'llama2' in tag_lower:
            return "Llama 2"
        elif 'llama' in tag_lower:
            return "Llama"
        elif 'mistral' in tag_lower:
            return "Mistral"
        elif 'mixtral' in tag_lower:
            return "Mixtral"
        elif 'qwen2.5' in tag_lower:
            return "Qwen 2.5"
        elif 'qwen2' in tag_lower:
            return "Qwen 2"
        elif 'qwen' in tag_lower:
            return "Qwen"
        elif 'phi-3' in tag_lower or 'phi3' in tag_lower:
            return "Phi-3"
        elif 'gemma' in tag_lower:
            return "Gemma"
        elif 'yi' in tag_lower:
            return "Yi"
    
    # Check model ID if tags don't match
    if 'llama-3' in model_id or 'llama3' in model_id:
        return "Llama 3"
    elif 'llama-2' in model_id or 'llama2' in model_id:
        return "Llama 2"
    elif 'llama' in model_id:
        return "Llama"
    elif 'mistral' in model_id:
        return "Mistral"
    elif 'mixtral' in model_id:
        return "Mixtral"
    elif 'qwen2.5' in model_id or 'qwen-2.5' in model_id:
        return "Qwen 2.5"
    elif 'qwen2' in model_id or 'qwen-2' in model_id:
        return "Qwen 2"
    elif 'qwen' in model_id:
        return "Qwen"
    elif 'phi-3' in model_id or 'phi3' in model_id:
        return "Phi-3"
    elif 'gemma' in model_id:
        return "Gemma"
    elif 'yi-' in model_id or 'yi_' in model_id:
        return "Yi"
    
    return "Unknown"


def extract_size_info(filename: str) -> Dict[str, Any]:
    """Extract quantization and size information from GGUF filename.
    
    Args:
        filename: GGUF filename (e.g., "llama-2-7b-chat.Q4_K_M.gguf")
        
    Returns:
        Dictionary with quantization info
    """
    filename_lower = filename.lower()
    
    # Common quantization patterns
    quantizations = {
        'q2_k': 'Q2_K',
        'q3_k_s': 'Q3_K_S',
        'q3_k_m': 'Q3_K_M',
        'q3_k_l': 'Q3_K_L',
        'q4_0': 'Q4_0',
        'q4_1': 'Q4_1',
        'q4_k_s': 'Q4_K_S',
        'q4_k_m': 'Q4_K_M',
        'q5_0': 'Q5_0',
        'q5_1': 'Q5_1',
        'q5_k_s': 'Q5_K_S',
        'q5_k_m': 'Q5_K_M',
        'q6_k': 'Q6_K',
        'q8_0': 'Q8_0',
        'f16': 'F16',
        'f32': 'F32',
    }
    
    quantization = None
    for pattern, name in quantizations.items():
        if pattern in filename_lower:
            quantization = name
            break
    
    return {
        "quantization": quantization,
        "filename": filename
    }

