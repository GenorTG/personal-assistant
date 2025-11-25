"""LLM model manager using OpenAI-compatible server."""
from typing import Optional, List, Dict, Any, AsyncIterator
from pathlib import Path
import logging
from datetime import datetime
import json

from openai import AsyncOpenAI
from .loader import LLMLoader
from .downloader import ModelDownloader
from .sampler import SamplerSettings
from ..server import llm_server
from ..config import settings

logger = logging.getLogger(__name__)


class LLMManager:
    """Manages LLM models and inference via local OpenAI-compatible server."""
    
    def __init__(self, tool_registry: Optional[Any] = None):
        self.loader = LLMLoader()  # Kept for hardware detection
        self.downloader = ModelDownloader()
        self.client: Optional[AsyncOpenAI] = None
        self.current_model_name: Optional[str] = None
        
        # Settings
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
        
        # State tracking
        self._last_request_time = None
        self._last_request_info = None
    
    def set_tool_registry(self, tool_registry: Any) -> None:
        """Set the tool registry for function calling."""
        self.tool_registry = tool_registry
        logger.info("Tool registry set for LLM Manager")
    
    async def load_model(
        self, 
        model_path: str,
        n_ctx: Optional[int] = None,
        n_threads: Optional[int] = None,
        n_gpu_layers: Optional[int] = None,
        use_flash_attention: Optional[bool] = None,
        flash_attn: bool = False, # Changed from use_flash_attention
        use_mmap: Optional[bool] = None,
        use_mlock: Optional[bool] = None,
        n_batch: Optional[int] = None,
        n_predict: Optional[int] = None,
        rope_freq_base: Optional[float] = None,
        rope_freq_scale: Optional[float] = None,
        main_gpu: int = 0,
        tensor_split: Optional[List[float]] = None,
        n_cpu_moe: Optional[int] = None,
        cache_type_k: Optional[str] = None,
        cache_type_v: Optional[str] = None
    ) -> bool:
        """
        Load a model via the server.
        
        Args:
            model_path: Path to GGUF model file
            n_gpu_layers: Number of layers to offload to GPU
            n_ctx: Context window size
            n_batch: Batch size for prompt processing
            n_threads: Number of CPU threads
            use_mlock: Lock model in memory
            use_mmap: Use memory mapping
            flash_attn: Use Flash Attention
            main_gpu: Main GPU ID
            tensor_split: Split across GPUs
            n_cpu_moe: Number of experts to offload to CPU
            cache_type_k: KV cache data type for K
            cache_type_v: KV cache data type for V
        """
        try:
            # Use provided options or defaults
            effective_n_ctx = n_ctx or settings.llm_context_size
            effective_n_threads = n_threads or settings.llm_n_threads
            effective_n_gpu_layers = n_gpu_layers if n_gpu_layers is not None else self.loader._gpu_layers
            
            logger.info("=" * 60)
            logger.info("STARTING LLM SERVER")
            logger.info(f"Model: {model_path}")
            logger.info(f"Context: {effective_n_ctx}, GPU Layers: {effective_n_gpu_layers}")
            logger.info("=" * 60)
            
            # Start server with model
            success = await llm_server.start_server(
                model_path=model_path,
                n_gpu_layers=effective_n_gpu_layers,
                n_ctx=effective_n_ctx,
                n_batch=n_batch or 512,
                n_threads=effective_n_threads,
                use_mlock=use_mlock or False,
                use_mmap=use_mmap if use_mmap is not None else True,
                flash_attn=flash_attn,
                main_gpu=main_gpu,
                tensor_split=tensor_split,
                n_cpu_moe=n_cpu_moe,
                cache_type_k=cache_type_k,
                cache_type_v=cache_type_v
            )
            
            if success:
                self.current_model_name = Path(model_path).name
                # Initialize OpenAI client
                self.client = AsyncOpenAI(
                    base_url=f"http://{llm_server.host}:{llm_server.port}/v1",
                    api_key="sk-no-key-required"
                )
                logger.info("LLM Manager connected to server")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}", exc_info=True)
            return False
    
    def is_model_loaded(self) -> bool:
        """Check if model is loaded (server running)."""
        return llm_server.is_running() and self.client is not None
    
    def get_current_model_path(self) -> Optional[str]:
        """Get the path of the currently loaded model."""
        return llm_server.current_model_path
    
    async def unload_model(self) -> bool:
        """Unload model (stop server)."""
        await llm_server.stop_server()
        self.client = None
        self.current_model_name = None
        return True
        
    async def generate_response(
        self,
        message: str,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate response using OpenAI API."""
        if not self.is_model_loaded():
            raise RuntimeError("No model loaded")
            
        # Track request
        self._last_request_time = datetime.utcnow().isoformat()
        
        # Build messages
        messages = self._build_messages(message, history, context, tool_results)
        
        # Prepare tools
        tools = None
        if self.tool_registry:
            tool_list = self.tool_registry.list_tools()
            if tool_list:
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": t.get("schema", {})
                        }
                    }
                    for t in tool_list
                ]

        try:
            if stream:
                # Return stream iterator
                response_stream = await self.client.chat.completions.create(
                    model=self.current_model_name,
                    messages=messages,
                    temperature=self.sampler_settings.temperature,
                    top_p=self.sampler_settings.top_p,
                    max_tokens=self.sampler_settings.max_tokens,
                    frequency_penalty=self.sampler_settings.repeat_penalty, # Map repeat to frequency penalty approx
                    tools=tools,
                    stream=True
                )
                return {
                    "stream": self._process_stream(response_stream),
                    "tool_calls": []
                }
            else:
                # Standard generation
                response = await self.client.chat.completions.create(
                    model=self.current_model_name,
                    messages=messages,
                    temperature=self.sampler_settings.temperature,
                    top_p=self.sampler_settings.top_p,
                    max_tokens=self.sampler_settings.max_tokens,
                    frequency_penalty=self.sampler_settings.repeat_penalty,
                    tools=tools,
                    stream=False
                )
                
                message_content = response.choices[0].message.content or ""
                tool_calls_data = response.choices[0].message.tool_calls
                
                parsed_tool_calls = []
                if tool_calls_data:
                    for tc in tool_calls_data:
                        parsed_tool_calls.append({
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments),
                            "id": tc.id
                        })
                
                return {
                    "response": message_content,
                    "tool_calls": parsed_tool_calls
                }
                
        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Generation failed: {str(e)}") from e

    async def _process_stream(self, stream):
        """Process OpenAI stream into simple text chunks."""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _build_messages(
        self,
        message: str,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        tool_results: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Build message list for OpenAI API."""
        messages = []
        
        # System prompt
        system_content = self._build_system_prompt()
        
        # Add context to system prompt or as first user message
        if context and context.get("retrieved_messages"):
            context_str = "\n\nRelevant context:\n" + "\n".join(
                f"- {msg}" for msg in context["retrieved_messages"][:5]
            )
            system_content += context_str
            
        messages.append({"role": "system", "content": system_content})
        
        # History
        if history:
            for msg in history[-10:]: # Limit history
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Tool results (if any) - need to match previous tool calls
        # This is simplified; robust tool handling requires tracking tool call IDs
        # For now, we append tool results as system/user info if not strictly following OpenAI tool flow
        if tool_results:
            for res in tool_results:
                messages.append({
                    "role": "tool", 
                    "tool_call_id": res.get("id", "unknown"),
                    "content": str(res.get("result", ""))
                })

        # Current message
        messages.append({"role": "user", "content": message})
        
        return messages

    # ... (Keep existing helper methods: update_settings, get_settings, etc.) ...
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
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current sampler settings."""
        return {
            "temperature": self.sampler_settings.temperature,
            "top_p": self.sampler_settings.top_p,
            "top_k": self.sampler_settings.top_k,
            "repeat_penalty": self.sampler_settings.repeat_penalty,
            "max_tokens": self.sampler_settings.max_tokens
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
        from ..schemas import CharacterCard
        if character_card:
            self.character_card = CharacterCard(**character_card)
        else:
            self.character_card = None
            
    def update_user_profile(self, user_profile: Dict[str, Any]) -> None:
        from ..schemas import UserProfile
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
