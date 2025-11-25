"""Chat conversation manager."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..memory.store import MemoryStore
from ..llm.manager import LLMManager
from ..tools.manager import ToolManager
from ...utils.helpers import generate_conversation_id, get_timestamp


class ChatManager:
    """Manages chat conversations and message flow."""
    
    def __init__(
        self,
        llm_manager: LLMManager,
        memory_store: MemoryStore,
        tool_manager: Optional[ToolManager] = None
    ):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("      Setting up ChatManager...")
        self.llm_manager = llm_manager
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
        conversation_id: Optional[str] = None
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
            exclude_conversation_id=conversation_id
        )
        
        # Get conversation history
        history = self.conversations[conversation_id]
        
        # Generate response with LLM
        response_data = await self.llm_manager.generate_response(
            message=message,
            history=history,
            context=context
        )
        
        # Handle tool calls if present
        if response_data.get("tool_calls") and self.tool_manager:
            tool_results = await self.tool_manager.execute_tools(
                response_data["tool_calls"]
            )
            # Continue conversation with tool results
            response_data = await self.llm_manager.generate_response(
                message=message,
                history=history,
                context=context,
                tool_results=tool_results
            )
        
        # Store assistant response
        assistant_msg = {
            "role": "assistant",
            "content": response_data["response"],
            "timestamp": get_timestamp()
        }
        self.conversations[conversation_id].append(assistant_msg)
        
        # Store in memory
        conv_name = self._conversation_names.get(conversation_id)
        await self.memory_store.store_conversation(
            conversation_id=conversation_id,
            messages=[user_msg, assistant_msg],
            name=conv_name
        )
        
        return {
            "response": response_data["response"],
            "conversation_id": conversation_id,
            "context_used": context.get("retrieved_messages", []),
            "tool_calls": response_data.get("tool_calls")
        }
    
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