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
from .vector_memory_settings import (
    should_save_vector_memory,
    should_read_vector_memory,
    get_vector_memory_settings as get_vector_memory_settings_impl,
    set_vector_memory_settings as set_vector_memory_settings_impl,
    apply_global_settings_to_all_conversations,
    get_conversation_vector_memory_settings as get_conversation_vector_memory_settings_impl,
    set_conversation_vector_memory_settings as set_conversation_vector_memory_settings_impl
)
from .conversation_ops import store_conversation_with_vector
from ...config.settings import settings

logger = logging.getLogger(__name__)


class MemoryStore:
    """Persistent memory storage with fast file-based storage and vector search."""
    
    def __init__(self):
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
    
    async def _get_current_user_profile_id(self) -> Optional[str]:
        """Get the current active user profile ID.
        
        Returns:
            User profile ID or None if no profile is set
        """
        try:
            return await self.user_profile_store.get_current_user_profile_id()
        except Exception as e:
            logger.warning(f"Error getting current user profile ID: {e}")
            return None
    
    async def initialize(self):
        """Initialize memory store resources."""
        # Clean up old SQLite data (we use file store now)
        await self._cleanup_old_data()
        
    async def _cleanup_old_data(self):
        """Remove old SQLite database files - we use file store only now."""
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
        user_profile_id = await self._get_current_user_profile_id()
        await store_conversation_with_vector(
            file_store=self.file_store,
            vector_store=self.vector_store,
            conversation_id=conversation_id,
            messages=messages,
            name=name,
            should_save_vector_func=lambda cid: self._should_save_vector_memory(cid),
            user_profile_id=user_profile_id
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
        
        user_profile_id = await self._get_current_user_profile_id()
        return await self.retriever.retrieve_context(
            query=query,
            top_k=top_k,
            exclude_conversation_id=exclude_conversation_id,
            user_profile_id=user_profile_id
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
            
            # Clear vector store (clear all user collections)
            try:
                if self.vector_store.client and self.vector_store.store_type == "chromadb":
                    # ChromaDB: Delete all collections (each user has their own collection)
                    try:
                        # Get all collections and delete them
                        collections = self.vector_store.client.list_collections()
                        deleted_count = 0
                        for coll in collections:
                            try:
                                count = coll.count()
                                self.vector_store.client.delete_collection(name=coll.name)
                                deleted_count += count
                                logger.info(f"Deleted collection {coll.name} with {count} entries")
                            except Exception as e:
                                logger.warning(f"Could not delete collection {coll.name}: {e}")
                        
                        # Clear cache
                        self.vector_store._collections_cache.clear()
                        self.vector_store.collection = None
                        
                        logger.info(f"Deleted {deleted_count} total entries from vector store across all users")
                        results["vector_store_cleared"] = True
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
            user_profile_id = await self._get_current_user_profile_id()
            await self.vector_store.delete_conversation(conversation_id, user_profile_id=user_profile_id)
            
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

    async def update_message(
        self,
        conversation_id: str,
        message_index: int,
        new_content: str,
        role: Optional[str] = None
    ) -> bool:
        """Update a message in a conversation and update vector store.
        
        Args:
            conversation_id: Conversation ID
            message_index: Index of message to update
            new_content: New message content
            role: Optional role to update
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the conversation to find the old message
            messages = await self.file_store.get_conversation(conversation_id)
            if not messages or message_index >= len(messages):
                return False
            
            old_message = messages[message_index]
            old_content = old_message.get("content", "")
            old_timestamp = old_message.get("timestamp")
            
            # Update in file store
            success = await self.file_store.update_message(
                conversation_id=conversation_id,
                message_index=message_index,
                new_content=new_content,
                role=role
            )
            
            if not success:
                return False
            
            # Update vector store: delete old entry and add new one
            if old_content and old_timestamp:
                # Parse timestamp
                if isinstance(old_timestamp, str):
                    try:
                        old_timestamp_dt = datetime.fromisoformat(old_timestamp.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        old_timestamp_dt = datetime.utcnow()
                elif not isinstance(old_timestamp, datetime):
                    old_timestamp_dt = datetime.utcnow()
                else:
                    old_timestamp_dt = old_timestamp
                
                # Find and delete old vector entry
                user_profile_id = await self._get_current_user_profile_id()
                collection = self.vector_store._get_collection(user_profile_id)
                if collection and self.vector_store.store_type == "chromadb":
                    try:
                        # Get all messages for this conversation
                        results = collection.get(
                            where={"conversation_id": conversation_id},
                            include=["documents", "metadatas"]
                        )
                        
                        # Find matching entry by content
                        for i, doc in enumerate(results.get("documents", [])):
                            if doc == old_content:
                                # Check timestamp if available
                                meta = results.get("metadatas", [])[i] if i < len(results.get("metadatas", [])) else {}
                                stored_timestamp = meta.get("timestamp", "")
                                
                                # Delete if content matches (and optionally timestamp)
                                if not stored_timestamp or stored_timestamp.startswith(old_timestamp_dt.isoformat()[:19]):
                                    collection.delete(ids=[results["ids"][i]])
                                    logger.info(f"Deleted old vector entry for updated message in conversation {conversation_id}")
                                    break
                    except Exception as e:
                        logger.warning(f"Error deleting old vector entry: {e}")
            
            # Add new vector entry
            if new_content and new_content.strip():
                new_timestamp = datetime.utcnow()
                user_profile_id = await self._get_current_user_profile_id()
                await self.vector_store.add_message(
                    conversation_id=conversation_id,
                    message=new_content,
                    role=role or old_message.get("role", "user"),
                    timestamp=new_timestamp,
                    user_profile_id=user_profile_id
                )
                logger.info(f"Added updated message to vector store for conversation {conversation_id}")
            
            return True
        except Exception as e:
            logger.error(f"Error updating message: {e}", exc_info=True)
            return False
    
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
        """Check if vector memory saving is enabled for a conversation."""
        return await should_save_vector_memory(
            conversation_id,
            self.file_store.conversations_dir,
            self.get_setting
        )
    
    async def _should_read_vector_memory(self, conversation_id: Optional[str]) -> bool:
        """Check if vector memory reading is enabled for a conversation."""
        return await should_read_vector_memory(
            conversation_id,
            self.file_store.conversations_dir,
            self.get_setting
        )
    
    async def get_vector_memory_settings(self) -> Dict[str, Any]:
        """Get global vector memory settings."""
        return await get_vector_memory_settings_impl(self.get_setting)
    
    async def set_vector_memory_settings(self, settings: Dict[str, Any]):
        """Set global vector memory settings."""
        await set_vector_memory_settings_impl(
            settings,
            self.set_setting,
            self.file_store,
            lambda s: apply_global_settings_to_all_conversations(
                s,
                self.file_store.conversations_dir,
                self.file_store.list_conversations
            )
        )
    
    async def get_conversation_vector_memory_settings(self, conversation_id: str) -> Dict[str, Any]:
        """Get per-conversation vector memory settings from file store."""
        return await get_conversation_vector_memory_settings_impl(
            conversation_id,
            self.file_store.conversations_dir
        )
    
    async def set_conversation_vector_memory_settings(
        self, 
        conversation_id: str, 
        settings: Dict[str, Any]
    ):
        """Set per-conversation vector memory settings in file store."""
        await set_conversation_vector_memory_settings_impl(
            conversation_id,
            settings,
            self.file_store.conversations_dir
        )
    
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