"""LLM model manager for server process management."""
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from .loader import LLMLoader
from .downloader import ModelDownloader
from .sampler import SamplerSettings
from ..external.llm_server_service import llm_server
from ...config.settings import settings

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages LLM server process and model loading.
    
    This manager handles the lifecycle of the llama-cpp-python server,
    including starting with appropriate parameters, stopping, and
    tracking the current model state.
    """
    
    def __init__(self, tool_registry: Optional[Any] = None):
        self.loader = LLMLoader()  # Kept for hardware detection
        self.downloader = ModelDownloader()
        self.current_model_name: Optional[str] = None
        
        # Settings (kept for compatibility with existing code that reads these)
        self.sampler_settings = SamplerSettings(
            temperature=settings.temperature,
            top_p=settings.top_p,
            top_k=settings.top_k,
            repeat_penalty=settings.repeat_penalty,
            max_tokens=settings.llm_context_size // 4
        )
        self.system_prompt = settings.default_system_prompt
        self.character_card = None
        self.user_profile = None
        self.tool_registry = tool_registry
        self._memory_store = None  # Will be set during initialization
        self.supports_tool_calling: bool = False  # Auto-detected when model loads
    
    def _detect_tool_calling_support(self, model_path: str) -> bool:
        """Detect if the loaded model supports tool calling (function calling).
        
        Args:
            model_path: Path to the model file
            
        Returns:
            True if model supports tool calling, False otherwise
        """
        from pathlib import Path
        from .model_info import ModelInfoExtractor
        
        model_file = Path(model_path)
        model_name = model_file.name.lower()
        
        # Extract model info
        info_extractor = ModelInfoExtractor(model_file.parent)
        model_info = info_extractor.extract_info(model_file.name)
        architecture = model_info.get("architecture", "Unknown").lower()
        
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
        
        # Check architecture
        supports = False
        
        if "llama" in architecture or "llama" in model_name:
            # Llama 3.1+ and 3.2+ support function calling
            if "3.1" in model_name or "3.2" in model_name or "llama-3.1" in model_name or "llama-3.2" in model_name:
                supports = True
            # Llama 3.0 may support it in some implementations
            elif "3.0" in model_name or "llama-3" in model_name:
                # Check if it's 3.0 or 3.1+ by looking for version indicators
                # Default to True for Llama 3.x as most support it
                supports = True
            # Llama 2 and older don't support it
            else:
                supports = False
        
        elif "mistral" in architecture or "mistral" in model_name:
            # Mistral 7B v0.2+ supports function calling
            # Check for version indicators
            if "v0.2" in model_name or "v0.3" in model_name or "0.2" in model_name or "0.3" in model_name:
                supports = True
            # Newer Mistral models (without version) likely support it
            elif "mistral-7b" not in model_name or "v0.1" not in model_name:
                # Assume newer versions support it
                supports = True
            else:
                supports = False
        
        elif "mixtral" in architecture or "mixtral" in model_name:
            # Mixtral models generally support function calling
            supports = True
        
        elif "qwen" in architecture or "qwen" in model_name:
            # Qwen 2.5+ and Qwen 2+ support function calling
            if "2.5" in model_name or "2-" in model_name or "qwen2" in model_name:
                supports = True
            # Qwen 1.x may not support it
            else:
                supports = False
        
        elif "phi" in architecture or "phi" in model_name:
            # Phi-3.5+ supports function calling
            if "3.5" in model_name or "phi-3.5" in model_name:
                supports = True
            else:
                supports = False
        
        elif "gemma" in architecture or "gemma" in model_name:
            # Gemma 2+ supports function calling
            if "2" in model_name or "gemma-2" in model_name:
                supports = True
            else:
                supports = False
        
        elif "deepseek" in architecture or "deepseek" in model_name:
            # DeepSeek models generally support function calling
            supports = True
        
        elif "yi" in architecture or "yi" in model_name:
            # Yi models (newer versions) support function calling
            # Assume support unless it's clearly an old version
            supports = True
        
        else:
            # Unknown architecture - default to False for safety
            # User can manually enable if needed
            supports = False
            logger.info("Unknown architecture '%s' - assuming no tool calling support", architecture)
        
        return supports
    
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
        # MoE settings
        # Note: n_cpu_moe is not a valid parameter for llama-cpp-python server
        # It was incorrectly documented as "CPU threads for MoE experts"
        # The correct parameter is n_experts_to_use (number of experts to activate per token)
        n_experts_to_use: Optional[int] = None,
        # Deprecated parameters (ignored)
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
            # n_cpu_moe removed - not a valid parameter for llama-cpp-python server
            
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
            logger.warning("n_cpu_moe is not a valid parameter for llama-cpp-python server, ignoring")
            kwargs.pop('n_cpu_moe')
            
        if kwargs:
            logger.warning("Unknown parameters ignored: %s", list(kwargs.keys()))
        
        try:
            # Extract model info for optimization and MoE detection
            from .model_info import ModelInfoExtractor
            from ...config.settings import settings as app_settings
            
            model_file = Path(model_path)
            info_extractor = ModelInfoExtractor(model_file.parent)
            model_info = info_extractor.extract_info(model_file.name, use_cache=True)
            
            # Auto-detect MoE model info
            # Note: n_cpu_moe is not a valid parameter for llama-cpp-python server
            # The correct parameter is n_experts_to_use (number of experts per token)
            moe_info = model_info.get("moe", {})
            is_moe = moe_info.get("is_moe", False)
            num_experts = moe_info.get("num_experts")
            
            # Use provided options or defaults
            effective_n_ctx = n_ctx or settings.llm_context_size
            effective_n_threads = n_threads or settings.llm_n_threads
            effective_n_gpu_layers = n_gpu_layers if n_gpu_layers is not None else self.loader._gpu_layers
            effective_n_batch = n_batch or 512
            effective_use_mmap = use_mmap if use_mmap is not None else True
            effective_use_mlock = use_mlock if use_mlock is not None else False
            
            logger.info("=" * 60)
            logger.info("LOADING MODEL")
            logger.info("=" * 60)
            logger.info("Model: %s", model_path)
            logger.info("Architecture: %s | Parameters: %s", 
                       model_info.get("architecture", "Unknown"),
                       model_info.get("parameters", "Unknown"))
            if is_moe:
                logger.info("MoE Model: %d experts, %d experts per token", 
                           num_experts or 0, moe_info.get("experts_per_token", 2))
                if n_experts_to_use:
                    logger.info("MoE: Using %d experts per token", n_experts_to_use)
            logger.info("Context: %d | Batch: %d | Threads: %d", 
                       effective_n_ctx, effective_n_batch, effective_n_threads)
            logger.info("GPU Layers: %d | Flash Attention: %s", 
                       effective_n_gpu_layers, flash_attn)
            if cache_type_k or cache_type_v:
                logger.info("KV Cache: K=%s V=%s", 
                           cache_type_k or "f16", cache_type_v or "f16")
            logger.info("=" * 60)
            
            # Start server with model
            success = await llm_server.start_server(
                model_path=model_path,
                n_gpu_layers=effective_n_gpu_layers,
                n_ctx=effective_n_ctx,
                n_batch=effective_n_batch,
                n_threads=effective_n_threads,
                n_threads_batch=n_threads_batch,
                use_mlock=effective_use_mlock,
                use_mmap=effective_use_mmap,
                flash_attn=flash_attn,
                main_gpu=main_gpu,
                tensor_split=tensor_split,
                rope_freq_base=rope_freq_base,
                rope_freq_scale=rope_freq_scale,
                rope_scaling_type=rope_scaling_type,
                yarn_ext_factor=yarn_ext_factor,
                yarn_attn_factor=yarn_attn_factor,
                yarn_beta_fast=yarn_beta_fast,
                yarn_beta_slow=yarn_beta_slow,
                yarn_orig_ctx=yarn_orig_ctx,
                cache_type_k=cache_type_k,
                cache_type_v=cache_type_v,
                # n_cpu_moe removed - not a valid parameter
                n_experts_to_use=n_experts_to_use,
            )
            
            if success:
                self.current_model_name = Path(model_path).name
                logger.info("Model loaded successfully: %s", self.current_model_name)
                
                # Detect tool calling support
                self.supports_tool_calling = await self._detect_tool_calling_support(model_path)
                logger.info("Tool calling support: %s", "enabled" if self.supports_tool_calling else "disabled")
                
                return True
            
            logger.error("Failed to start LLM server")
            return False
            
        except Exception as e:
            logger.error("Failed to load model: %s", e, exc_info=True)
            return False
    
    def is_model_loaded(self) -> bool:
        """Check if model is loaded (server running)."""
        return llm_server.is_running()
    
    def get_current_model_path(self) -> Optional[str]:
        """Get the path of the currently loaded model."""
        return llm_server.current_model_path
    
    async def unload_model(self) -> bool:
        """Unload model (stop server)."""
        await llm_server.stop_server()
        self.current_model_name = None
        self.supports_tool_calling = False  # Reset tool calling support
        return True

    def update_settings(self, settings_dict: Dict[str, Any]):
        """Update sampler settings."""
        if "temperature" in settings_dict:
            self.sampler_settings.temperature = float(settings_dict["temperature"])
        if "top_p" in settings_dict:
            self.sampler_settings.top_p = float(settings_dict["top_p"])
        if "top_k" in settings_dict:
            self.sampler_settings.top_k = int(settings_dict["top_k"])
        if "repeat_penalty" in settings_dict:
            self.sampler_settings.repeat_penalty = float(settings_dict["repeat_penalty"])
        if "max_tokens" in settings_dict:
            self.sampler_settings.max_tokens = int(settings_dict["max_tokens"])
        
        # DRY (Dynamic Repetition Penalty) settings
        if "dry_multiplier" in settings_dict:
            self.sampler_settings.dry_multiplier = float(settings_dict["dry_multiplier"])
        if "dry_base" in settings_dict:
            self.sampler_settings.dry_base = float(settings_dict["dry_base"])
        if "dry_allowed_length" in settings_dict:
            self.sampler_settings.dry_allowed_length = int(settings_dict["dry_allowed_length"])
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current sampler settings."""
        return {
            "temperature": self.sampler_settings.temperature,
            "top_p": self.sampler_settings.top_p,
            "top_k": self.sampler_settings.top_k,
            "repeat_penalty": self.sampler_settings.repeat_penalty,
            "max_tokens": self.sampler_settings.max_tokens,
            "dry_multiplier": self.sampler_settings.dry_multiplier,
            "dry_base": self.sampler_settings.dry_base,
            "dry_allowed_length": self.sampler_settings.dry_allowed_length
        }
    
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
        """Build system prompt from base prompt, character card, and user profile."""
        prompt_parts = []
        
        if self.character_card:
            if self.character_card.name:
                prompt_parts.append(f"You are {self.character_card.name}.")
            if self.character_card.personality:
                prompt_parts.append(f"Personality: {self.character_card.personality}")
            if self.character_card.background:
                prompt_parts.append(f"Background: {self.character_card.background}")
            if self.character_card.instructions:
                prompt_parts.append(f"Instructions: {self.character_card.instructions}")
            prompt_parts.append("")
        
        if self.user_profile:
            prompt_parts.append("About the user:")
            if self.user_profile.name:
                prompt_parts.append(f"- Name: {self.user_profile.name}")
            if self.user_profile.about:
                prompt_parts.append(f"- About: {self.user_profile.about}")
            if self.user_profile.preferences:
                prompt_parts.append(f"- Preferences: {self.user_profile.preferences}")
            prompt_parts.append("")
        
        prompt_parts.append(self.system_prompt)
        return "\n".join(prompt_parts)
    
    def get_default_load_options(self) -> Dict[str, Any]:
        """Get default model load options."""
        return {
            "n_gpu_layers": self.loader._gpu_layers if hasattr(self.loader, '_gpu_layers') else -1,
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
