"""Message building utilities for chat."""
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MessageBuilder:
    """Builds message lists for LLM API requests."""
    
    @staticmethod
    def build_messages(
        message: str,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        system_prompt: str
    ) -> List[Dict[str, Any]]:
        """Build message list for OpenAI API.
        
        Args:
            message: Current user message
            history: Conversation history
            context: Retrieved context from memory
            system_prompt: System prompt content
            
        Returns:
            List of message dictionaries for API request
        """
        messages = []
        
        # Build system content with context
        system_content = system_prompt
        
        # Add context to system prompt
        if context and context.get("retrieved_messages"):
            context_str = "\n\nRelevant context from past conversations:\n" + "\n".join(
                f"- {msg}" for msg in context["retrieved_messages"][:5]
            )
            system_content += context_str
        
        messages.append({"role": "system", "content": system_content})
        
        # Add history (limit to last 10 messages)
        if history:
            for msg in history[-10:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        return messages
    
    @staticmethod
    def build_request_params(
        sampler_params: Optional[Dict[str, Any]],
        default_settings: Any  # SamplerSettings type
    ) -> Dict[str, Any]:
        """Build request parameters for LLM API.
        
        Args:
            sampler_params: Optional sampler parameters from request
            default_settings: Default sampler settings object
            
        Returns:
            Dictionary of request parameters
        """
        if sampler_params:
            request_params = {
                "temperature": sampler_params.get("temperature", default_settings.temperature),
                "top_p": sampler_params.get("top_p", default_settings.top_p),
                "max_tokens": sampler_params.get("max_tokens", default_settings.max_tokens),
            }
            
            # Add optional parameters if present
            optional_params = [
                "top_k", "min_p", "repeat_penalty", "presence_penalty",
                "frequency_penalty", "typical_p", "tfs_z", "mirostat_mode",
                "mirostat_tau", "mirostat_eta"
            ]
            
            for param in optional_params:
                if param in sampler_params:
                    request_params[param] = sampler_params[param]
            
            return request_params
        else:
            # Use saved settings
            return {
                "temperature": default_settings.temperature,
                "top_p": default_settings.top_p,
                "top_k": default_settings.top_k,
                "max_tokens": default_settings.max_tokens,
                "repeat_penalty": default_settings.repeat_penalty,
            }

