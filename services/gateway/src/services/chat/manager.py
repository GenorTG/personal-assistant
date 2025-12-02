"""Chat conversation manager."""
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
import json
import logging
from ..memory.client import MemoryServiceClient
from ..tools.manager import ToolManager
from ...utils.helpers import generate_conversation_id, get_timestamp
from ...config.settings import settings

logger = logging.getLogger(__name__)


class ChatManager:
    """Manages chat conversations and message flow."""
    
    def __init__(
        self,
        service_manager: Any,  # ServiceManager instance
        memory_store: MemoryServiceClient,
        tool_manager: Optional[ToolManager] = None
    ):
        logger.info("      Setting up ChatManager...")
        self.service_manager = service_manager
        self.memory_store = memory_store
        self.tool_manager = tool_manager
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._conversation_names: Dict[str, str] = {}
        self._initialized = False
        logger.info("      ChatManager setup complete (conversations load on first use)")
    
    async def _initialize(self):
        """Initialize by loading conversations from persistent storage."""
        if self._initialized:
            return
        
        # Load conversations from memory store
        stored_conversations = await self.memory_store.list_conversations()
        for conv_data in stored_conversations:
            conv_id = conv_data["conversation_id"]
            # Load messages
            messages = await self.memory_store.get_conversation(conv_id)
            # None means conversation doesn't exist (404), skip it
            if messages is None:
                logger.warning(f"Conversation {conv_id} listed but not found, skipping")
                continue
            # Empty list means conversation exists but has no messages
            if messages:
                self.conversations[conv_id] = messages
            else:
                self.conversations[conv_id] = []
            
            # Store name if available
            if conv_data.get("name"):
                self._conversation_names[conv_id] = conv_data["name"]
        
        self._initialized = True
    
    async def _generate_conversation_name(self, conversation_id: str) -> str:
        """Generate a default name for a conversation like 'Chat 1', 'Chat 2', etc."""
        await self._initialize()
        
        # Count existing conversations to determine next number
        all_conversations = await self.memory_store.list_conversations()
        existing_count = len(all_conversations)
        
        # Find the next available number
        used_numbers = set()
        for conv in all_conversations:
            name = conv.get("name", "")
            if name and name.startswith("Chat "):
                try:
                    num = int(name.replace("Chat ", ""))
                    used_numbers.add(num)
                except ValueError:
                    pass
        
        # Find first unused number
        next_num = 1
        while next_num in used_numbers:
            next_num += 1
        
        name = f"Chat {next_num}"
        self._conversation_names[conversation_id] = name
        await self.memory_store.set_conversation_name(conversation_id, name)
        return name
    
    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        sampler_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a user message and generate response."""
        await self._initialize()
        
        # Generate conversation ID if new
        if not conversation_id:
            conversation_id = generate_conversation_id()
            self.conversations[conversation_id] = []
            # Generate default name
            await self._generate_conversation_name(conversation_id)
        
        # Store user message
        user_msg = {
            "role": "user",
            "content": message,
            "timestamp": get_timestamp()
        }
        self.conversations[conversation_id].append(user_msg)
        
        # Retrieve relevant context from memory (exclude current conversation)
        context = await self.memory_store.retrieve_context(
            query=message,
            exclude_conversation_id=conversation_id,
            conversation_id=conversation_id
        )
        
        # Get conversation history
        history = self.conversations[conversation_id]
        
        # Build messages for OpenAI API
        messages = self._build_messages(message, history, context)
        
        # Get LLM settings - use provided sampler_params or fall back to saved settings
        llm_manager = self.service_manager.llm_manager
        sampler_settings = llm_manager.sampler_settings
        
        # Build request parameters - use sampler_params if provided, otherwise use saved settings
        if sampler_params:
            request_params = {
                "temperature": sampler_params.get("temperature", sampler_settings.temperature),
                "top_p": sampler_params.get("top_p", sampler_settings.top_p),
                "max_tokens": sampler_params.get("max_tokens", sampler_settings.max_tokens),
            }
            
            # Add optional parameters if present
            if "top_k" in sampler_params:
                request_params["top_k"] = sampler_params["top_k"]
            if "min_p" in sampler_params:
                request_params["min_p"] = sampler_params["min_p"]
            if "repeat_penalty" in sampler_params:
                request_params["repeat_penalty"] = sampler_params["repeat_penalty"]
            if "presence_penalty" in sampler_params:
                request_params["presence_penalty"] = sampler_params["presence_penalty"]
            if "frequency_penalty" in sampler_params:
                request_params["frequency_penalty"] = sampler_params["frequency_penalty"]
            if "typical_p" in sampler_params:
                request_params["typical_p"] = sampler_params["typical_p"]
            if "tfs_z" in sampler_params:
                request_params["tfs_z"] = sampler_params["tfs_z"]
            if "mirostat_mode" in sampler_params:
                request_params["mirostat_mode"] = sampler_params["mirostat_mode"]
                if "mirostat_tau" in sampler_params:
                    request_params["mirostat_tau"] = sampler_params["mirostat_tau"]
                if "mirostat_eta" in sampler_params:
                    request_params["mirostat_eta"] = sampler_params["mirostat_eta"]
        else:
            # Use saved settings
            request_params = {
                "temperature": sampler_settings.temperature,
                "top_p": sampler_settings.top_p,
                "top_k": sampler_settings.top_k,
                "max_tokens": sampler_settings.max_tokens,
                "repeat_penalty": sampler_settings.repeat_penalty,
            }
        
        # Prepare tools if available and model supports tool calling
        tools = None
        if self.tool_manager and llm_manager.supports_tool_calling:
            tool_list = await self.tool_manager.list_tools()
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
        elif self.tool_manager and not llm_manager.supports_tool_calling:
            logger.debug("Tool calling disabled - model does not support function calling")
        
        # Call gateway's proxy endpoint (which handles vector store integration)
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Use gateway's own proxy endpoint
                gateway_url = f"http://127.0.0.1:{settings.port}"
                response = await client.post(
                    f"{gateway_url}/v1/chat/completions",
                    json={
                        "model": llm_manager.current_model_name or "current_model",
                        "messages": messages,
                        **request_params,  # Include all sampler parameters
                        "tools": tools,
                        "stream": False
                    },
                    headers={
                        "X-Conversation-ID": conversation_id
                    }
                )
                
                if response.status_code != 200:
                    raise RuntimeError(f"LLM request failed: {response.text}")
                
                response_data = response.json()
                choice = response_data.get("choices", [{}])[0]
                message_obj = choice.get("message", {})
                assistant_content = message_obj.get("content", "")
                tool_calls_data = message_obj.get("tool_calls")
                
                # Parse tool calls
                parsed_tool_calls = []
                if tool_calls_data:
                    for tc in tool_calls_data:
                        parsed_tool_calls.append({
                            "name": tc.get("function", {}).get("name"),
                            "arguments": json.loads(tc.get("function", {}).get("arguments", "{}")),
                            "id": tc.get("id")
                        })
                
                # Handle tool calls if present
                initial_content = assistant_content  # Preserve initial response content
                if parsed_tool_calls and self.tool_manager:
                    tool_results = await self.tool_manager.execute_tools(
                        parsed_tool_calls,
                        conversation_id=conversation_id
                    )
                    # Continue conversation with tool results
                    # Add the assistant's initial message (with tool calls) to conversation history
                    assistant_msg_with_tools = {
                        "role": "assistant",
                        "content": initial_content if initial_content else None,
                        "tool_calls": message_obj.get("tool_calls", [])
                    }
                    messages.append(assistant_msg_with_tools)
                    
                    # Add tool results to messages
                    for res in tool_results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": res.get("id", "unknown"),
                            "content": str(res.get("result", ""))
                        })
                    
                    # Make second request with tool results
                    response2 = await client.post(
                        f"{gateway_url}/v1/chat/completions",
                        json={
                            "model": llm_manager.current_model_name or "current_model",
                            "messages": messages,
                            "temperature": sampler_settings.temperature,
                            "top_p": sampler_settings.top_p,
                            "max_tokens": sampler_settings.max_tokens,
                            "frequency_penalty": sampler_settings.repeat_penalty,
                            "stream": False
                        },
                        headers={
                            "X-Conversation-ID": conversation_id
                        }
                    )
                    
                    if response2.status_code == 200:
                        response_data2 = response2.json()
                        choice2 = response_data2.get("choices", [{}])[0]
                        message_obj2 = choice2.get("message", {})
                        follow_up_content = message_obj2.get("content", "")
                        
                        # Combine initial content with follow-up content
                        # If both exist, combine them naturally
                        if initial_content and follow_up_content:
                            # Combine: initial response + follow-up (which incorporates tool results)
                            assistant_content = f"{initial_content}\n\n{follow_up_content}".strip()
                        elif follow_up_content:
                            # Only follow-up exists (common case)
                            assistant_content = follow_up_content
                        elif initial_content:
                            # Only initial content exists (model responded but tools executed)
                            assistant_content = initial_content
                        else:
                            # No content at all
                            assistant_content = ""
                        
                        parsed_tool_calls = []  # Clear after handling
                
                # Store assistant response
                assistant_msg = {
                    "role": "assistant",
                    "content": assistant_content,
                    "timestamp": get_timestamp()
                }
                self.conversations[conversation_id].append(assistant_msg)
                
                # Note: Vector store saving is handled by the proxy endpoint
                # But we still store in memory for local cache
                conv_name = self._conversation_names.get(conversation_id)
                await self.memory_store.store_conversation(
                    conversation_id=conversation_id,
                    messages=[user_msg, assistant_msg],
                    name=conv_name
                )
                
                return {
                    "response": assistant_content,
                    "conversation_id": conversation_id,
                    "context_used": context.get("retrieved_messages", []),
                    "tool_calls": parsed_tool_calls
                }
        except httpx.ConnectError:
            raise RuntimeError("LLM service not available")
        except Exception as e:
            logger.error(f"Error calling LLM proxy: {e}", exc_info=True)
            raise RuntimeError(f"LLM request failed: {str(e)}") from e
    
    def _build_messages(
        self,
        message: str,
        history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build message list for OpenAI API."""
        messages = []
        
        # Get system prompt from LLM manager
        llm_manager = self.service_manager.llm_manager
        system_content = llm_manager._build_system_prompt()
        
        # Add context to system prompt
        if context and context.get("retrieved_messages"):
            context_str = "\n\nRelevant context from past conversations:\n" + "\n".join(
                f"- {msg}" for msg in context["retrieved_messages"][:5]
            )
            system_content += context_str
        
        messages.append({"role": "system", "content": system_content})
        
        # History
        if history:
            for msg in history[-10:]:  # Limit history
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Current message
        messages.append({"role": "user", "content": message})
        
        return messages
    
    async def get_conversation(self, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get conversation by ID."""
        await self._initialize()
        
        # Try to load from memory if not in cache
        if conversation_id not in self.conversations:
            messages = await self.memory_store.get_conversation(conversation_id)
            if messages is not None:
                self.conversations[conversation_id] = messages
            else:
                return None
        
        return self.conversations.get(conversation_id)
    
    async def list_conversations(self) -> List[str]:
        """List all conversation IDs."""
        await self._initialize()
        return list(self.conversations.keys())

    async def set_conversation_name(self, conversation_id: str, name: str) -> bool:
        """Set the name of a conversation.
        
        Args:
            conversation_id: ID of the conversation
            name: New name for the conversation
            
        Returns:
            True if successful, False if conversation not found
        """
        await self._initialize()
        
        # Check if conversation exists
        if conversation_id not in self.conversations:
            # Try to load it
            messages = await self.memory_store.get_conversation(conversation_id)
            if messages is None:
                return False
            self.conversations[conversation_id] = messages
        
        # Update cache
        self._conversation_names[conversation_id] = name
        
        # Update in database
        try:
            await self.memory_store.set_conversation_name(conversation_id, name)
            return True
        except Exception as e:
            logger.error(f"Error setting conversation name: {e}", exc_info=True)
            return False
    
    async def get_conversation_name(self, conversation_id: str) -> Optional[str]:
        """Get the name of a conversation."""
        await self._initialize()
        if conversation_id in self._conversation_names:
            return self._conversation_names[conversation_id]
        
        # Try to load from database
        conversations = await self.memory_store.list_conversations()
        for conv in conversations:
            if conv["conversation_id"] == conversation_id:
                name = conv.get("name")
                if name:
                    self._conversation_names[conversation_id] = name
                    return name
        
        return None

    async def create_conversation(self) -> str:
        """Create a new conversation.
        
        Returns:
            New conversation ID
        """
        await self._initialize()
        from ...utils.helpers import generate_conversation_id
        conversation_id = generate_conversation_id()
        self.conversations[conversation_id] = []
        # Generate default name
        name = await self._generate_conversation_name(conversation_id)
        # Persist empty conversation to database with name
        await self.memory_store.store_conversation(conversation_id, [], name=name)
        return conversation_id
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation.
        
        Args:
            conversation_id: ID of conversation to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self._initialize()
        
        # Delete from persistent storage
        success = await self.memory_store.delete_conversation(conversation_id)
        
        # Delete from memory cache
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
        if conversation_id in self._conversation_names:
            del self._conversation_names[conversation_id]
        
        return success
    
    async def get_conversation_count(self) -> int:
        """Get total number of conversations."""
        await self._initialize()
        return len(self.conversations)