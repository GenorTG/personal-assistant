"""Fast file-based conversation storage using JSON files."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import aiofiles
import logging

logger = logging.getLogger(__name__)


class FileConversationStore:
    """Fast file-based storage for conversations using JSON files.
    
    Structure:
    - conversations/{id}.json - Each conversation as a JSON file
    - conversations/index.json - Metadata index for fast listing
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.conversations_dir = self.base_dir / "conversations"
        self.index_file = self.conversations_dir / "index.json"
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self._index_cache: Optional[Dict[str, Any]] = None
    
    async def _load_index(self) -> Dict[str, Any]:
        """Load the conversations index file."""
        if self._index_cache is not None:
            return self._index_cache
        
        if not self.index_file.exists():
            self._index_cache = {"conversations": {}}
            return self._index_cache
        
        try:
            async with aiofiles.open(self.index_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._index_cache = json.loads(content)
                return self._index_cache
        except Exception as e:
            logger.error(f"Error loading index: {e}")
            self._index_cache = {"conversations": {}}
            return self._index_cache
    
    async def _save_index(self):
        """Save the conversations index file."""
        try:
            async with aiofiles.open(self.index_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._index_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving index: {e}")
    
    async def get_conversation(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get messages from a conversation file.
        
        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages (None = all)
        
        Returns:
            List of messages or None if not found
        """
        conv_file = self.conversations_dir / f"{conversation_id}.json"
        
        if not conv_file.exists():
            return None
        
        try:
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                messages = data.get("messages", [])
                
                if limit:
                    messages = messages[-limit:]  # Get last N messages
                
                return messages
        except Exception as e:
            logger.error(f"Error reading conversation {conversation_id}: {e}")
            return None
    
    async def save_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Save a conversation to a JSON file.
        
        Args:
            conversation_id: Conversation ID
            messages: List of messages
            name: Conversation name
            metadata: Additional metadata
        """
        conv_file = self.conversations_dir / f"{conversation_id}.json"
        
        # Prepare conversation data
        now = datetime.utcnow().isoformat()
        
        # Load existing vector memory settings if file exists
        vector_memory = {"custom": False, "save_enabled": None, "read_enabled": None}
        if conv_file.exists():
            try:
                async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                    existing_data = json.loads(await f.read())
                    vector_memory = existing_data.get("vector_memory", vector_memory)
            except Exception:
                pass
        
        # Update vector memory from metadata if provided
        if metadata:
            if "vector_memory_custom" in metadata:
                vector_memory["custom"] = metadata.get("vector_memory_custom", False)
            if "vector_memory_save_enabled" in metadata:
                vector_memory["save_enabled"] = metadata.get("vector_memory_save_enabled")
            if "vector_memory_read_enabled" in metadata:
                vector_memory["read_enabled"] = metadata.get("vector_memory_read_enabled")
        
        conv_data = {
            "conversation_id": conversation_id,
            "name": name,
            "messages": messages,
            "created_at": metadata.get("created_at") if metadata else now,
            "updated_at": now,
            "message_count": len(messages),
            "metadata": metadata or {},
            "vector_memory": vector_memory
        }
        
        try:
            # Save conversation file
            async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(conv_data, indent=2, default=str))
            
            # Update index
            index = await self._load_index()
            index["conversations"][conversation_id] = {
                "conversation_id": conversation_id,
                "name": name,
                "created_at": conv_data["created_at"],
                "updated_at": conv_data["updated_at"],
                "message_count": len(messages),
                "pinned": metadata.get("pinned", False) if metadata else False
            }
            self._index_cache = index
            await self._save_index()
            
            return True
        except Exception as e:
            logger.error(f"Error saving conversation {conversation_id}: {e}")
            return False
    
    async def list_conversations(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all conversations from index (very fast).
        
        Automatically removes stale entries (indexed but file missing).
        
        Args:
            limit: Maximum number to return
            offset: Offset for pagination
        
        Returns:
            List of conversation metadata
        """
        index = await self._load_index()
        conversations = list(index.get("conversations", {}).values())
        
        # Clean up stale entries (files that don't exist)
        valid_convs = []
        stale_ids = []
        for conv_data in conversations:
            conv_id = conv_data.get("conversation_id")
            if not conv_id:
                continue
            conv_file = self.conversations_dir / f"{conv_id}.json"
            if conv_file.exists():
                valid_convs.append(conv_data)
            else:
                stale_ids.append(conv_id)
        
        # Remove stale entries from index
        if stale_ids:
            logger.warning(f"Removing {len(stale_ids)} stale conversation entries from index")
            for stale_id in stale_ids:
                if stale_id in index.get("conversations", {}):
                    del index["conversations"][stale_id]
            self._index_cache = index
            await self._save_index()
        
        conversations = valid_convs
        
        # Sort by pinned first, then updated_at descending
        conversations.sort(
            key=lambda x: (
                not x.get("pinned", False),
                -(datetime.fromisoformat(x.get("updated_at", "")).timestamp() 
                  if x.get("updated_at") else 0)
            ),
            reverse=False
        )
        
        # Apply pagination
        if limit:
            conversations = conversations[offset:offset + limit]
        elif offset:
            conversations = conversations[offset:]
        
        return conversations
    
    async def clear_all(self) -> int:
        """Clear all conversations (delete all files and reset index).
        
        Returns:
            Number of conversations deleted
        """
        index = await self._load_index()
        count = len(index.get("conversations", {}))
        
        # Delete all conversation files
        if self.conversations_dir.exists():
            for conv_file in self.conversations_dir.glob("*.json"):
                if conv_file.name != "index.json":
                    try:
                        conv_file.unlink()
                    except Exception as e:
                        logger.error(f"Error deleting {conv_file}: {e}")
        
        # Reset index
        self._index_cache = {"conversations": {}}
        await self._save_index()
        
        logger.info(f"Cleared all {count} conversations")
        return count
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation file and remove from index."""
        conv_file = self.conversations_dir / f"{conversation_id}.json"
        
        try:
            # Delete file
            if conv_file.exists():
                conv_file.unlink()
            
            # Remove from index
            index = await self._load_index()
            if conversation_id in index.get("conversations", {}):
                del index["conversations"][conversation_id]
                self._index_cache = index
                await self._save_index()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            return False
    
    async def update_conversation_metadata(
        self,
        conversation_id: str,
        name: Optional[str] = None,
        pinned: Optional[bool] = None,
        **kwargs
    ) -> bool:
        """Update conversation metadata in index and file."""
        index = await self._load_index()
        
        if conversation_id not in index.get("conversations", {}):
            return False
        
        # Update index
        conv_meta = index["conversations"][conversation_id]
        if name is not None:
            conv_meta["name"] = name
        if pinned is not None:
            conv_meta["pinned"] = pinned
        conv_meta["updated_at"] = datetime.utcnow().isoformat()
        
        # Update conversation file if it exists
        conv_file = self.conversations_dir / f"{conversation_id}.json"
        if conv_file.exists():
            try:
                async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                
                if name is not None:
                    data["name"] = name
                if pinned is not None:
                    data["metadata"]["pinned"] = pinned
                data["updated_at"] = conv_meta["updated_at"]
                
                async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, indent=2, default=str))
            except Exception as e:
                logger.error(f"Error updating conversation file {conversation_id}: {e}")
        
        self._index_cache = index
        await self._save_index()
        return True

