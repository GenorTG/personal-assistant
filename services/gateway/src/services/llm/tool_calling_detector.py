"""Utility to detect tool calling support from model metadata."""
import logging
import re
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple

from huggingface_hub import HfApi

logger = logging.getLogger(__name__)


def detect_tool_calling_from_chat_template(chat_template: str) -> Tuple[bool, Optional[str]]:
    """Detect tool calling support from chat template string.
    
    Analyzes the chat template for patterns that indicate tool calling support.
    
    Args:
        chat_template: The chat template string from GGUF metadata
        
    Returns:
        Tuple of (supports_tool_calling, detected_format)
        - supports_tool_calling: True if template indicates tool calling support
        - detected_format: Suggested chat_format name (e.g., "functionary-v2", "chatml-function-calling") or None
    """
    if not chat_template:
        return False, None
    
    template_lower = chat_template.lower()
    
    # Check for functionary patterns
    # Functionary templates typically contain "function" or "tool" references
    functionary_patterns = [
        r"function",
        r"tool",
        r"function_call",
        r"tool_call",
        r"functionary",
    ]
    
    has_functionary_patterns = any(
        re.search(pattern, template_lower) for pattern in functionary_patterns
    )
    
    # Check for chatml-function-calling patterns
    # This format uses specific markers for tool calls
    chatml_function_patterns = [
        r"tool_use",
        r"tool_result",
        r"function",
        r"tool.*call",
    ]
    
    has_chatml_function_patterns = any(
        re.search(pattern, template_lower) for pattern in chatml_function_patterns
    )
    
    # Check for OpenAI-style function calling patterns
    # These templates reference "tools" or "function" in the message format
    openai_patterns = [
        r"tools.*function",
        r"function.*name",
        r"tool_calls",
        r"tool_choice",
    ]
    
    has_openai_patterns = any(
        re.search(pattern, template_lower) for pattern in openai_patterns
    )
    
    # Determine format and support
    if has_functionary_patterns:
        # Try to determine functionary version
        if "functionary" in template_lower and ("v2" in template_lower or "version.*2" in template_lower):
            return True, "functionary-v2"
        elif "functionary" in template_lower:
            return True, "functionary-v1"
        else:
            # Generic functionary-like pattern
            return True, "functionary-v2"  # Default to v2
    
    elif has_chatml_function_patterns:
        return True, "chatml-function-calling"
    
    elif has_openai_patterns:
        # OpenAI-compatible tool calling
        return True, None  # Let llama-cpp-python auto-detect from template
    
    # Check for common tool calling indicators in Jinja2 templates
    # Look for conditional blocks that handle tools/functions
    jinja_tool_patterns = [
        r"{%\s*if.*tool",
        r"{%\s*if.*function",
        r"{%\s*for.*tool",
        r"tool_calls",
        r"functions",
    ]
    
    has_jinja_tool_patterns = any(
        re.search(pattern, template_lower) for pattern in jinja_tool_patterns
    )
    
    if has_jinja_tool_patterns:
        # Likely supports tool calling but format unknown
        return True, None
    
    return False, None


@lru_cache(maxsize=128)
def _fetch_hf_metadata(repo_id: str) -> Tuple[List[str], Optional[str]]:
    """Fetch tags and primary architecture from HuggingFace for stronger assurance.
    
    Returns:
        (tags, architecture) where tags is a list of strings and architecture is optional.
    """
    try:
        api = HfApi()
        info = api.model_info(repo_id, timeout=5)
        tags = list(getattr(info, "tags", []) or [])
        architecture = None
        try:
            cfg = getattr(info, "config", None) or {}
            architectures = cfg.get("architectures") or []
            if architectures:
                architecture = architectures[0]
        except Exception:
            pass
        return tags, architecture
    except Exception as e:
        logger.debug("HF metadata fetch failed for %s: %s", repo_id, e)
        return [], None


def detect_tool_calling_from_metadata(
    model_id: str,
    model_name: str = None,
    architecture: str = None,
    tags: List[str] = None,
    repo_id: Optional[str] = None,
    remote_fetch: bool = False,
    chat_template: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Detect if a model supports tool calling (function calling) from metadata.
    
    Args:
        model_id: Full model ID (e.g., "TheBloke/Llama-3.1-8B-Instruct-GGUF")
        model_name: Model name (extracted from model_id if not provided)
        architecture: Model architecture (e.g., "LlamaForCausalLM")
        tags: List of model tags from HuggingFace
        repo_id: Optional HuggingFace repo id to fetch authoritative metadata
        remote_fetch: If True, attempt to fetch model_info from HuggingFace for assurance
        chat_template: Optional chat template string from GGUF metadata
        
    Returns:
        Tuple of (supports_tool_calling, suggested_chat_format)
        - supports_tool_calling: True if model supports tool calling
        - suggested_chat_format: Recommended chat_format (e.g., "functionary-v2") or None
    """
    # Use model_id if model_name not provided
    if not model_name:
        model_name = model_id.split("/")[-1] if "/" in model_id else model_id
    
    model_name_lower = model_name.lower()
    model_id_lower = model_id.lower()
    
    remote_tags: List[str] = []
    remote_arch = None
    if remote_fetch and repo_id:
        remote_tags, remote_arch = _fetch_hf_metadata(repo_id)
    
    # Merge tags (remote first for authoritative data)
    combined_tags = list(remote_tags or []) + list(tags or [])
    tags_lower = [tag.lower() if isinstance(tag, str) else str(tag).lower() for tag in combined_tags]
    
    # Prefer remote architecture if available
    architecture_lower = (remote_arch or architecture or "").lower()
    
    # PRIMARY METHOD: Check chat template from GGUF metadata
    if chat_template:
        supports, suggested_format = detect_tool_calling_from_chat_template(chat_template)
        if supports:
            logger.debug(f"Detected tool calling support from chat template. Suggested format: {suggested_format}")
            return True, suggested_format
    
    # SECONDARY METHOD: Check for explicit tool calling tags
    tool_calling_tags = [
        "function-calling", "function_calling", "functioncalling",
        "tool-use", "tool_use", "tooluse",
        "tools", "tool-calling", "tool_calling"
    ]
    if any(tag in tags_lower for tag in tool_calling_tags):
        logger.debug("Detected tool calling support from HuggingFace tags")
        return True, None  # Format unknown from tags alone
    
    # Models that support function calling:
    # - Llama 3.1+ (llama-3.1, llama3.1)
    # - Llama 3.2+ (llama-3.2, llama3.2)
    # - Mistral 7B v0.2+ and newer
    # - Mixtral 8x7B and newer
    # - Qwen 2.5+ (qwen2.5)
    # - Qwen 2+ (qwen2)
    # - Phi-3.5+
    # - Gemma 2+
    # - DeepSeek models
    # - Yi models (newer versions)
    
    supports = False
    
    # Check for Llama models
    if "llama" in architecture_lower or "llama" in model_name_lower or "llama" in model_id_lower:
        if any(x in model_name_lower or x in model_id_lower for x in ["3.1", "3.2", "llama-3.1", "llama-3.2", "llama3.1", "llama3.2"]):
            supports = True
        elif "3.0" in model_name_lower or "llama-3" in model_name_lower or "llama3" in model_name_lower:
            supports = True
        else:
            supports = False
    
    # Check for Mistral models
    elif "mistral" in architecture_lower or "mistral" in model_name_lower or "mistral" in model_id_lower:
        if any(x in model_name_lower or x in model_id_lower for x in ["v0.2", "v0.3", "0.2", "0.3"]):
            supports = True
        elif "mistral-7b" not in model_name_lower or "v0.1" not in model_name_lower:
            supports = True
        else:
            supports = False
    
    # Check for Mixtral models
    elif "mixtral" in architecture_lower or "mixtral" in model_name_lower or "mixtral" in model_id_lower:
        supports = True
    
    # Check for Qwen models
    elif "qwen" in architecture_lower or "qwen" in model_name_lower or "qwen" in model_id_lower:
        if any(x in model_name_lower or x in model_id_lower for x in ["2.5", "2-", "qwen2"]):
            supports = True
        else:
            supports = False
    
    # Check for Phi models
    elif "phi" in architecture_lower or "phi" in model_name_lower or "phi" in model_id_lower:
        if "3.5" in model_name_lower or "phi-3.5" in model_name_lower:
            supports = True
        else:
            supports = False
    
    # Check for Gemma models
    elif "gemma" in architecture_lower or "gemma" in model_name_lower or "gemma" in model_id_lower:
        if "2" in model_name_lower or "gemma-2" in model_name_lower:
            supports = True
        else:
            supports = False
    
    # Check for DeepSeek models
    elif "deepseek" in architecture_lower or "deepseek" in model_name_lower or "deepseek" in model_id_lower:
        supports = True
    
    # Check for Yi models
    elif "yi" in architecture_lower or "yi" in model_name_lower or "yi" in model_id_lower:
        supports = True
    
    else:
        supports = False
    
    # Return tuple with format suggestion (None if pattern matching used)
    suggested_format = None
    if supports:
        # Try to infer format from model name/architecture
        if "functionary" in model_name_lower or "functionary" in model_id_lower:
            suggested_format = "functionary-v2"
        elif "chatml" in model_name_lower or "chatml" in model_id_lower:
            suggested_format = "chatml-function-calling"
    
    return supports, suggested_format

