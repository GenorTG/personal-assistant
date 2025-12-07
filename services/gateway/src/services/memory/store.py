"""Memory storage service."""
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from pathlib import Path
from .vector_store import VectorStore
from .retrieval import ContextRetriever
from .file_store import FileConversationStore
from .settings_store import FileSettingsStore
from .app_settings_store import (
    FileSystemPromptStore,
    FileCharacterCardStore,
    FileUserProfileStore,
    FileSamplerSettingsStore
)
from ...config.settings import settings


class MemoryStore:
    """Persistent memory storage with fast file-based storage and vector search."""
    
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("      Creating FileConversationStore (fast JSON file storage)...")
        self.file_store = FileConversationStore(settings.memory_dir)
        logger.info("      FileConversationStore created")
        logger.info("      Creating FileSettingsStore (fast JSON file storage)...")
        self.settings_store = FileSettingsStore(settings.memory_dir)
        logger.info("      FileSettingsStore created")
        logger.info("      Creating VectorStore (embedding model loads on first use)...")
        self.vector_store = VectorStore()
        logger.info("      VectorStore created")
        logger.info("      Creating ContextRetriever...")
        self.retriever = ContextRetriever(self.vector_store)
        logger.info("      ContextRetriever created")
        logger.info("      Creating app settings stores...")
        self.system_prompt_store = FileSystemPromptStore(settings.memory_dir)
        self.character_card_store = FileCharacterCardStore(settings.memory_dir)
        self.user_profile_store = FileUserProfileStore(settings.memory_dir)
        self.sampler_settings_store = FileSamplerSettingsStore(settings.memory_dir)
        logger.info("      App settings stores created")
    
    async def initialize(self):
        """Initialize memory store resources."""
        # Clean up old SQLite data (we use file store now)
        await self._cleanup_old_data()
        
    async def _cleanup_old_data(self):
        """Remove old SQLite database files - we use file store only now."""
        logger = logging.getLogger(__name__)
        
        try:
            # Delete old conversations.db if it exists (we use file store now)
            old_conv_db = settings.memory_dir / "conversations.db"
            if old_conv_db.exists():
                try:
                    old_conv_db.unlink()
                    logger.info(f"Deleted old conversations database: {old_conv_db}")
                except Exception as e:
                    logger.warning(f"Could not delete old conversations.db: {e}")
            
            # Delete main database if it exists (we use file store now)
            old_db = settings.data_dir / "assistant.db"
            if old_db.exists():
                try:
                    old_db.unlink()
                    logger.info(f"Deleted old database: {old_db}")
                except Exception as e:
                    logger.warning(f"Could not delete old database: {e}")
        except Exception as e:
            logger.warning(f"Error cleaning up old data: {e}")

    async def _initialize_db(self):
        """Legacy method - no longer needed (we use file store now)."""
        # Database is no longer used - all data in file store
        pass
    
    async def store_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        name: Optional[str] = None
    ):
        """Store conversation messages in memory.
        
        Uses fast file-based storage as primary, with vector store for search.
        
        Args:
            conversation_id: Unique conversation identifier
            messages: List of message dictionaries with 'role', 'content', and optionally 'timestamp'
            name: Optional conversation name to set
        """
        # Get existing metadata to preserve created_at and pinned status
        # Load from index to get metadata
        index = await self.file_store._load_index()
        existing_meta = index.get("conversations", {}).get(conversation_id, {})
        
        # Preserve name if not provided
        final_name = name if name else existing_meta.get("name")
        
        # Store in file store (primary storage - fast and simple)
        metadata = {
            "created_at": existing_meta.get("created_at") or datetime.utcnow().isoformat(),
            "pinned": existing_meta.get("pinned", False)
        }
        await self.file_store.save_conversation(
            conversation_id=conversation_id,
            messages=messages,
            name=final_name,
            metadata=metadata
        )
        
        # Check if vector memory saving is enabled for this conversation
        save_enabled = await self._should_save_vector_memory(conversation_id)
        
        # Store in vector store (for semantic search) only if enabled
        if save_enabled:
            for message in messages:
                message_content = message.get("content", "")
                if message_content and message_content.strip():
                    message_timestamp = message.get("timestamp")
                    if isinstance(message_timestamp, str):
                        try:
                            message_timestamp = datetime.fromisoformat(message_timestamp.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            message_timestamp = datetime.utcnow()
                    elif not isinstance(message_timestamp, datetime):
                        message_timestamp = datetime.utcnow()
                    
                    await self.vector_store.add_message(
                        conversation_id=conversation_id,
                        message=message_content,
                        role=message.get("role", "user"),
                        timestamp=message_timestamp
                    )
    
    async def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        exclude_conversation_id: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve relevant context for a query.
        
        Args:
            query: Search query (typically the current user message)
            top_k: Number of results to retrieve (default from settings)
            exclude_conversation_id: Conversation ID to exclude from results
            conversation_id: Conversation ID to check read settings for
        
        Returns:
            Dictionary with retrieved messages, scores, and metadata
        """
        # Check if vector memory reading is enabled
        read_enabled = await self._should_read_vector_memory(conversation_id)
        
        if not read_enabled:
            # Return empty context if reading is disabled
            return {
                "retrieved_messages": [],
                "scores": [],
                "metadata": {}
            }
        
        return await self.retriever.retrieve_context(
            query=query,
            top_k=top_k,
            exclude_conversation_id=exclude_conversation_id
        )
    
    async def get_conversation(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get all messages from a conversation.
        
        Uses file-based storage only (no SQLite).
        
        Args:
            conversation_id: Conversation ID to retrieve
            limit: Maximum number of messages to retrieve (None = all)
        
        Returns:
            List of message dictionaries, or None if conversation not found
        """
        # Use file store only
        return await self.file_store.get_conversation(conversation_id, limit=limit)
    
    async def list_conversations(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all conversations with metadata.
        
        Uses fast file-based index for instant listing, with auto-cleanup of stale entries.
        
        Args:
            limit: Maximum number of conversations to return
            offset: Offset for pagination
        
        Returns:
            List of conversation dictionaries with metadata
        """
        # File store now handles cleanup automatically
        return await self.file_store.list_conversations(limit=limit, offset=offset)
        
    async def reset_all_data(self, keep_models: bool = True) -> Dict[str, Any]:
        """Reset all app data (conversations, settings, vector store).
        
        Args:
            keep_models: If True, keeps downloaded models
        
        Returns:
            Dictionary with counts of deleted items
        """
        logger = logging.getLogger(__name__)
        results = {
            "conversations_deleted": 0,
            "settings_cleared": False,
            "vector_store_cleared": False
        }
        
        try:
            # Clear all conversations
            results["conversations_deleted"] = await self.file_store.clear_all()
            
            # Clear all settings
            settings = await self.settings_store.get_all_settings()
            for key in settings.keys():
                await self.settings_store.delete_setting(key)
            results["settings_cleared"] = True
            
            # Clear vector store
            try:
                if self.vector_store.collection and self.vector_store.store_type == "chromadb":
                    # ChromaDB: Get all IDs and delete them
                    try:
                        # Get all results (this might be slow for large stores, but necessary for reset)
                        all_results = self.vector_store.collection.get()
                        if all_results and "ids" in all_results and all_results["ids"]:
                            self.vector_store.collection.delete(ids=all_results["ids"])
                            logger.info(f"Deleted {len(all_results['ids'])} entries from vector store")
                            results["vector_store_cleared"] = True
                        else:
                            results["vector_store_cleared"] = True  # Already empty
                    except Exception as e:
                        logger.warning(f"Could not clear vector store entries: {e}")
                        results["vector_store_cleared"] = False
                else:
                    results["vector_store_cleared"] = True  # No vector store or not ChromaDB
            except Exception as e:
                logger.error(f"Error clearing vector store: {e}")
                results["vector_store_cleared"] = False
            
            logger.info(f"Reset all app data: {results}")
            return results
        except Exception as e:
            logger.error(f"Error resetting app data: {e}", exc_info=True)
            raise
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages.
        
        Args:
            conversation_id: Conversation ID to delete
        
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            # Delete from vector store
            await self.vector_store.delete_conversation(conversation_id)
            
            # Delete from file store (primary storage)
            return await self.file_store.delete_conversation(conversation_id)
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")
            return False
    
    async def get_conversation_count(self) -> int:
        """Get the total number of conversations.
        
        Returns:
            Number of conversations
        """
        conversations = await self.file_store.list_conversations()
        return len(conversations)
    
    async def set_conversation_name(self, conversation_id: str, name: str) -> bool:
        """Set the name of a conversation.
        
        Args:
            conversation_id: Conversation ID
            name: Name to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.file_store.update_conversation_metadata(
                conversation_id=conversation_id,
                name=name
            )
        except Exception as e:
            logger.error(f"Error setting conversation name: {e}")
            return False
    
    async def set_conversation_pinned(self, conversation_id: str, pinned: bool) -> bool:
        """Set the pinned status of a conversation.
        
        Args:
            conversation_id: Conversation ID
            pinned: Whether to pin the conversation
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.file_store.update_conversation_metadata(
                conversation_id=conversation_id,
                pinned=pinned
            )
        except Exception as e:
            logger.error(f"Error setting conversation pinned status: {e}")
            return False
    
    async def get_message_count(self) -> int:
        """Get the total number of messages across all conversations.
        
        Returns:
            Number of messages
        """
        conversations = await self.file_store.list_conversations()
        total = 0
        for conv in conversations:
            total += conv.get("message_count", 0)
        return total

    async def get_last_entry_timestamp(self) -> Optional[str]:
        """Get timestamp of last entry across all conversations.
        
        Returns:
            ISO timestamp string or None
        """
        conversations = await self.file_store.list_conversations()
        if not conversations:
            return None
        
        # Get most recent updated_at
        latest = max(
            (conv.get("updated_at") for conv in conversations if conv.get("updated_at")),
            default=None
        )
        return latest
    
    async def get_db_size(self) -> int:
        """Get size of file store in bytes (for compatibility).
        
        Returns:
            Size in bytes (0 since we don't use database anymore)
        """
        return 0
    
    async def get_vector_store_stats(self) -> Dict[str, Any]:
        """Get vector store statistics.
        
        Returns:
            Dictionary with vector store stats
        """
        stats = {
            "type": self.vector_store.store_type,
            "initialized": self.vector_store.collection is not None,
            "entry_count": 0,
            "last_entry": None
        }
        
        if self.vector_store.collection:
            try:
                # Get count from ChromaDB collection
                count_result = self.vector_store.collection.count()
                stats["entry_count"] = count_result if count_result else 0
            except Exception:
                stats["entry_count"] = 0
        
        return stats
    
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value from file store.
        
        Args:
            key: Setting key
            default: Default value if setting doesn't exist
            
        Returns:
            Setting value (decrypted if encrypted)
        """
        return await self.settings_store.get_setting(key, default)
    
    async def set_setting(self, key: str, value: str, encrypted: bool = False):
        """Set a setting value in file store.
        
        Args:
            key: Setting key
            value: Setting value
            encrypted: Whether to encrypt the value
        """
        await self.settings_store.set_setting(key, value, encrypted=encrypted)
    
    async def _should_save_vector_memory(self, conversation_id: str) -> bool:
        """Check if vector memory saving is enabled for a conversation.
        
        Checks per-conversation settings first (from file store), then falls back to global settings.
        """
        # Check per-conversation settings from file store
        conv_file = self.file_store.conversations_dir / f"{conversation_id}.json"
        if conv_file.exists():
            try:
                import aiofiles
                import json
                async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    vector_memory = data.get("vector_memory", {})
                    if vector_memory.get("custom", False):
                        save_enabled = vector_memory.get("save_enabled")
                        if save_enabled is not None:
                            return save_enabled
            except Exception:
                pass  # Fall through to global settings
        
        # Fall back to global settings
        global_enabled = await self.get_setting("vector_memory_enabled", "true")
        if global_enabled != "true":
            return False
        
        global_save = await self.get_setting("vector_memory_save_enabled", "true")
        return global_save == "true"
    
    async def _should_read_vector_memory(self, conversation_id: Optional[str]) -> bool:
        """Check if vector memory reading is enabled for a conversation.
        
        Checks per-conversation settings first (from file store), then falls back to global settings.
        """
        if conversation_id:
            # Check per-conversation settings from file store
            conv_file = self.file_store.conversations_dir / f"{conversation_id}.json"
            if conv_file.exists():
                try:
                    import aiofiles
                    import json
                    async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        vector_memory = data.get("vector_memory", {})
                        if vector_memory.get("custom", False):
                            read_enabled = vector_memory.get("read_enabled")
                            if read_enabled is not None:
                                return read_enabled
                except Exception:
                    pass  # Fall through to global settings
        
        # Fall back to global settings
        global_enabled = await self.get_setting("vector_memory_enabled", "true")
        if global_enabled != "true":
            return False
        
        global_read = await self.get_setting("vector_memory_read_enabled", "true")
        return global_read == "true"
    
    async def get_vector_memory_settings(self) -> Dict[str, Any]:
        """Get global vector memory settings."""
        return {
            "vector_memory_enabled": await self.get_setting("vector_memory_enabled", "true") == "true",
            "vector_memory_save_enabled": await self.get_setting("vector_memory_save_enabled", "true") == "true",
            "vector_memory_read_enabled": await self.get_setting("vector_memory_read_enabled", "true") == "true",
            "vector_memory_apply_to_all": await self.get_setting("vector_memory_apply_to_all", "false") == "true"
        }
    
    async def set_vector_memory_settings(self, settings: Dict[str, Any]):
        """Set global vector memory settings."""
        for key, value in settings.items():
            await self.set_setting(key, "true" if value else "false")
        
        # If apply_to_all is True, update all conversations
        if settings.get("vector_memory_apply_to_all", False):
            await self._apply_global_settings_to_all_conversations(settings)
    
    async def _apply_global_settings_to_all_conversations(self, settings: Dict[str, Any]):
        """Apply global vector memory settings to all conversations (update file store)."""
        import aiofiles
        import json
        
        conversations = await self.file_store.list_conversations()
        updated_count = 0
        
        for conv_data in conversations:
            conv_id = conv_data["conversation_id"]
            conv_file = self.file_store.conversations_dir / f"{conv_id}.json"
            
            if not conv_file.exists():
                continue
            
            try:
                # Read conversation file
                async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                
                # Update vector memory settings
                if "vector_memory" not in data:
                    data["vector_memory"] = {}
                
                data["vector_memory"]["custom"] = False  # Reset to use global
                data["vector_memory"]["save_enabled"] = None
                data["vector_memory"]["read_enabled"] = None
                data["updated_at"] = datetime.utcnow().isoformat()
                
                # Write back
                async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, indent=2, default=str))
                
                updated_count += 1
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error updating conversation {conv_id}: {e}")
        
        logger = logging.getLogger(__name__)
        logger.info(f"Applied global vector memory settings to {updated_count} conversations")
    
    async def get_conversation_vector_memory_settings(self, conversation_id: str) -> Dict[str, Any]:
        """Get per-conversation vector memory settings from file store."""
        import aiofiles
        import json
        
        conv_file = self.file_store.conversations_dir / f"{conversation_id}.json"
        
        if not conv_file.exists():
                    return {
                "custom": False,
                "save_enabled": None,
                "read_enabled": None
            }
        
        try:
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                vector_memory = data.get("vector_memory", {})
                return {
                    "custom": vector_memory.get("custom", False),
                    "save_enabled": vector_memory.get("save_enabled"),
                    "read_enabled": vector_memory.get("read_enabled")
                }
        except Exception:
            return {
                "custom": False,
                "save_enabled": None,
                "read_enabled": None
            }
    
    async def set_conversation_vector_memory_settings(
        self, 
        conversation_id: str, 
        settings: Dict[str, Any]
    ):
        """Set per-conversation vector memory settings in file store."""
        import aiofiles
        import json
        
        conv_file = self.file_store.conversations_dir / f"{conversation_id}.json"
        
        if not conv_file.exists():
            raise ValueError(f"Conversation {conversation_id} not found")
        
        custom = settings.get("custom", False)
        save_enabled = settings.get("save_enabled", True) if custom else None
        read_enabled = settings.get("read_enabled", True) if custom else None
        
        try:
            # Read conversation file
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            # Update vector memory settings
            if "vector_memory" not in data:
                data["vector_memory"] = {}
            
            data["vector_memory"]["custom"] = custom
            data["vector_memory"]["save_enabled"] = save_enabled
            data["vector_memory"]["read_enabled"] = read_enabled
            data["updated_at"] = datetime.utcnow().isoformat()
            
            # Write back
            async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error setting vector memory settings for {conversation_id}: {e}")
            raise
    
    # System prompt methods
    async def get_system_prompt(self, prompt_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get system prompt from file store."""
        return await self.system_prompt_store.get_system_prompt(prompt_id=prompt_id)
    
    async def set_system_prompt(
        self,
        content: str,
        name: Optional[str] = None,
        prompt_id: Optional[str] = None,
        is_default: bool = False
    ) -> str:
        """Set system prompt in file store."""
        return await self.system_prompt_store.set_system_prompt(
            content=content,
            name=name,
            prompt_id=prompt_id,
            is_default=is_default
        )
    
    async def list_system_prompts(self) -> List[Dict[str, Any]]:
        """List all system prompts from file store."""
        return await self.system_prompt_store.list_system_prompts()
    
    async def delete_system_prompt(self, prompt_id: str) -> bool:
        """Delete system prompt from file store."""
        return await self.system_prompt_store.delete_system_prompt(prompt_id)
    
    # Character card methods
    async def get_character_card(self) -> Optional[Dict[str, Any]]:
        """Get character card from file store."""
        return await self.character_card_store.get_character_card()
    
    async def set_character_card(self, card: Optional[Dict[str, Any]]) -> bool:
        """Set character card in file store."""
        return await self.character_card_store.set_character_card(card)
    
    # User profile methods
    async def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Get user profile from file store."""
        return await self.user_profile_store.get_user_profile()
    
    async def set_user_profile(self, profile: Optional[Dict[str, Any]]) -> bool:
        """Set user profile in file store."""
        return await self.user_profile_store.set_user_profile(profile)
    
    # Sampler settings methods
    async def get_sampler_settings(self) -> Dict[str, Any]:
        """Get sampler settings from file store."""
        return await self.sampler_settings_store.get_sampler_settings()
    
    async def set_sampler_settings(self, settings: Dict[str, Any]) -> bool:
        """Set sampler settings in file store."""
        return await self.sampler_settings_store.set_sampler_settings(settings)
    
    async def update_sampler_settings(self, updates: Dict[str, Any]) -> bool:
        """Update sampler settings in file store (merge with existing)."""
        return await self.sampler_settings_store.update_sampler_settings(updates)