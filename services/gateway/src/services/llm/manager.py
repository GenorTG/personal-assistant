"""LLM model manager for OpenAI-compatible server management."""
# Standard library
import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

# Third-party
import httpx

# Local
from .downloader import ModelDownloader
from .sampler import SamplerSettings
from .server_manager import LLMServerManager
from ...config.settings import settings

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages OpenAI-compatible LLM server and model loading.
    
    This manager handles the lifecycle of the llama-cpp-python OpenAI-compatible server,
    including starting with appropriate parameters, stopping, and
    tracking the current model state.
    """
    
    def __init__(self, tool_registry: Optional[Any] = None):
        self.server_manager = LLMServerManager()
        self.downloader = ModelDownloader()
        self.current_model_name: Optional[str] = None
        self._current_model_path: Optional[str] = None  # Track current model path
        
        # Settings (kept for compatibility with existing code that reads these)
        self.sampler_settings = SamplerSettings(
            temperature=settings.temperature,
            top_p=settings.top_p,
            top_k=settings.top_k,
            repeat_penalty=settings.repeat_penalty,
            max_tokens=settings.llm_context_size // 4
        )
        # Tool calling sampler settings (more deterministic for precise tool calls)
        self.tool_calling_sampler_settings = SamplerSettings(
            temperature=0.3,  # Lower temperature for more deterministic tool calls
            top_p=0.8,  # Slightly lower top_p
            top_k=20,  # Lower top_k for more focused sampling
            repeat_penalty=settings.repeat_penalty,  # Keep same repeat penalty
            max_tokens=settings.llm_context_size // 4  # Same max tokens
        )
        self.system_prompt = settings.default_system_prompt
        self.character_card = None
        self.user_profile = None
        self.tool_registry = tool_registry
        self._memory_store = None  # Will be set during initialization
        self.supports_tool_calling: bool = False  # Auto-detected when model loads
        self._suggested_chat_format: Optional[str] = None  # Suggested chat_format from detection
    
    def _detect_tool_calling_support(self, model_path: str) -> bool:
        """Detect if the loaded model supports tool calling (function calling).
        
        Uses GGUF chat template as primary method, falls back to pattern matching.
        After server starts, can use verified template info from /props endpoint.
        
        Args:
            model_path: Path to the model file
            
        Returns:
            True if model supports tool calling, False otherwise
        """
        from pathlib import Path
        from .model_info import ModelInfoExtractor
        from .tool_calling_detector import detect_tool_calling_from_metadata
        
        model_file = Path(model_path)
        model_name = model_file.name
        
        logger.info(f"[TOOL CALLING DETECTION] Checking model: {model_path}")
        logger.info(f"[TOOL CALLING DETECTION] Model filename: {model_name}")
        
        # First, check if we have verified template info from /props (after server started)
        template_info = self.server_manager.get_template_info()
        if template_info and template_info.get("has_tool_use_template"):
            logger.info(f"[TOOL CALLING DETECTION] Using verified template info from /props: tool-use template available")
            self._suggested_chat_format = None  # Let server use embedded template
            return True
        
        # Extract model info (includes chat_template from GGUF if available)
        # Use use_cache=False to ensure we get fresh data with chat_template
        # (in case cache was created before chat_template extraction was added)
        info_extractor = ModelInfoExtractor(model_file.parent)
        model_info = info_extractor.extract_info(model_file.name, use_cache=False)
        architecture = model_info.get("architecture", "Unknown")
        chat_template = model_info.get("chat_template")
        
        logger.info(f"[TOOL CALLING DETECTION] Architecture: {architecture}")
        if chat_template:
            logger.info(f"[TOOL CALLING DETECTION] Found chat template in GGUF metadata (length: {len(chat_template)} chars)")
        else:
            logger.info(f"[TOOL CALLING DETECTION] No chat template found in GGUF metadata - will use pattern matching")
        
        # Use the improved detection function that checks chat template first
        # Get repo_id from metadata if available
        repo_id = None
        metadata_file = model_file.parent / "model_info.json" if model_file.is_file() else model_file.parent.parent / "model_info.json"
        if metadata_file.exists():
            try:
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    repo_id = metadata.get("repo_id")
            except Exception as e:
                logger.debug(f"Could not read metadata file for repo_id: {e}")
        
        # Call the detection function with chat template
        supports, suggested_format = detect_tool_calling_from_metadata(
            model_id=str(model_path),
            model_name=model_name,
            architecture=architecture,
            tags=[],  # Could fetch from HF if needed
            repo_id=repo_id,
            remote_fetch=False,  # Don't fetch remotely by default (can be slow)
            chat_template=chat_template
        )
        
        # Store suggested format for server configuration
        self._suggested_chat_format = suggested_format
        
        detection_method = "chat template" if chat_template else "pattern matching"
        logger.info(f"[TOOL CALLING DETECTION] Detection method: {detection_method}")
        if suggested_format:
            logger.info(f"[TOOL CALLING DETECTION] Suggested chat_format: {suggested_format}")
        logger.info(f"[TOOL CALLING DETECTION] Final result for {model_path}: supports_tool_calling={supports}")
        
        return supports
    
    def get_suggested_chat_format(self) -> Optional[str]:
        """Get the suggested chat_format for the current model.
        
        Returns:
            Suggested chat_format string (e.g., "functionary-v2", "chatml-function-calling") or None
        """
        return self._suggested_chat_format
    
    async def _verify_tool_calling_support(self) -> bool:
        """Verify tool calling support by making a test request.
        
        Makes a simple tool call request to verify the model actually responds with tool calls.
        
        Returns:
            True if model responds with tool calls, False otherwise
        """
        if not self.server_manager.is_running():
            logger.warning("[TOOL CALLING VERIFICATION] Server not running, skipping verification")
            return False
        
        try:
            logger.info("[TOOL CALLING VERIFICATION] Making test tool call request...")
            
            # Create a simple test tool
            test_tool = {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "format": {
                                "type": "string",
                                "description": "Time format (e.g., 'iso', 'unix')"
                            }
                        }
                    }
                }
            }
            
            # Make a test request asking for time
            # Use better prompts that encourage tool use
            # Check if this is Qwen model for Qwen-specific prompting
            is_qwen = "qwen" in (self.current_model_name or "").lower()
            
            if is_qwen:
                # Qwen-specific prompt that encourages tool use
                test_messages = [
                    {
                        "role": "system",
                        "content": "You are Qwen, a helpful assistant created by Alibaba Cloud. When asked to use a tool, you must call it using the proper format."
                    },
                    {
                        "role": "user",
                        "content": "What is the current time? You MUST use the get_current_time tool to check. Call the tool now."
                    }
                ]
            else:
                # Generic prompt for other models
                test_messages = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant with access to tools. When asked to use a tool, you must call it."
                    },
                    {
                        "role": "user",
                        "content": "What is the current time? You must use the get_current_time tool to check."
                    }
                ]
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.server_manager.server_url}/v1/chat/completions",
                    json={
                        "model": self.current_model_name or "default",
                        "messages": test_messages,
                        "tools": [test_tool],
                        "tool_choice": "auto",
                        "max_tokens": 100
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    choices = result.get("choices", [])
                    if choices:
                        message = choices[0].get("message", {})
                        tool_calls = message.get("tool_calls")
                        
                        if tool_calls and len(tool_calls) > 0:
                            logger.info(f"[TOOL CALLING VERIFICATION] SUCCESS - Model made {len(tool_calls)} tool call(s)")
                            return True
                        else:
                            logger.warning("[TOOL CALLING VERIFICATION] FAILED - Model did not make tool calls")
                            logger.debug(f"[TOOL CALLING VERIFICATION] Response: {result}")
                            return False
                    else:
                        logger.warning("[TOOL CALLING VERIFICATION] FAILED - No choices in response")
                        return False
                else:
                    logger.warning(f"[TOOL CALLING VERIFICATION] FAILED - Server returned status {response.status_code}")
                    logger.debug(f"[TOOL CALLING VERIFICATION] Response: {response.text}")
                    return False
                    
        except Exception as e:
            logger.warning(f"[TOOL CALLING VERIFICATION] Error during verification: {e}", exc_info=True)
            # Don't fail model load if verification fails - just log warning
            return False
    
    async def load_settings_from_file_stores(self, memory_store):
        """Load settings from file stores into memory.
        
        Args:
            memory_store: MemoryStore instance to load from
        """
        self._memory_store = memory_store
        
        try:
            # Load system prompt
            system_prompt_data = await memory_store.get_system_prompt()
            if system_prompt_data and system_prompt_data.get("content"):
                self.system_prompt = system_prompt_data["content"]
            
            # Load character card
            character_card = await memory_store.get_character_card()
            if character_card:
                from ...api.schemas import CharacterCard
                self.character_card = CharacterCard(**character_card)
            
            # Load user profile
            user_profile = await memory_store.get_user_profile()
            if user_profile:
                from ...api.schemas import UserProfile
                self.user_profile = UserProfile(**user_profile)
            
            # Load sampler settings
            sampler_settings = await memory_store.get_sampler_settings()
            if sampler_settings:
                if "temperature" in sampler_settings:
                    self.sampler_settings.temperature = float(sampler_settings["temperature"])
                if "top_p" in sampler_settings:
                    self.sampler_settings.top_p = float(sampler_settings["top_p"])
                if "top_k" in sampler_settings:
                    self.sampler_settings.top_k = int(sampler_settings["top_k"])
                if "repeat_penalty" in sampler_settings:
                    self.sampler_settings.repeat_penalty = float(sampler_settings["repeat_penalty"])
                if "max_tokens" in sampler_settings:
                    self.sampler_settings.max_tokens = int(sampler_settings["max_tokens"])
                
                # DRY (Dynamic Repetition Penalty) settings
                if "dry_multiplier" in sampler_settings:
                    self.sampler_settings.dry_multiplier = float(sampler_settings["dry_multiplier"])
                if "dry_base" in sampler_settings:
                    self.sampler_settings.dry_base = float(sampler_settings["dry_base"])
                if "dry_allowed_length" in sampler_settings:
                    self.sampler_settings.dry_allowed_length = int(sampler_settings["dry_allowed_length"])
            
            logger.info("Loaded settings from file stores")
        except Exception as e:
            logger.error(f"Error loading settings from file stores: {e}")
    
    def set_tool_registry(self, tool_registry: Any) -> None:
        """Set the tool registry for function calling."""
        self.tool_registry = tool_registry
        logger.info("Tool registry set for LLM Manager")
    
    async def load_model(
        self, 
        model_path: str,
        # Core parameters
        n_ctx: Optional[int] = None,
        n_batch: Optional[int] = None,
        n_threads: Optional[int] = None,
        n_threads_batch: Optional[int] = None,
        # GPU settings
        n_gpu_layers: Optional[int] = None,
        main_gpu: int = 0,
        tensor_split: Optional[List[float]] = None,
        # Memory settings
        use_mmap: Optional[bool] = None,
        use_mlock: Optional[bool] = None,
        # Performance settings
        flash_attn: bool = False,
        # RoPE settings
        rope_freq_base: Optional[float] = None,
        rope_freq_scale: Optional[float] = None,
        rope_scaling_type: Optional[int] = None,
        yarn_ext_factor: Optional[float] = None,
        yarn_attn_factor: Optional[float] = None,
        yarn_beta_fast: Optional[float] = None,
        yarn_beta_slow: Optional[float] = None,
        yarn_orig_ctx: Optional[int] = None,
        # KV cache settings
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None,
        use_flash_attention: Optional[bool] = None,
        offload_kqv: Optional[bool] = None,
        **kwargs  # Catch any unknown parameters
    ) -> bool:
        """Load a model via the server.
        
        Args:
            model_path: Path to GGUF model file
            n_ctx: Context window size (default: settings.llm_context_size)
            n_batch: Batch size for prompt processing (default: 512)
            n_threads: Number of CPU threads (default: settings.llm_n_threads)
            n_threads_batch: Threads for batch processing
            n_gpu_layers: GPU layers (-1=all, 0=CPU only)
            main_gpu: Main GPU device ID
            tensor_split: GPU split ratios
            use_mmap: Memory-mapped loading (default: True)
            use_mlock: Lock model in RAM (default: False)
            flash_attn: Enable Flash Attention
            rope_freq_base/scale: RoPE context extension
            rope_scaling_type: RoPE scaling type
            yarn_*: YaRN context extension parameters
            cache_type_k/v: KV cache data types
            # n_cpu_moe removed - not a valid parameter for OpenAI-compatible server
            
        Returns:
            True if model loaded successfully
        """
        # Handle deprecated parameter
        if use_flash_attention is not None and not flash_attn:
            logger.warning("use_flash_attention is deprecated, use flash_attn instead")
            flash_attn = use_flash_attention
            
        if offload_kqv is not None:
            logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
        
        # n_cpu_moe is not a valid parameter - ignore if provided for backwards compatibility
        if 'n_cpu_moe' in kwargs:
            logger.warning("n_cpu_moe is not a valid parameter for OpenAI-compatible server, ignoring")
            kwargs.pop('n_cpu_moe')
            
        if kwargs:
            logger.warning("Unknown parameters ignored: %s", list(kwargs.keys()))
        
        try:
            # Extract model info for optimization and MoE detection
            from .model_info import ModelInfoExtractor
            
            model_file = Path(model_path)
            info_extractor = ModelInfoExtractor(model_file.parent)
            model_info = info_extractor.extract_info(model_file.name, use_cache=True)
            
            # Use provided options or defaults
            # Treat 0 as "use model defaults" (None) - don't pass the parameter
            effective_n_ctx = n_ctx or settings.llm_context_size
            # If n_threads is 0, pass None to use model defaults; otherwise use provided value or settings default
            effective_n_threads = None if (n_threads is not None and n_threads == 0) else (n_threads or settings.llm_n_threads)
            # Detect GPU layers if not provided
            if n_gpu_layers is not None:
                effective_n_gpu_layers = n_gpu_layers
            else:
                # Auto-detect GPU layers
                try:
                    from llama_cpp import llama_cpp
                    has_cuda = hasattr(llama_cpp, 'llama_supports_gpu_offload') or hasattr(llama_cpp, 'llama_gpu_offload')
                    effective_n_gpu_layers = -1 if has_cuda else 0
                except ImportError:
                    effective_n_gpu_layers = 0
            # If n_batch is 0, pass None to use model defaults; otherwise use provided value or None (model default)
            effective_n_batch = None if (n_batch is not None and n_batch == 0) else n_batch
            effective_use_mmap = use_mmap if use_mmap is not None else True
            effective_use_mlock = use_mlock if use_mlock is not None else False
            
            logger.info("=" * 60)
            logger.info("LOADING MODEL")
            logger.info("=" * 60)
            logger.info("Model: %s", model_path)
            logger.info("Architecture: %s | Parameters: %s", 
                       model_info.get("architecture", "Unknown"),
                       model_info.get("parameters", "Unknown"))
            logger.info("Context: %d | Batch: %s | Threads: %d", 
                       effective_n_ctx, effective_n_batch if effective_n_batch is not None else "default", effective_n_threads)
            logger.info("GPU Layers: %d | Flash Attention: %s", 
                       effective_n_gpu_layers, flash_attn)
            if cache_type_k or cache_type_v:
                logger.info("KV Cache: K=%s V=%s", 
                           cache_type_k or "f16", cache_type_v or "f16")
            logger.info("=" * 60)
            
            # Start OpenAI-compatible server with model
            try:
                # Unload existing model if loaded
                if self.current_model_name:
                    await self.unload_model()
                
                # Extract and save chat template if available (for potential use with --chat-template-file)
                from .model_info import ModelInfoExtractor
                info_extractor = ModelInfoExtractor(Path(model_path).parent)
                template_file_path = None
                try:
                    template_file_path = info_extractor.extract_and_save_template(
                        Path(model_path).name,
                        force=False  # Don't overwrite existing
                    )
                    if template_file_path:
                        logger.info(f"[MODEL LOAD] Chat template saved to: {template_file_path}")
                except Exception as e:
                    logger.warning(f"[MODEL LOAD] Could not extract/save template: {e}")
                
                # Detect tool calling support BEFORE starting server (needed for chat_format)
                try:
                    self.supports_tool_calling = self._detect_tool_calling_support(model_path)
                    suggested_chat_format = self.get_suggested_chat_format()
                    logger.info(f"[MODEL LOAD] Tool calling support: {'ENABLED' if self.supports_tool_calling else 'DISABLED'} for model {model_path}")
                    logger.info(f"[MODEL LOAD] Suggested chat format: {suggested_chat_format}")
                except Exception as e:
                    logger.error(f"[MODEL LOAD] Error during tool calling detection: {e}", exc_info=True)
                    # Fallback: enable for known tool-calling models
                    architecture = model_info.get("architecture", "").lower()
                    model_name_lower = Path(model_path).name.lower()
                    if ("llama" in architecture or "llama" in model_name_lower) and ("3.2" in model_name_lower or "3_2" in model_name_lower or "3.1" in model_name_lower or "3_1" in model_name_lower):
                        logger.warning(f"[MODEL LOAD] Detection failed but model is Llama 3.1/3.2 - forcing tool calling enabled")
                        self.supports_tool_calling = True
                        self._suggested_chat_format = None
                    else:
                        self.supports_tool_calling = False
                        self._suggested_chat_format = None
                
                # For Qwen and Llama models, explicitly ensure tool calling is enabled
                # This runs REGARDLESS of detection result to handle edge cases
                architecture = model_info.get("architecture", "").lower()
                model_name_lower = Path(model_path).name.lower()
                
                # Check if this is a known tool-calling model
                is_llama_32 = ("3.2" in model_name_lower or "3_2" in model_name_lower or "3-2" in model_name_lower)
                is_llama_31 = ("3.1" in model_name_lower or "3_1" in model_name_lower or "3-1" in model_name_lower)
                is_llama = ("llama" in architecture or "llama" in model_name_lower)
                is_qwen = ("qwen" in architecture or "qwen" in model_name_lower)
                
                # Force enable for Llama 3.1/3.2 models (they support tool calling natively)
                if is_llama and (is_llama_32 or is_llama_31):
                    logger.info(f"[LLAMA FORCE] Model is Llama 3.1/3.2 - FORCING tool calling enabled")
                    logger.info(f"[LLAMA FORCE] Architecture: {architecture}, Model: {model_name_lower}")
                    self.supports_tool_calling = True
                    logger.info(f"[LLAMA FORCE] Tool calling set to: {self.supports_tool_calling}")
                elif is_qwen and self.supports_tool_calling:
                    logger.info(f"[QWEN] Tool calling explicitly enabled for Qwen model - will not be disabled by verification")
                
                # Only use chat_format if we have a way to get the tokenizer
                # Some chat formats (like functionary-v2) require a tokenizer path, which GGUF repos don't have
                # For GGUF models, tokenizer is embedded, so we skip chat_format that requires external tokenizer
                hf_pretrained_model_name_or_path = None
                final_chat_format = None
                
                # For GGUF models, prioritize tool-calling chat formats if tool calling is detected
                # If tool calling is supported, use a format that enables it
                # Otherwise, use standard formats that work with embedded tokenizer
                architecture = model_info.get("architecture", "").lower()
                model_name_lower = Path(model_path).name.lower()
                
                # For Llama 3.x models, use 'llama-3' format
                # NOTE: llama-cpp-python only supports 'llama-3', NOT 'llama-3.1' or 'llama-3.2'
                if "llama" in architecture or "llama" in model_name_lower:
                    if self.supports_tool_calling:
                        # All Llama 3.x models (3.0, 3.1, 3.2) use 'llama-3' format
                        # CRITICAL: Must use 'llama-3', NOT 'llama-3.2' or 'llama-3.1'
                        if "3" in model_name_lower or "3.2" in model_name_lower or "3_2" in model_name_lower or "3.1" in model_name_lower or "3_1" in model_name_lower:
                            logger.info(f"[LLAMA 3.x] Tool calling detected - using 'llama-3' format (supports tool calling)")
                            final_chat_format = "llama-3"  # EXPLICITLY set to 'llama-3', never 'llama-3.2'
                        else:
                            # Llama 2 or older
                            final_chat_format = "llama-2"
                    else:
                        # No tool calling - still use appropriate format
                        if "3" in model_name_lower or "3.2" in model_name_lower or "3_2" in model_name_lower or "3.1" in model_name_lower or "3_1" in model_name_lower:
                            final_chat_format = "llama-3"  # EXPLICITLY set to 'llama-3', never 'llama-3.2'
                        else:
                            final_chat_format = "llama-2"
                # For Qwen models with tool calling, use qwen format
                elif "qwen" in architecture or "qwen" in model_name_lower:
                    if self.supports_tool_calling:
                        logger.info(f"[QWEN] Tool calling detected - using 'chatml-function-calling' format for function calling")
                        final_chat_format = "chatml-function-calling"
                    else:
                        logger.info(f"[QWEN] No tool calling detected - using 'qwen' chat format")
                        final_chat_format = "qwen"
                # For other models, check for tool-calling formats (but avoid functionary-v2 which needs external tokenizer)
                elif self.supports_tool_calling:
                    # If we have a suggested format, use it; otherwise use chatml with jinja
                    suggested_format = self.get_suggested_chat_format()
                    if suggested_format:
                        logger.info(f"[MODEL LOAD] Tool calling detected - using suggested format: {suggested_format}")
                        final_chat_format = suggested_format
                    else:
                        # Default to chatml when tool calling is detected but no specific format suggested
                        logger.info(f"[MODEL LOAD] Tool calling detected but no specific format - defaulting to chatml (will use jinja)")
                        final_chat_format = "chatml"
                # Set standard format if not already set
                else:
                    if "mistral" in architecture or "mistral" in model_name_lower:
                        final_chat_format = "mistral"
                    else:
                        # Always default to chatml when no detection is given
                        logger.info(f"[MODEL LOAD] No specific format detected - defaulting to chatml")
                        final_chat_format = "chatml"
                
                # CRITICAL: Ensure we never pass 'llama-3.2' or 'llama-3.1' - only 'llama-3'
                if final_chat_format and ("llama-3.2" in str(final_chat_format) or "llama-3.1" in str(final_chat_format)):
                    logger.error(f"[CRITICAL FIX] Detected invalid chat_format '{final_chat_format}' - forcing to 'llama-3'")
                    final_chat_format = "llama-3"
                
                logger.info(f"[MODEL LOAD] Using chat format: {final_chat_format}")
                logger.info(f"[MODEL LOAD] Embedded tokenizer will be used (no external tokenizer needed)")
                logger.info(f"[MODEL LOAD] Tool calling support: {'ENABLED' if self.supports_tool_calling else 'DISABLED'}")
                
                # Determine if we should use jinja flag and template file
                # chatml-function-calling format handles tool calling automatically - no jinja/template needed
                use_jinja = False
                chat_template_file_param = None
                
                if final_chat_format == "chatml-function-calling":
                    # chatml-function-calling format handles tool calling automatically
                    # No need for jinja flag or template files
                    logger.info("[MODEL LOAD] Using chatml-function-calling format - tool calling enabled automatically")
                elif self.supports_tool_calling:
                    # For other formats that support tool calling, use jinja/template if available
                    use_jinja = True
                    if template_file_path and template_file_path.exists():
                        # Check if we have a fixed template (backup exists means we fixed it)
                        backup_path = template_file_path.with_suffix('.jinja.backup')
                        if backup_path.exists():
                            # We have a fixed template - use it!
                            chat_template_file_param = str(template_file_path)
                            logger.info(f"[MODEL LOAD] Using FIXED template file for tool calling: {chat_template_file_param}")
                        elif final_chat_format not in ["llama-3", "qwen", "mistral"]:
                            # For generic formats, use template file even if not fixed
                            chat_template_file_param = str(template_file_path)
                            logger.info(f"[MODEL LOAD] Will use custom template file: {chat_template_file_param}")
                
                hf_pretrained_model_name_or_path = None
                
                # Store current chat format for system prompt building
                self.current_chat_format = final_chat_format
                
                # Start server with model
                logger.info(f"[LLM MANAGER] Starting server with chat_format: {final_chat_format}")
                logger.info(f"[LLM MANAGER] Template file: {chat_template_file_param}")
                server_start_time = time.time()
                server_started = await self.server_manager.start_server(
                    model_path=str(model_path),
                    n_ctx=effective_n_ctx,
                    n_threads=effective_n_threads,
                    n_gpu_layers=effective_n_gpu_layers,
                    n_batch=effective_n_batch,
                    use_mmap=effective_use_mmap,
                    use_mlock=effective_use_mlock,
                    flash_attn=flash_attn,
                    rope_freq_base=rope_freq_base,
                    rope_freq_scale=rope_freq_scale,
                    main_gpu=main_gpu,
                    tensor_split=tensor_split,
                    chat_format=final_chat_format,  # Only pass if we have one and it's safe to use
                    use_jinja=use_jinja,  # Enable jinja for function calling
                    chat_template_file=chat_template_file_param,  # Use template file if available
                    hf_pretrained_model_name_or_path=hf_pretrained_model_name_or_path  # Only pass if we have a valid base model repo
                )
                server_start_duration = time.time() - server_start_time
                
                if server_started:
                    self.current_model_name = Path(model_path).name
                    self._current_model_path = str(model_path)
                    logger.info(f"[LLM MANAGER] ✓ Server started successfully in {server_start_duration:.2f}s")
                    logger.info(f"[LLM MANAGER] Model: {self.current_model_name}")
                    
                    # Verify template support via /props if jinja was used
                    if use_jinja:
                        template_info = await self.server_manager._verify_template_support()
                        if template_info:
                            if template_info.get("has_tool_use_template"):
                                logger.info("✓ Verified: Tool-use template is available via /props")
                                # Update tool calling support based on verified info
                                if not self.supports_tool_calling:
                                    logger.info("  Updating tool calling support to True based on verified template")
                                    self.supports_tool_calling = True
                            else:
                                logger.warning("⚠ Template verification: Tool-use template not found in /props")
                    
                    # Broadcast model loaded event via WebSocket
                    try:
                        from ...services.websocket_manager import get_websocket_manager
                        from ...api.routes.system import _get_debug_info_internal
                        ws_manager = get_websocket_manager()
                        await ws_manager.broadcast_model_loaded(
                            model_id=str(model_path),
                            model_info={
                                "model_name": self.current_model_name,
                                "model_path": str(model_path),
                                "supports_tool_calling": self.supports_tool_calling,
                                "suggested_chat_format": self._suggested_chat_format,
                                "architecture": model_info.get("architecture"),
                                "parameters": model_info.get("parameters"),
                            }
                        )
                        # Also broadcast full debug info update for debug panel
                        debug_info = await _get_debug_info_internal()
                        await ws_manager.broadcast_debug_info_updated(debug_info)
                    except Exception as e:
                        logger.debug(f"Failed to broadcast model_loaded event: {e}")
                    
                    # Runtime verification: test tool calling if detected
                    # NOTE: Standard chat formats (llama-3.2, llama-3.1, etc.) DO support tool calling
                    # The verification might fail due to model behavior, not lack of support
                    # So we keep tool calling enabled even if verification fails, but log a warning
                    # For Qwen models, we NEVER disable tool calling even if verification fails
                    if self.supports_tool_calling:
                        # Check if this is Qwen (from earlier detection)
                        architecture = model_info.get("architecture", "").lower()
                        is_qwen = "qwen" in architecture
                        
                        if is_qwen:
                            logger.info(f"[QWEN] Skipping runtime verification - Qwen tool calling will remain enabled")
                            logger.info(f"[QWEN] Qwen models support tool calling via chat template - verification not needed")
                        else:
                            verified = await self._verify_tool_calling_support()
                            if not verified:
                                logger.warning(f"[TOOL CALLING] Runtime verification failed - model may not respond with tool calls")
                                logger.warning(f"[TOOL CALLING] Keeping tool calling enabled anyway - model may work with proper prompting")
                                logger.warning(f"[TOOL CALLING] Standard chat formats support tool calling - verification may be too strict")
                                # DON'T DISABLE - keep tool calling enabled to allow real user requests to try
                            else:
                                logger.info(f"[TOOL CALLING] Runtime verification passed - tool calling confirmed")
                    
                    return True
                else:
                    logger.error(f"[LLM MANAGER] ❌ Server failed to start after {server_start_duration:.2f}s")
                    last_error = getattr(self.server_manager, '_last_error', 'Unknown error')
                    logger.error(f"[LLM MANAGER] Error: {last_error}")
                    error_msg = self.server_manager.get_last_error() or "Failed to start model server"
                    raise RuntimeError(error_msg)
            except FileNotFoundError as e:
                logger.error("Model file not found: %s", e)
                return False
            except Exception as e:
                logger.error("Error starting model server: %s", e, exc_info=True)
                return False
            
        except Exception as e:
            logger.error("Failed to load model: %s", e, exc_info=True)
            return False
    
    def is_model_loaded(self) -> bool:
        """Check if model is loaded (server is running)."""
        return (
            self.server_manager.is_running() and
            self.current_model_name is not None and 
            self._current_model_path is not None
        )
    
    def get_current_model_path(self) -> Optional[str]:
        """Get the path of the currently loaded model."""
        return self._current_model_path
    
    def get_current_model(self) -> Optional[Any]:
        """Get the currently loaded model instance (deprecated - models are in server)."""
        # Models are now in the server, not in-process
        # This method is kept for compatibility but returns None
        return None
    
    async def unload_model(self) -> bool:
        """Stop the model server."""
        try:
            # Stop the server
            await self.server_manager.stop_server()
            
            model_id = self._current_model_path
            self.current_model_name = None
            self._current_model_path = None
            self.supports_tool_calling = False
            logger.info("Model server stopped successfully")
            
            # Broadcast model unloaded event via WebSocket
            try:
                from ...services.websocket_manager import get_websocket_manager
                ws_manager = get_websocket_manager()
                await ws_manager.broadcast_model_unloaded(model_id=model_id)
            except Exception as e:
                logger.debug(f"Failed to broadcast model_unloaded event: {e}")
            
            return True
        except Exception as e:
            logger.error("Error stopping model server: %s", e, exc_info=True)
            # Still clear state even if stop fails
            model_id = self._current_model_path
            self.current_model_name = None
            self._current_model_path = None
            self.supports_tool_calling = False
            
            # Broadcast model unloaded event via WebSocket
            try:
                from ...services.websocket_manager import get_websocket_manager
                from ...api.routes.system import _get_debug_info_internal
                ws_manager = get_websocket_manager()
                await ws_manager.broadcast_model_unloaded(model_id=model_id)
                # Also broadcast full debug info update for debug panel
                debug_info = await _get_debug_info_internal()
                await ws_manager.broadcast_debug_info_updated(debug_info)
            except Exception as e:
                logger.debug(f"Failed to broadcast model_unloaded event: {e}")
            
            return False

    def _validate_sampler_settings(self) -> None:
        """Validate and clamp sampler settings to safe ranges.
        
        Raises:
            ValueError: If settings are invalid
        """
        # Clamp temperature to valid range
        if not (0.0 <= self.sampler_settings.temperature <= 2.0):
            logger.warning("Temperature %f out of range [0.0, 2.0], clamping", self.sampler_settings.temperature)
            self.sampler_settings.temperature = max(0.0, min(2.0, self.sampler_settings.temperature))
        
        # Clamp top_p to valid range
        if not (0.0 <= self.sampler_settings.top_p <= 1.0):
            logger.warning("top_p %f out of range [0.0, 1.0], clamping", self.sampler_settings.top_p)
            self.sampler_settings.top_p = max(0.0, min(1.0, self.sampler_settings.top_p))
        
        # Clamp top_k to valid range
        if self.sampler_settings.top_k < 0:
            logger.warning("top_k %d is negative, setting to 0", self.sampler_settings.top_k)
            self.sampler_settings.top_k = 0
        
        # Clamp repeat_penalty to reasonable range
        if not (0.5 <= self.sampler_settings.repeat_penalty <= 2.0):
            logger.warning("repeat_penalty %f out of range [0.5, 2.0], clamping", self.sampler_settings.repeat_penalty)
            self.sampler_settings.repeat_penalty = max(0.5, min(2.0, self.sampler_settings.repeat_penalty))
        
        # Clamp max_tokens to reasonable range - ensure minimum of 10 to prevent immediate stopping
        if self.sampler_settings.max_tokens < 10:
            logger.warning("max_tokens %d is too low (minimum 10), setting to 10 to prevent empty responses", self.sampler_settings.max_tokens)
            self.sampler_settings.max_tokens = 10
        elif self.sampler_settings.max_tokens > 8192:
            logger.warning("max_tokens %d is very large, limiting to 8192", self.sampler_settings.max_tokens)
            self.sampler_settings.max_tokens = 8192
    
    def update_settings(self, settings_dict: Dict[str, Any]):
        """Update sampler settings with validation.
        
        Also updates tool-calling sampler settings proportionally to maintain
        the relationship (tool calling uses lower temperature for more deterministic calls).
        """
        if "temperature" in settings_dict:
            new_temp = float(settings_dict["temperature"])
            self.sampler_settings.temperature = new_temp
            # Update tool calling temperature proportionally (keep it lower)
            # If regular temp is 0.7, tool temp is 0.3 (ratio ~0.43)
            # If regular temp changes, maintain similar ratio but clamp to reasonable range
            tool_temp = max(0.1, min(0.5, new_temp * 0.43))
            self.tool_calling_sampler_settings.temperature = tool_temp
            logger.debug(f"Updated temperature: regular={new_temp}, tool_calling={tool_temp}")
        if "top_p" in settings_dict:
            new_top_p = float(settings_dict["top_p"])
            self.sampler_settings.top_p = new_top_p
            # Tool calling uses slightly lower top_p
            self.tool_calling_sampler_settings.top_p = max(0.5, min(0.9, new_top_p * 0.89))
        if "top_k" in settings_dict:
            new_top_k = int(settings_dict["top_k"])
            self.sampler_settings.top_k = new_top_k
            # Tool calling uses lower top_k for more focused sampling
            self.tool_calling_sampler_settings.top_k = max(10, min(40, int(new_top_k * 0.5)))
        if "repeat_penalty" in settings_dict:
            repeat_penalty = float(settings_dict["repeat_penalty"])
            self.sampler_settings.repeat_penalty = repeat_penalty
            self.tool_calling_sampler_settings.repeat_penalty = repeat_penalty
        if "max_tokens" in settings_dict:
            max_tokens = int(settings_dict["max_tokens"])
            self.sampler_settings.max_tokens = max_tokens
            self.tool_calling_sampler_settings.max_tokens = max_tokens
        if "stop" in settings_dict:
            # Stop strings can be a list or None
            stop_value = settings_dict["stop"]
            if stop_value is None:
                self.sampler_settings.stop = []
            elif isinstance(stop_value, list):
                self.sampler_settings.stop = [str(s) for s in stop_value]
            else:
                logger.warning(f"Invalid stop value type: {type(stop_value)}, expected list or None")
        
        # Smooth Sampling settings
        if "smoothing_factor" in settings_dict:
            self.sampler_settings.smoothing_factor = float(settings_dict["smoothing_factor"])
        if "smoothing_curve" in settings_dict:
            # smoothing_curve is a float (1.0+), not a string
            try:
                curve_value = float(settings_dict["smoothing_curve"])
                if curve_value >= 1.0:
                    self.sampler_settings.smoothing_curve = curve_value
                else:
                    logger.warning(f"Invalid smoothing_curve: {curve_value}, must be >= 1.0, using default 1.0")
            except (ValueError, TypeError):
                logger.warning(f"Invalid smoothing_curve value: {settings_dict['smoothing_curve']}, must be a float >= 1.0")
        
        # DRY (Dynamic Repetition Penalty) settings
        if "dry_multiplier" in settings_dict:
            self.sampler_settings.dry_multiplier = float(settings_dict["dry_multiplier"])
        if "dry_base" in settings_dict:
            self.sampler_settings.dry_base = float(settings_dict["dry_base"])
        if "dry_allowed_length" in settings_dict:
            self.sampler_settings.dry_allowed_length = int(settings_dict["dry_allowed_length"])
        
        # Validate after update
        self._validate_sampler_settings()
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current sampler settings."""
        result = {
            "temperature": self.sampler_settings.temperature,
            "top_p": self.sampler_settings.top_p,
            "top_k": self.sampler_settings.top_k,
            "repeat_penalty": self.sampler_settings.repeat_penalty,
            "max_tokens": self.sampler_settings.max_tokens,
            "dry_multiplier": self.sampler_settings.dry_multiplier,
            "dry_base": self.sampler_settings.dry_base,
            "dry_allowed_length": self.sampler_settings.dry_allowed_length
        }
        # Include stop strings if they exist
        if hasattr(self.sampler_settings, 'stop') and self.sampler_settings.stop:
            result["stop"] = self.sampler_settings.stop
        # Include smooth sampling settings
        if hasattr(self.sampler_settings, 'smoothing_factor'):
            result["smoothing_factor"] = self.sampler_settings.smoothing_factor
        if hasattr(self.sampler_settings, 'smoothing_curve'):
            result["smoothing_curve"] = self.sampler_settings.smoothing_curve
        return result
    
    def update_system_prompt(self, prompt: str):
        self.system_prompt = prompt
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    def get_character_card(self) -> Optional[Dict[str, Any]]:
        """Get current character card as dict."""
        if self.character_card:
            return self.character_card.model_dump() if hasattr(self.character_card, 'model_dump') else self.character_card.__dict__
        return None
    
    def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Get current user profile as dict."""
        if self.user_profile:
            return self.user_profile.model_dump() if hasattr(self.user_profile, 'model_dump') else self.user_profile.__dict__
        return None
        
    def update_character_card(self, character_card: Dict[str, Any]) -> None:
        from ...api.schemas import CharacterCard
        if character_card:
            self.character_card = CharacterCard(**character_card)
        else:
            self.character_card = None
            
    def update_user_profile(self, user_profile: Dict[str, Any]) -> None:
        from ...api.schemas import UserProfile
        if user_profile:
            self.user_profile = UserProfile(**user_profile)
        else:
            self.user_profile = None

    def _build_system_prompt(self) -> str:
        """Build system prompt from base prompt, character card, and user profile.
        
        Note: This is used for building the system message sent to the OpenAI-compatible server.
        The server handles prompt formatting internally.
        
        For chatml-function-calling format, uses the exact system message from official docs.
        """
        from datetime import datetime
        from ...utils.template_parser import parse_template_variables
        
        # Get current date and time - always include this so model can parse natural language dates
        current_datetime = datetime.now()
        current_date_str = current_datetime.strftime("%Y-%m-%d")
        current_time_str = current_datetime.strftime("%H:%M:%S")
        current_weekday = current_datetime.strftime("%A")
        current_datetime_iso = current_datetime.isoformat()
        
        # CRITICAL: For chatml-function-calling format, use the exact system message from official docs
        # This is required for function calling to work correctly
        if hasattr(self, 'current_chat_format') and self.current_chat_format == "chatml-function-calling":
            # Still include date/time even for chatml-function-calling format
            base_prompt = "A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. The assistant calls functions with appropriate input when necessary"
            return f"{base_prompt}\n\nCurrent Date and Time: {current_datetime_iso} ({current_weekday}, {current_date_str} at {current_time_str})"
        
        prompt_parts = []
        
        # Always add current date and time at the beginning
        prompt_parts.append("CURRENT DATE AND TIME:")
        prompt_parts.append(f"- ISO Format: {current_datetime_iso}")
        prompt_parts.append(f"- Human Readable: {current_weekday}, {current_date_str} at {current_time_str}")
        prompt_parts.append(f"- Use this as reference when parsing natural language dates like 'tomorrow', 'next week', 'friday at 2pm', etc.")
        prompt_parts.append("")
        
        # Extract names for template parsing
        user_name = None
        char_name = None
        
        if self.character_card:
            # Handle both dict and object types
            if isinstance(self.character_card, dict):
                char_name = self.character_card.get("name")
                personality = self.character_card.get("personality")
                background = self.character_card.get("background")
                instructions = self.character_card.get("instructions")
            else:
                # It's a CharacterCard object
                char_name = getattr(self.character_card, "name", None)
                personality = getattr(self.character_card, "personality", None)
                background = getattr(self.character_card, "background", None)
                instructions = getattr(self.character_card, "instructions", None)
            
            if char_name:
                prompt_parts.append(f"You are {char_name}.")
            if personality:
                # Parse template variables in personality
                personality = parse_template_variables(personality, user_name, char_name)
                prompt_parts.append(f"Personality: {personality}")
            if background:
                # Parse template variables in background
                background = parse_template_variables(background, user_name, char_name)
                prompt_parts.append(f"Background: {background}")
            if instructions:
                # Parse template variables in instructions
                instructions = parse_template_variables(instructions, user_name, char_name)
                prompt_parts.append(f"Instructions: {instructions}")
            prompt_parts.append("")
        
        if self.user_profile:
            # Handle both dict and object types
            if isinstance(self.user_profile, dict):
                user_name = self.user_profile.get("name")
                about = self.user_profile.get("about")
                preferences = self.user_profile.get("preferences")
            else:
                # It's a UserProfile object
                user_name = getattr(self.user_profile, "name", None)
                about = getattr(self.user_profile, "about", None)
                preferences = getattr(self.user_profile, "preferences", None)
            
            prompt_parts.append("About the user:")
            if user_name:
                prompt_parts.append(f"- Name: {user_name}")
            if about:
                # Parse template variables in about
                about = parse_template_variables(about, user_name, char_name)
                prompt_parts.append(f"- About: {about}")
            if preferences:
                # Parse template variables in preferences
                preferences = parse_template_variables(preferences, user_name, char_name)
                prompt_parts.append(f"- Preferences: {preferences}")
            prompt_parts.append("")
        
        # Parse template variables in system prompt
        system_prompt = parse_template_variables(self.system_prompt, user_name, char_name)
        prompt_parts.append(system_prompt)
        
        # Add comprehensive tool calling instructions if tools are available
        tool_source = getattr(self, 'tool_manager', None) or getattr(self, 'tool_registry', None)
        if tool_source and self.supports_tool_calling:
            prompt_parts.append("")
            prompt_parts.append("=" * 60)
            prompt_parts.append("TOOL USAGE INSTRUCTIONS")
            prompt_parts.append("=" * 60)
            prompt_parts.append("You have access to tools that can perform actions to help the user accomplish tasks.")
            prompt_parts.append("")
            prompt_parts.append("WHEN TO USE TOOLS:")
            prompt_parts.append("- When the user asks you to perform an action (create calendar events, search the web, etc.)")
            prompt_parts.append("- When the user asks for information that requires a tool to retrieve (calendar events, current time, etc.)")
            prompt_parts.append("- When a task cannot be completed with text alone and requires an external action")
            prompt_parts.append("")
            prompt_parts.append("HOW TO USE TOOLS - CRITICAL INSTRUCTIONS:")
            prompt_parts.append("1. ALWAYS extract ALL required parameters from the user's message")
            prompt_parts.append("2. Read the tool's description carefully to understand what parameters are required")
            prompt_parts.append("3. For calendar events, you MUST extract THREE required parameters:")
            prompt_parts.append("   - title: The name of the event. Look for:")
            prompt_parts.append("     * Words like 'called', 'named', 'titled' followed by the title")
            prompt_parts.append("     * The event name itself if it's clear (e.g., 'Team Meeting', 'Doctor Appointment')")
            prompt_parts.append("     * Example: 'add a meeting tomorrow at 2pm called Important' → title='Important'")
            prompt_parts.append("     * Example: 'schedule Team Sync for Friday' → title='Team Sync'")
            prompt_parts.append("     * NEVER use a generic default like 'Meeting' if the user specified a name!")
            prompt_parts.append("   - start_time: When the event starts. Look for:")
            prompt_parts.append("     * 'at 2pm', 'from 2pm', 'starts at 2pm', 'tomorrow at 2pm'")
            prompt_parts.append("     * Natural language is fine: 'tomorrow at 2pm', 'friday at 13:00', 'next week monday at 9am'")
            prompt_parts.append("   - end_time: When the event ends. Look for:")
            prompt_parts.append("     * 'to 3pm', 'until 3pm', 'ends at 3pm', 'from 2pm to 3pm'")
            prompt_parts.append("     * If only duration is given (e.g., '1 hour meeting'), calculate end_time from start_time")
            prompt_parts.append("   Full example: 'add meeting tomorrow 2pm to 3pm called Important'")
            prompt_parts.append("     → action='create', title='Important', start_time='tomorrow at 2pm', end_time='tomorrow at 3pm'")
            prompt_parts.append("4. CRITICAL: NEVER leave required parameters empty! If a parameter is marked as REQUIRED in the tool schema, you MUST provide it.")
            prompt_parts.append("5. Use natural language for dates/times when the tool supports it (e.g., 'tomorrow at 2pm')")
            prompt_parts.append("- After calling a tool, wait for the result before responding to the user")
            prompt_parts.append("")
            prompt_parts.append("IMPORTANT RULES:")
            prompt_parts.append("- NEVER claim to have performed an action unless you actually called a tool to do it")
            prompt_parts.append("- NEVER make up or hallucinate results from tool calls - only report what the tools actually return")
            prompt_parts.append("- If a tool call fails or returns an error, report that error honestly to the user")
            prompt_parts.append("- If you did not call a tool, do not claim that you did")
            prompt_parts.append("- Always be truthful and accurate about what actions were taken and what results were obtained")
            prompt_parts.append("- When asked about calendar events, file contents, or other data, you MUST use the appropriate tools to retrieve the information - do not make up data")
            prompt_parts.append("")
            prompt_parts.append("After successfully calling a tool, provide a natural, conversational response to the user explaining what was done.")
            prompt_parts.append("=" * 60)
        
        return "\n".join(prompt_parts)
    
    def get_default_load_options(self) -> Dict[str, Any]:
        """Get default model load options."""
        # Detect GPU layers (similar to what loader did)
        try:
            from llama_cpp import llama_cpp
            has_cuda = hasattr(llama_cpp, 'llama_supports_gpu_offload') or hasattr(llama_cpp, 'llama_gpu_offload')
            default_gpu_layers = -1 if has_cuda else 0
        except ImportError:
            default_gpu_layers = 0
        
        return {
            "n_gpu_layers": default_gpu_layers,
            "n_ctx": settings.llm_context_size,
            "n_batch": 512,
            "n_threads": settings.llm_n_threads,
            "flash_attn": False,
            "use_mmap": True,
            "use_mlock": False,
            "cache_type_k": "f16",
            "cache_type_v": "f16",
        }
    
    def update_default_load_options(self, options: Dict[str, Any]):
        """Update default load options (stored in settings, not here)."""
        # This is a no-op for now - options are passed per-request
        pass
    
    def get_model_config(self, model_id: str) -> Dict[str, Any]:
        """Get saved configuration for a model."""
        try:
            config_path = settings.data_dir / "model_configs.json"
            if config_path.exists():
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
                    return configs.get(model_id, {})
        except Exception as e:
            logger.error("Failed to load model config: %s", e)
        return {}
    
    def save_model_config(self, model_id: str, config: Dict[str, Any]):
        """Save configuration for a model."""
        try:
            config_path = settings.data_dir / "model_configs.json"
            configs = {}
            if config_path.exists():
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
            configs[model_id] = config
            import json
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(configs, f, indent=2)
        except Exception as e:
            logger.error("Failed to save model config: %s", e)
    
    async def _get_tool_source(self) -> Optional[Any]:
        """Get the tool source (tool_manager or tool_registry).
        
        Returns:
            Tool source object or None if not available.
        """
        # Try to get from LLM manager attributes first
        tool_source = getattr(self, 'tool_manager', None) or getattr(self, 'tool_registry', None)
        
        # If not found, try to get from service_manager
        if not tool_source:
            try:
                from ...services.service_manager import service_manager
                if hasattr(service_manager, 'tool_manager') and service_manager.tool_manager:
                    tool_source = service_manager.tool_manager
                    logger.info("[TOOL CALLING] Retrieved tool_manager from service_manager")
            except Exception as e:
                logger.warning(f"[TOOL CALLING] Could not get tool_manager from service_manager: {e}")
        
        if tool_source:
            logger.info(f"[TOOL CALLING] Tool source available: {type(tool_source).__name__}")
        else:
            logger.warning("[TOOL CALLING] No tool source available")
        
        return tool_source
    
    def _filter_history_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Filter and convert a history message to OpenAI format.
        
        Args:
            msg: History message dict with 'role' and optionally 'content', 'tool_calls'
            
        Returns:
            OpenAI-formatted message dict or None if message should be skipped
        """
        if not isinstance(msg, dict) or "role" not in msg:
            return None
        
        role = msg.get("role")
        
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            # When tool_results are present, we're in a follow-up call
            # In this case, we should include assistant messages with tool_calls from history
            # But we need to be careful - the LLM server expects a specific format
            if not tool_calls or (isinstance(tool_calls, list) and len(tool_calls) == 0):
                logger.debug(f"Skipping assistant message without tool_calls from history")
                return None
            
            # If we have tool_results, this is a follow-up call
            # The assistant message with tool_calls should be included, but we need to ensure
            # it's properly formatted and not causing validation errors
            # Actually, the issue is that when tool_results are present, we should NOT
            # include the assistant message in history - it should be implicit from the tool results
            # Let's skip it and let the tool results speak for themselves
            if hasattr(self, '_has_tool_results') and self._has_tool_results:
                logger.debug(f"Skipping assistant message with tool_calls in follow-up call (tool_results present)")
                return None
            
            # Convert tool_calls to OpenAI format if needed
            if isinstance(tool_calls, list) and len(tool_calls) > 0:
                first_tc = tool_calls[0]
                if isinstance(first_tc, dict) and "function" in first_tc:
                    # Already in OpenAI format
                    return {
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": tool_calls
                    }
                elif isinstance(first_tc, dict) and "name" in first_tc:
                    # Custom format - convert to OpenAI format
                    openai_tool_calls = []
                    for tc in tool_calls:
                        openai_tool_calls.append({
                            "id": tc.get("id", f"call_{len(openai_tool_calls)}"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("arguments", {})) if isinstance(tc.get("arguments"), dict) else str(tc.get("arguments", "{}"))
                            }
                        })
                    return {
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": openai_tool_calls
                    }
                else:
                    logger.warning(f"Unknown tool_calls format in history, skipping: {first_tc}")
                    return None
            else:
                logger.debug(f"Skipping assistant message - tool_calls is not a valid list: {tool_calls}")
                return None
        
        elif role == "tool":
            return {
                "role": "tool",
                "content": msg.get("content", ""),
                "tool_call_id": msg.get("tool_call_id")
            }
        
        elif role in ("system", "user"):
            return {
                "role": role,
                "content": msg.get("content", "")
            }
        
        else:
            logger.warning(f"Unknown message role in history: {role}, skipping")
            return None
    
    def _build_tool_result_messages(self, tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build OpenAI-formatted tool result messages.
        
        Note: This only creates tool result messages, NOT assistant messages with tool_calls.
        The assistant message with tool_calls should already be in the history.
        
        Args:
            tool_results: List of tool result dicts with 'id', 'name', 'result', 'success', 'error', 'arguments'
            
        Returns:
            List of OpenAI-formatted tool result messages (role="tool")
        """
        messages = []
        for result in tool_results:
            tool_call_id = result.get("id", f"call_{int(time.time())}")
            success = result.get("success", False)
            result_data = result.get("result")
            error = result.get("error")
            
            # Only add tool result message (assistant message with tool_calls should already be in history)
            tool_result_content = json.dumps(result_data) if success else json.dumps({"error": error})
            messages.append({
                "role": "tool",
                "content": tool_result_content,
                "tool_call_id": tool_call_id
            })
        
        return messages
    
    def _validate_assistant_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and filter out invalid assistant messages (without tool_calls).
        
        Args:
            messages: List of OpenAI-formatted messages
            
        Returns:
            Filtered list with invalid assistant messages removed
        """
        filtered = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant":
                if not msg.get("tool_calls"):
                    logger.error(f"CRITICAL: Found assistant message at index {i} without tool_calls! Removing it. Message keys: {list(msg.keys())}")
                    continue
            filtered.append(msg)
        
        if len(filtered) < len(messages):
            logger.warning(f"Filtered out {len(messages) - len(filtered)} invalid assistant message(s)")
        
        return filtered
    
    def _build_openai_messages(
        self,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        tool_results: Optional[List[Dict[str, Any]]],
        message: str
    ) -> List[Dict[str, Any]]:
        """Build OpenAI-formatted message list from history, context, tool results, and current message.
        
        Args:
            history: Conversation history
            context: Retrieved context from memory
            tool_results: Tool call results from previous executions
            message: Current user message
            
        Returns:
            List of OpenAI-formatted messages
        """
        messages = []
        
        # Add system prompt
        system_prompt = self._build_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            logger.debug(f"Added system prompt ({len(system_prompt)} chars)")
        
        # Add context if available
        if context and context.get("retrieved_messages"):
            context_text = "Relevant context from past conversations:\n"
            for msg in context["retrieved_messages"][:5]:
                context_text += f"- {msg}\n"
            messages.append({"role": "system", "content": context_text})
            logger.debug(f"Added context ({len(context['retrieved_messages'])} messages)")
        
        # When tool_results are present, we're in a follow-up call
        # The LLM server doesn't expect assistant messages with tool_calls in this context
        # We need to skip them from history - the tool results themselves imply the assistant made those calls
        skip_assistant_with_tool_calls = tool_results is not None and len(tool_results) > 0
        
        # Add history messages (filtered and converted)
        history_added = 0
        for msg in history:
            # Skip assistant messages with tool_calls when tool_results are present
            if skip_assistant_with_tool_calls and msg.get("role") == "assistant" and msg.get("tool_calls"):
                logger.debug(f"Skipping assistant message with tool_calls in follow-up call (tool_results present)")
                continue
            filtered_msg = self._filter_history_message(msg)
            if filtered_msg:
                messages.append(filtered_msg)
                history_added += 1
        
        logger.debug(f"Added {history_added} history messages (filtered from {len(history)} total)")
        
        # Log messages before adding tool results
        logger.debug(f"Messages before tool_results (count: {len(messages)}):")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            has_tool_calls = "tool_calls" in msg and msg.get("tool_calls")
            logger.debug(f"  Message {i}: role={role}, has_tool_calls={bool(has_tool_calls)}, content_length={len(str(msg.get('content', '')))}")
        
        # Add tool results if available
        if tool_results:
            tool_result_messages = self._build_tool_result_messages(tool_results)
            logger.info(f"[MESSAGE BUILD] Adding {len(tool_result_messages)} tool result message(s)")
            for i, tr_msg in enumerate(tool_result_messages):
                logger.info(f"[MESSAGE BUILD]   Tool result {i+1}: role={tr_msg.get('role')}, tool_call_id={tr_msg.get('tool_call_id')}, content_length={len(str(tr_msg.get('content', '')))}")
            messages.extend(tool_result_messages)
        
        # Add current user message
        # Note: In follow-up calls with tool_results, we still add the user message
        # as it provides context for the model's response
        messages.append({"role": "user", "content": message})
        logger.info(f"[MESSAGE BUILD] Added user message: {message[:100]}...")
        
        # Log final message structure
        logger.info(f"[MESSAGE BUILD] Final message count: {len(messages)}")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            has_tool_calls = "tool_calls" in msg and msg.get("tool_calls")
            has_tool_call_id = "tool_call_id" in msg
            content_preview = str(msg.get("content", ""))[:50] if msg.get("content") else "None"
            logger.info(f"[MESSAGE BUILD]   Message {i}: role={role}, has_tool_calls={has_tool_calls}, has_tool_call_id={has_tool_call_id}, content='{content_preview}...'")
        
        # Final validation
        messages = self._validate_assistant_messages(messages)
        
        return messages
    
    def _should_force_tool_calling(self) -> bool:
        """Check if tool calling should be forced for Llama 3.1/3.2 models.
        
        Returns:
            True if tool calling should be forced, False otherwise
        """
        model_name_lower = (self.current_model_name or "").lower()
        is_llama_32 = ("3.2" in model_name_lower or "3_2" in model_name_lower)
        is_llama_31 = ("3.1" in model_name_lower or "3_1" in model_name_lower)
        is_llama = ("llama" in model_name_lower)
        
        if is_llama and (is_llama_32 or is_llama_31) and not self.supports_tool_calling:
            logger.warning("[LLAMA FORCE] Detection failed but model is Llama 3.1/3.2 - FORCING tool calling")
            return True
        return False
    
    def _ensure_tool_format(self, tools: List[Dict[str, Any]], chat_format: Optional[str]) -> List[Dict[str, Any]]:
        """Ensure tools have required fields for the chat format.
        
        For chatml-function-calling, ensures title fields exist at root and property level.
        
        Args:
            tools: List of tool dicts in OpenAI format
            chat_format: Current chat format (e.g., "chatml-function-calling")
            
        Returns:
            Tools with required fields ensured
        """
        if chat_format != "chatml-function-calling":
            return tools
        
        for tool in tools:
            params = tool.get('function', {}).get('parameters', {})
            tool_name = tool.get('function', {}).get('name', 'unknown')
            
            # Ensure root-level title
            if 'title' not in params:
                params['title'] = tool_name
                logger.debug(f"[TOOL FORMAT] Added missing 'title' to tool {tool_name}")
            
            # Ensure property-level titles
            if 'properties' in params:
                for prop_name, prop_def in params['properties'].items():
                    if isinstance(prop_def, dict) and 'title' not in prop_def:
                        prop_def['title'] = prop_name.capitalize()
                        logger.debug(f"[TOOL FORMAT] Added missing 'title' to property {prop_name} in tool {tool_name}")
        
        return tools
    
    async def _retrieve_tools(self, tool_source: Any) -> List[Dict[str, Any]]:
        """Retrieve tools from tool source in OpenAI format.
        
        Args:
            tool_source: Tool source object with list_tools() method
            
        Returns:
            List of tools in OpenAI format, or empty list if unavailable
        """
        if not tool_source:
            return []
        
        if not hasattr(tool_source, 'list_tools'):
            logger.error(f"[TOOL CALLING] Tool source {type(tool_source).__name__} does not have list_tools() method")
            return []
        
        try:
            if asyncio.iscoroutinefunction(tool_source.list_tools):
                tools = await tool_source.list_tools()
            else:
                tools = tool_source.list_tools()
            
            if not tools:
                logger.debug("[TOOL CALLING] Tool source returned empty list")
                return []
            
            logger.info(f"[TOOL CALLING] Retrieved {len(tools)} tools from tool source")
            tool_names = [t.get('function', {}).get('name') for t in tools]
            logger.info(f"[TOOL CALLING] Tool names: {tool_names}")
            
            return tools
        except Exception as e:
            logger.error(f"[TOOL CALLING] Error retrieving tools: {e}", exc_info=True)
            return []
    
    async def _get_model_name_for_request(self, server_url: str) -> str:
        """Get the model name to use in the request.
        
        For chatml-function-calling, returns "test" as per official docs.
        For other formats, queries the server for the actual model ID.
        
        Args:
            server_url: LLM server URL
            
        Returns:
            Model name string
        """
        chat_format = getattr(self, 'current_chat_format', None)
        if chat_format == "chatml-function-calling":
            logger.info("[MODEL NAME] Using 'test' for chatml-function-calling format")
            return "test"
        
        # Get the actual model ID from the server
        model_name = self.current_model_name or "default"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{server_url}/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data") and len(data["data"]) > 0:
                        model_name = data["data"][0]["id"]
                        logger.debug(f"Using model ID from server: {model_name}")
        except Exception as e:
            logger.warning(f"Could not query server for model ID, using default: {e}")
        
        return model_name
    
    def _build_request_payload(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        stream: bool,
        model_name: str,
        server_url: str
    ) -> Dict[str, Any]:
        """Build the request payload for the LLM server.
        
        Args:
            messages: OpenAI-formatted messages
            tools: List of tools in OpenAI format
            stream: Whether to stream the response
            model_name: Model name to use
            server_url: Server URL for logging
            
        Returns:
            Request payload dict
        """
        # Use tool-calling sampler settings if tools are present (for more deterministic tool calls)
        # Otherwise use regular sampler settings (for creative chat responses)
        use_tool_settings = bool(tools) and len(tools) > 0
        active_settings = self.tool_calling_sampler_settings if use_tool_settings else self.sampler_settings
        
        if use_tool_settings:
            logger.warning(f"[TOOL CALLING] 🔧 Using tool-calling sampler settings (temperature={active_settings.temperature}, top_p={active_settings.top_p}, top_k={active_settings.top_k}) for more deterministic tool calls")
        else:
            logger.debug(f"[GENERATE] Using regular sampler settings (temperature={active_settings.temperature})")
        
        # Ensure max_tokens is reasonable before building payload
        max_tokens = active_settings.max_tokens
        if max_tokens < 10:
            logger.warning(f"[GENERATE] max_tokens ({max_tokens}) is too low, using minimum of 10")
            max_tokens = 10
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": active_settings.temperature,
            "top_p": active_settings.top_p,
            "max_tokens": max_tokens,
        }
        
        # Add other sampler parameters from active settings
        if active_settings.top_k != self.sampler_settings.top_k or use_tool_settings:
            payload["top_k"] = active_settings.top_k
        
        # Add stop tokens if specified - validate they won't cause immediate stopping
        # CRITICAL: Replace template variables in stop tokens (e.g., {{user}} -> actual user name)
        if hasattr(self.sampler_settings, 'stop') and self.sampler_settings.stop:
            stop_tokens = self.sampler_settings.stop
            if isinstance(stop_tokens, list) and len(stop_tokens) > 0:
                # Get user_name and char_name for template variable replacement
                user_name = None
                char_name = None
                if self.user_profile:
                    if isinstance(self.user_profile, dict):
                        user_name = self.user_profile.get("name")
                    else:
                        user_name = getattr(self.user_profile, "name", None)
                if self.character_card:
                    if isinstance(self.character_card, dict):
                        char_name = self.character_card.get("name")
                    else:
                        char_name = getattr(self.character_card, "name", None)
                
                # Replace template variables in stop tokens
                from ...utils.template_parser import parse_stop_strings
                parsed_stop_tokens = parse_stop_strings(stop_tokens, user_name, char_name)
                
                # Filter out only truly empty/invalid stop tokens
                # Stop tokens are meant to prevent user impersonation and hallucinations, so we keep them
                valid_stop_tokens = []
                
                logger.info(f"[GENERATE] Processing {len(parsed_stop_tokens) if parsed_stop_tokens else 0} stop tokens after template replacement")
                for s in parsed_stop_tokens:
                    if not s:
                        continue
                    s_stripped = s.strip()
                    # Only filter out completely empty strings after stripping
                    if len(s_stripped) == 0:
                        logger.debug(f"[GENERATE] Skipping empty stop token: {repr(s)}")
                        continue
                    # Keep all non-empty stop tokens - they serve a purpose (prevent impersonation/hallucination)
                    valid_stop_tokens.append(s)
                
                # Log stop token processing
                logger.info(f"[GENERATE] Stop token processing:")
                logger.info(f"  Original: {len(stop_tokens)} tokens")
                logger.info(f"  After template replacement: {len(parsed_stop_tokens) if parsed_stop_tokens else 0} tokens")
                logger.info(f"  Valid (non-empty): {len(valid_stop_tokens)} tokens")
                
                if stop_tokens != parsed_stop_tokens:
                    logger.info(f"[GENERATE] Template variables replaced:")
                    logger.info(f"  Original: {stop_tokens}")
                    logger.info(f"  Replaced: {parsed_stop_tokens}")
                    logger.info(f"  user_name={user_name}, char_name={char_name}")
                
                # Stop tokens implementation based on official OpenAI API and llama-cpp-python docs:
                # - Stop parameter accepts a list of strings (up to 4 in OpenAI API)
                # - When the model generates any of these sequences, it stops generation
                # - Stop sequences are NOT included in the generated text
                # - Stop sequences should only match in generated output, not in the prompt
                # - Stop tokens are meant to prevent user impersonation and hallucinations
                #
                # Implementation: Send valid stop tokens to the LLM server
                # The server handles matching stop sequences in generated output only
                if valid_stop_tokens:
                    payload["stop"] = valid_stop_tokens
                    logger.info(f"[GENERATE] Using stop tokens: {valid_stop_tokens}")
                else:
                    logger.info(f"[GENERATE] No valid stop tokens after processing")
                    # Explicitly remove stop from payload if it was set
                    if "stop" in payload:
                        del payload["stop"]
            else:
                logger.warning(f"[GENERATE] Invalid stop tokens format: {stop_tokens}")
        
        logger.debug(f"[GENERATE] Payload max_tokens: {max_tokens}")
        
        # Add tools if available
        if tools:
            payload["tools"] = tools
            # tool_choice handling: Let the LLM decide when to use tools
            # "auto" = model can choose to use tools OR respond normally
            # This is the correct approach - let the LLM decide based on the conversation
            if not stream:
                payload["tool_choice"] = "auto"
                logger.info(f"[TOOL CALLING] ✅ Using tool_choice='auto' - letting LLM decide when to use tools")
            else:
                logger.info(f"[TOOL CALLING] ✅ Sending request with {len(tools)} tools (no tool_choice - streaming mode)")
            
            tool_names = [t.get('function', {}).get('name') for t in tools]
            logger.info(f"[TOOL CALLING] Tool names: {tool_names}")
            logger.info(f"[TOOL CALLING] Using model name: {model_name} (chat_format: {getattr(self, 'current_chat_format', 'unknown')})")
        else:
            if self.supports_tool_calling:
                logger.warning("[TOOL CALLING] ⚠️  Tool calling enabled but no tools available - request will be sent without tools!")
        
        return payload
    
    def _parse_tool_calls_standard(self, message_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse tool calls from standard tool_calls field in message.
        
        Args:
            message_obj: Message object from response
            
        Returns:
            List of tool call dicts in OpenAI format
        """
        tool_calls = []
        if "tool_calls" in message_obj and message_obj["tool_calls"]:
            logger.info(f"✅ Tool calls detected in response: {len(message_obj['tool_calls'])}")
            for i, tc in enumerate(message_obj["tool_calls"]):
                tool_call_data = {
                    "id": tc.get("id"),
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc.get("function", {}).get("name"),
                        "arguments": tc.get("function", {}).get("arguments", "{}")
                    }
                }
                tool_calls.append(tool_call_data)
                logger.info(f"  Tool call {i+1}: {tool_call_data['function']['name']} (id: {tool_call_data['id']})")
                logger.info(f"  Arguments: {tool_call_data['function']['arguments']}")
        return tool_calls
    
    def _parse_tool_calls_from_json_content(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from JSON content in response text.
        
        Handles both full JSON content and embedded JSON objects.
        Supports both "arguments" and "parameters" keys.
        
        Args:
            response_text: Response text content
            
        Returns:
            List of tool call dicts in OpenAI format
        """
        tool_calls = []
        logger.debug(f"[TOOL CALL PARSING] Checking content for JSON tool call: {response_text[:200]}")
        
        # Try to parse the entire content as JSON first
        try:
            tool_call_json = json.loads(response_text.strip())
            if isinstance(tool_call_json, dict) and "name" in tool_call_json:
                logger.info(f"[TOOL CALL PARSING] Found tool call JSON as entire content: {tool_call_json.get('name')}")
                args = tool_call_json.get("arguments") or tool_call_json.get("parameters", {})
                tool_call_data = {
                    "id": f"call_{int(time.time())}",
                    "type": "function",
                    "function": {
                        "name": tool_call_json.get("name"),
                        "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                    }
                }
                tool_calls.append(tool_call_data)
                logger.info(f"  ✅ Parsed tool call from content: {tool_call_data['function']['name']}")
                logger.info(f"  Arguments: {tool_call_data['function']['arguments']}")
                return tool_calls
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON object within content
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"name"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_match = re.search(json_pattern, response_text)
        if not json_match:
            json_match = re.search(r'\{.*?"name".*?\}', response_text, re.DOTALL)
        
        if json_match:
            try:
                tool_call_json = json.loads(json_match.group())
                if "name" in tool_call_json:
                    logger.info(f"[TOOL CALL PARSING] Found tool call JSON in content: {tool_call_json.get('name')}")
                    args = tool_call_json.get("arguments") or tool_call_json.get("parameters", {})
                    tool_call_data = {
                        "id": f"call_{int(time.time())}",
                        "type": "function",
                        "function": {
                            "name": tool_call_json.get("name"),
                            "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                        }
                    }
                    tool_calls.append(tool_call_data)
                    logger.info(f"  ✅ Parsed tool call from content: {tool_call_data['function']['name']}")
                    logger.info(f"  Arguments: {tool_call_data['function']['arguments']}")
            except json.JSONDecodeError as e:
                logger.debug(f"[TOOL CALL PARSING] Failed to parse JSON: {e}")
        
        return tool_calls
    
    def _parse_tool_calls_qwen_hermes(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse Qwen's Hermes-style tool calls from XML tags.
        
        Args:
            response_text: Response text content
            
        Returns:
            List of tool call dicts in OpenAI format
        """
        tool_calls = []
        tool_call_matches = re.findall(r'<tool_call>(.*?)</tool_call>', response_text, re.DOTALL)
        if tool_call_matches:
            logger.info(f"[QWEN] Found Hermes-style tool calls in response: {len(tool_call_matches)}")
            for i, match in enumerate(tool_call_matches):
                try:
                    tool_call_json = json.loads(match.strip())
                    args = tool_call_json.get("arguments") or tool_call_json.get("parameters", {})
                    tool_call_data = {
                        "id": f"call_qwen_{i}_{int(time.time())}",
                        "type": "function",
                        "function": {
                            "name": tool_call_json.get("name", ""),
                            "arguments": json.dumps(args) if isinstance(args, dict) else str(args)
                        }
                    }
                    tool_calls.append(tool_call_data)
                    logger.info(f"  [QWEN] Parsed tool call {i+1}: {tool_call_data['function']['name']}")
                    logger.info(f"  Arguments: {tool_call_data['function']['arguments']}")
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"[QWEN] Failed to parse Hermes tool call: {e}")
                    logger.debug(f"[QWEN] Tool call content: {match[:200]}")
        return tool_calls
    
    def _parse_tool_calls_from_response(self, message_obj: Dict[str, Any], response_text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from LLM response.
        
        Tries standard format first, then JSON content, then Qwen Hermes format.
        
        Args:
            message_obj: Message object from response
            response_text: Response text content
            
        Returns:
            List of tool call dicts in OpenAI format
        """
        # Try standard format first
        tool_calls = self._parse_tool_calls_standard(message_obj)
        if tool_calls:
            return tool_calls
        
        # Try JSON content parsing
        if response_text:
            tool_calls = self._parse_tool_calls_from_json_content(response_text)
            if tool_calls:
                return tool_calls
            
            # Try Qwen Hermes format
            is_qwen = "qwen" in (self.current_model_name or "").lower()
            if is_qwen:
                tool_calls = self._parse_tool_calls_qwen_hermes(response_text)
                if tool_calls:
                    return tool_calls
        
        if not tool_calls:
            logger.info("No tool calls in response")
            if response_text:
                logger.debug(f"Response text content: {response_text[:300]}")
        
        return tool_calls
    
    async def generate_response(
        self,
        message: str,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate a response using the OpenAI-compatible server.
        
        Args:
            message: Current user message
            history: Conversation history (list of dicts with 'role' and 'content')
            context: Retrieved context from memory
            tool_results: Tool call results from previous tool executions
            stream: Whether to stream the response (not yet implemented)
            
        Returns:
            Dict with 'response' (str) and 'tool_calls' (list)
        """
        if not self.is_model_loaded():
            logger.error("No model loaded. Current model path: %s, Model name: %s", 
                        self._current_model_path, self.current_model_name)
            raise RuntimeError("No model loaded. Please load a model first.")
        
        if stream:
            raise NotImplementedError("Streaming not yet implemented")
        
        try:
            # Validate and clamp sampler settings
            self._validate_sampler_settings()
            
            # Check server health
            if not await self.server_manager.health_check():
                raise RuntimeError("LLM server is not responding. Please reload the model.")
            
            # Get server URL
            server_url = self.server_manager.get_server_url()
            
            # Debug: Log tool calling support and availability
            logger.info("=" * 60)
            logger.info("GENERATE RESPONSE - TOOL CALLING DEBUG")
            logger.info("=" * 60)
            logger.info(f"Model supports tool calling: {self.supports_tool_calling}")
            logger.info(f"Tool registry available: {hasattr(self, 'tool_registry') and self.tool_registry is not None}")
            
            # Get tool source
            tool_source = await self._get_tool_source()
            
            logger.info(f"Tool results provided: {tool_results is not None and len(tool_results) > 0 if tool_results else False}")
            if tool_results:
                logger.info(f"Tool results count: {len(tool_results)}")
                for i, result in enumerate(tool_results):
                    logger.info(f"  Tool result {i+1}: {result.get('name')} - success={result.get('success')}")
            logger.info("=" * 60)
            
            # Always use OpenAI-compatible server for generation
            tool_calls = []
            response_text = ""
            
            # Build messages for OpenAI format
            openai_messages = self._build_openai_messages(history, context, tool_results, message)
            
            # Force enable tool calling for Llama 3.1/3.2 if needed
            if self._should_force_tool_calling():
                self.supports_tool_calling = True
            
            # Retrieve tools if tool calling is enabled
            # IMPORTANT: Don't send tools in follow-up calls (when tool_results are present)
            # The model already has the tool results and should respond normally
            openai_tools = []
            logger.warning(f"[TOOL CALLING] 🔍 Step 1: supports_tool_calling={self.supports_tool_calling}, tool_results={bool(tool_results)}, tool_source={bool(tool_source)}")
            
            if self.supports_tool_calling and not tool_results:
                if tool_source:
                    logger.warning(f"[TOOL CALLING] 🔍 Step 2: Retrieving tools from tool_source...")
                    openai_tools = await self._retrieve_tools(tool_source)
                    logger.warning(f"[TOOL CALLING] 🔍 Step 3: Retrieved {len(openai_tools)} tools from tool_source")
                    if openai_tools:
                        tool_names = [t.get('function', {}).get('name', 'unknown') for t in openai_tools[:3]]
                        logger.warning(f"[TOOL CALLING] 🔍 Step 3b: Tool names: {tool_names}")
                else:
                    logger.warning("[TOOL CALLING] ⚠️  Tool calling enabled but no tool_source available - tools won't be sent")
            elif tool_results:
                logger.info("[TOOL CALLING] Follow-up call with tool results - not sending tools (model should respond normally)")
            else:
                logger.info("[TOOL CALLING] Tool calling is DISABLED - tools will not be sent")
            
            # Ensure tools have required format fields
            if openai_tools:
                chat_format = getattr(self, 'current_chat_format', None)
                logger.warning(f"[TOOL CALLING] 🔍 Step 4: Formatting {len(openai_tools)} tools with chat_format={chat_format}")
                openai_tools = self._ensure_tool_format(openai_tools, chat_format)
                logger.warning(f"[TOOL CALLING] 🔍 Step 5: After formatting: {len(openai_tools)} tools ready")
            else:
                logger.warning(f"[TOOL CALLING] 🔍 Step 4: No tools to format (openai_tools is empty)")
            
            # Get model name for request
            model_name = await self._get_model_name_for_request(server_url)
            
            # Build request payload - THIS IS WHERE TOOL-CALLING SETTINGS ARE APPLIED
            # Log BEFORE building payload so we can verify tools are present
            logger.warning(f"[TOOL CALLING] 🔍 Step 6: About to build payload with {len(openai_tools)} tools - will use {'TOOL-CALLING' if openai_tools else 'REGULAR'} settings")
            payload = self._build_request_payload(openai_messages, openai_tools, stream, model_name, server_url)
            actual_temp = payload.get('temperature', 'N/A')
            actual_tools_count = len(payload.get('tools', []))
            logger.warning(f"[TOOL CALLING] 🔍 Step 7: Payload built - temperature={actual_temp}, tools_in_payload={actual_tools_count}, top_p={payload.get('top_p', 'N/A')}, top_k={payload.get('top_k', 'N/A')}")
            
            # Log request for debugging
            from .debug_logger import log_llm_request, log_llm_response, log_llm_error
            debug_log = log_llm_request(
                payload=payload,
                metadata={
                    "chat_format": getattr(self, 'current_chat_format', None),
                    "model_name": model_name,
                    "supports_tool_calling": self.supports_tool_calling,
                    "server_url": server_url,
                    "tool_count": len(openai_tools) if openai_tools else 0
                }
            )
            request_start = time.time()
            
            # Make request to OpenAI-compatible server
            try:
                # Log request details for debugging empty responses (INFO level so it's captured)
                logger.info(f"[GENERATE] Request payload summary:")
                logger.info(f"  Messages count: {len(payload.get('messages', []))}")
                logger.info(f"  Tools count: {len(payload.get('tools', []))}")
                logger.info(f"  Max tokens: {payload.get('max_tokens', 'default')}")
                logger.info(f"  Temperature: {payload.get('temperature', 'default')} {'(TOOL-CALLING SETTINGS)' if openai_tools else '(REGULAR SETTINGS)'}")
                logger.info(f"  Top_p: {payload.get('top_p', 'default')}")
                logger.info(f"  Top_k: {payload.get('top_k', 'default')}")
                logger.info(f"  Stop tokens sent to LLM: {payload.get('stop', 'NOT SET')}")
                if payload.get('messages'):
                    logger.info(f"  Last message role: {payload['messages'][-1].get('role')}")
                    logger.info(f"  Last message preview: {str(payload['messages'][-1].get('content', ''))[:100]}")
                
                async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced from 300s to 30s
                    response = await client.post(
                        f"{server_url}/v1/chat/completions",
                        json=payload
                    )
                    request_duration = (time.time() - request_start) * 1000  # Convert to ms
                    response.raise_for_status()
                    resp_data = response.json()
                    logger.info(f"[GENERATE] Received response from LLM server, status={response.status_code}")
                    
                    # Log FULL raw response for debugging - this is critical
                    logger.info(f"[GENERATE] FULL RAW RESPONSE:")
                    logger.info(f"  Response keys: {list(resp_data.keys())}")
                    logger.info(f"  Full response JSON: {json.dumps(resp_data, indent=2, default=str)}")
                    
                    if "choices" in resp_data and len(resp_data["choices"]) > 0:
                        choice = resp_data["choices"][0]
                        logger.info(f"[GENERATE] Choice details:")
                        logger.info(f"  Finish reason: {choice.get('finish_reason')}")
                        logger.info(f"  Index: {choice.get('index')}")
                        message_obj = choice.get('message', {})
                        logger.info(f"  Message keys: {list(message_obj.keys())}")
                        logger.info(f"  Message full: {json.dumps(message_obj, indent=2, default=str)}")
                        content = message_obj.get('content', '') or ''
                        logger.info(f"  Content: {repr(content)}")
                        logger.info(f"  Content length: {len(content)}")
                        if message_obj.get('tool_calls'):
                            logger.info(f"  Tool calls count: {len(message_obj['tool_calls'])}")
                            logger.info(f"  Tool calls: {json.dumps(message_obj['tool_calls'], indent=2, default=str)}")
                    
                    # Extract tool calls for logging
                    tool_calls_for_log = []
                    if resp_data.get("choices") and len(resp_data["choices"]) > 0:
                        message_obj = resp_data["choices"][0].get("message", {})
                        logger.info(f"[TOOL CALLING] Response message keys: {list(message_obj.keys())}")
                        logger.info(f"[TOOL CALLING] Response has 'tool_calls' key: {'tool_calls' in message_obj}")
                        if message_obj.get("tool_calls"):
                            tool_calls_for_log = message_obj["tool_calls"]
                            logger.info(f"[TOOL CALLING] ✅ Found {len(tool_calls_for_log)} tool call(s) in response!")
                        else:
                            content = message_obj.get("content", "")
                            logger.info(f"[TOOL CALLING] No tool_calls in response, content length: {len(content)}")
                            logger.debug(f"[TOOL CALLING] Response content preview: {content[:200]}")
                    
                    # Log response
                    log_llm_response(
                        log_entry=debug_log,
                        response=resp_data,
                        duration_ms=request_duration,
                        tool_calls=tool_calls_for_log if tool_calls_for_log else None
                    )
                
                # SIMPLIFIED EXTRACTION: Just get the content directly, no complex logic
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    choice = resp_data["choices"][0]
                    message_obj = choice.get("message", {})
                    finish_reason = choice.get("finish_reason", "unknown")
                    
                    # Parse tool calls FIRST - if tool calls exist, empty content is expected
                    tool_calls = self._parse_tool_calls_from_response(message_obj, "")
                    
                    # Get content - handle all possible types
                    content_raw = message_obj.get("content")
                    if content_raw is None:
                        response_text = ""
                    elif content_raw == "":
                        response_text = ""
                    elif isinstance(content_raw, str):
                        response_text = content_raw
                    else:
                        # Convert to string if it's not None/empty
                        response_text = str(content_raw)
                    
                    logger.info(f"[GENERATE] Content extracted: type={type(content_raw)}, value={repr(content_raw)}, final={repr(response_text)}")
                    logger.info(f"[GENERATE] Tool calls parsed: {len(tool_calls)}")
                    
                    # Log response details for debugging
                    logger.info(f"[GENERATE] Response extracted:")
                    logger.info(f"  Content length: {len(response_text)}")
                    logger.info(f"  Tool calls: {len(tool_calls)}")
                    logger.info(f"  Finish reason: {finish_reason}")
                    logger.info(f"  Message keys: {list(message_obj.keys())}")
                    
                    # Only warn about empty content if there are NO tool calls
                    # If tool calls exist, empty content is EXPECTED and NORMAL
                    if not response_text and not tool_calls:
                        logger.warning(f"Empty content in response. Message object keys: {list(message_obj.keys())}")
                        logger.warning(f"Full message object: {message_obj}")
                        logger.warning(f"Finish reason: {finish_reason}")
                        
                        # Log what finish_reason means
                        if finish_reason == "stop":
                            logger.warning("[GENERATE] Model stopped with 'stop' reason - a stop token was matched")
                            logger.warning(f"[GENERATE] Stop tokens that were sent: {payload.get('stop', 'NOT SET')}")
                        elif finish_reason == "length":
                            logger.warning(f"[GENERATE] Model stopped due to length limit (max_tokens: {payload.get('max_tokens', 'default')})")
                        elif finish_reason == "tool_calls":
                            logger.info("[GENERATE] Model stopped for tool calls - this is expected")
                        elif finish_reason:
                            logger.warning(f"[GENERATE] Model stopped with reason: {finish_reason}")
                    elif not response_text and tool_calls:
                        logger.info("[GENERATE] Empty content but tool calls present - this is EXPECTED and NORMAL behavior")
                else:
                    logger.warning("Invalid response format from OpenAI endpoint")
                    logger.warning(f"Response data keys: {list(resp_data.keys()) if isinstance(resp_data, dict) else 'Not a dict'}")
                    response_text = ""
            except httpx.HTTPStatusError as e:
                request_duration = (time.time() - request_start) * 1000
                error_detail = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
                logger.error(f"[GENERATE] HTTP error: {error_detail}")
                log_llm_error(
                    log_entry=debug_log,
                    error=error_detail,
                    duration_ms=request_duration
                )
                raise Exception(f"Generation failed: {error_detail}") from e
            except Exception as e:
                request_duration = (time.time() - request_start) * 1000
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"[GENERATE] Exception: {error_msg}")
                log_llm_error(
                    log_entry=debug_log,
                    error=error_msg,
                    duration_ms=request_duration
                )
                raise
            
            # If we got empty response with tool_choice="auto" and no tool calls,
            # retry with tool_choice="none" as a fallback to ensure normal chat works
            if not response_text and not tool_calls and openai_tools and payload.get("tool_choice") == "auto":
                logger.warning("[TOOL CALLING] Got empty response with tool_choice='auto' and no tool calls")
                logger.warning("[TOOL CALLING] Retrying with tool_choice='none' as fallback")
                
                # Retry with tool_choice="none"
                payload_retry = payload.copy()
                payload_retry["tool_choice"] = "none"
                
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        retry_response = await client.post(
                            f"{server_url}/v1/chat/completions",
                            json=payload_retry
                        )
                        retry_response.raise_for_status()
                        retry_data = retry_response.json()
                        
                        if "choices" in retry_data and len(retry_data["choices"]) > 0:
                            retry_choice = retry_data["choices"][0]
                            retry_message = retry_choice.get("message", {})
                            retry_content = retry_message.get("content", "") or ""
                            retry_tool_calls = self._parse_tool_calls_from_response(retry_message, retry_content)
                            
                            if retry_content or retry_tool_calls:
                                logger.info(f"[TOOL CALLING] ✅ Retry successful! Got content: {len(retry_content)} chars, tool_calls: {len(retry_tool_calls)}")
                                response_text = retry_content
                                tool_calls = retry_tool_calls
                                resp_data = retry_data  # Update resp_data for logging
                            else:
                                logger.warning("[TOOL CALLING] Retry also returned empty - this is a deeper issue")
                except Exception as retry_e:
                    logger.error(f"[TOOL CALLING] Retry failed: {retry_e}")
            
            # CRITICAL FIX: If we get empty content, check if it's actually empty or if there's a parsing issue
            # Sometimes the model returns content but we're not extracting it correctly
            if not response_text and not tool_calls:
                # Double-check the raw response
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    raw_message = resp_data["choices"][0].get("message", {})
                    raw_content = raw_message.get("content")
                    logger.error(f"[GENERATE] Empty response - raw content from server: {repr(raw_content)}")
                    logger.error(f"[GENERATE] Raw content type: {type(raw_content)}")
                    
                    # Try to extract content again if it exists
                    if raw_content and isinstance(raw_content, str) and len(raw_content.strip()) > 0:
                        logger.warning(f"[GENERATE] Found content that was missed! Using it: {raw_content[:100]}")
                        response_text = raw_content
                    elif raw_content is not None and raw_content != "":
                        # Content exists but might be non-string
                        response_text = str(raw_content)
                        logger.warning(f"[GENERATE] Converted non-string content to string: {response_text[:100]}")
                
                # If still empty after all checks, log the issue but don't set fallback
                # Let the caller decide what to do
                if not response_text and not tool_calls:
                    logger.error("[GENERATE] CRITICAL: Model returned truly empty response")
                    logger.error(f"[GENERATE] Finish reason: {finish_reason}")
                    logger.error(f"[GENERATE] This indicates the model stopped before generating anything")
                    # Don't set fallback - return empty and let caller handle
                    response_text = ""
            elif not response_text and tool_calls:
                logger.info("Empty content but tool calls present - this is expected behavior")
            
            logger.info(f"Response generated: {len(response_text)} characters")
            logger.info(f"Tool calls detected: {len(tool_calls)}")
            if tool_calls:
                logger.info("Final tool calls summary:")
                for i, tc in enumerate(tool_calls):
                    logger.info(f"  {i+1}. {tc.get('function', {}).get('name')} (id: {tc.get('id')})")
            else:
                logger.info("No tool calls in final response")
            
            # Additional validation: if we got empty response, log the full request context
            if not response_text and not tool_calls:
                logger.error("[GENERATE] Empty response validation failed - logging request context:")
                logger.error(f"  Messages sent: {len(openai_messages)}")
                if openai_messages:
                    logger.error(f"  Last message: {openai_messages[-1]}")
                logger.error(f"  Tools available: {len(openai_tools) if openai_tools else 0}")
                logger.error(f"  Payload keys: {list(payload.keys())}")
                logger.error(f"  Model: {model_name}")
                logger.error(f"  Server URL: {server_url}")
            
            return {
                "response": response_text,
                "tool_calls": tool_calls
            }
        except ValueError as e:
            # Validation errors - return clear error message
            logger.error("Validation error in generation: %s", e)
            raise RuntimeError(f"Invalid input: {str(e)}") from e
        except RuntimeError:
            # Re-raise runtime errors (like model not loaded)
            raise
        except Exception as e:
            logger.error("Generation failed: %s", e, exc_info=True)
            # Don't crash the server - raise a runtime error with clear message
            raise RuntimeError(f"Generation failed: {str(e)}") from e
    
    def _validate_history(self, history: List[Dict[str, Any]]) -> None:
        """Validate conversation history format.
        
        Args:
            history: Conversation history to validate
            
        Raises:
            ValueError: If history format is invalid
        """
        if not isinstance(history, list):
            raise ValueError(f"History must be a list, got {type(history)}")
        
        for i, msg in enumerate(history):
            if not isinstance(msg, dict):
                raise ValueError(f"Message {i} is not a dict: {msg}")
            if 'role' not in msg:
                raise ValueError(f"Message {i} missing 'role' field: {msg}")
            if 'content' not in msg:
                raise ValueError(f"Message {i} missing 'content' field: {msg}")
            if not isinstance(msg.get('content'), str):
                raise ValueError(f"Message {i} 'content' must be a string: {msg}")
    
    def _validate_context(self, context: Optional[Dict[str, Any]]) -> None:
        """Validate context format.
        
        Args:
            context: Context dictionary to validate
            
        Raises:
            ValueError: If context format is invalid
        """
        if context is None:
            return
        
        if not isinstance(context, dict):
            raise ValueError(f"Context must be a dict, got {type(context)}")
        
        if "retrieved_messages" in context:
            retrieved = context["retrieved_messages"]
            if not isinstance(retrieved, list):
                raise ValueError(f"Context 'retrieved_messages' must be a list, got {type(retrieved)}")
    
