"""Memory storage service using shared database."""
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiosqlite
from pathlib import Path
from .vector_store import VectorStore
from .retrieval import ContextRetriever
from ..config.settings import settings


class MemoryStore:
    """Persistent memory storage with vector search and SQLite metadata.
    
    Uses shared database at data/assistant.db for all services.
    """
    
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("      Creating VectorStore (embedding model loads on first use)...")
        self.vector_store = VectorStore()
        logger.info("      VectorStore created")
        logger.info("      Creating ContextRetriever...")
        self.retriever = ContextRetriever(self.vector_store)
        logger.info("      ContextRetriever created")
        self.db_path = settings.db_path  # Shared database
        self._db_initialized = False
        logger.info(f"      Database path: {self.db_path}")
    
    async def initialize(self):
        """Initialize memory store resources."""
        await self._initialize_db()

    async def _initialize_db(self):
        """Initialize SQLite database for conversation metadata in shared database."""
        if self._db_initialized:
            return
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Create conversations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    metadata TEXT
                )
            """)
            
            # Add name column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN name TEXT")
            except aiosqlite.OperationalError:
                pass  # Column already exists
            
            # Create messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                )
            """)
            
            # Create indexes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp)
            """)
            
            # Create app_settings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    encrypted INTEGER DEFAULT 0
                )
            """)
            
            # Create system_prompts table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    content TEXT NOT NULL,
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.commit()
        
        # Initialize encryption key
        self._init_encryption_key()
        
        self._db_initialized = True
    
    def _init_encryption_key(self):
        """Initialize encryption key for storing sensitive settings."""
        from cryptography.fernet import Fernet
        key_file = settings.data_dir / ".encryption_key"
        
        if key_file.exists():
            with open(key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
        
        self._fernet = Fernet(key)
    
    async def store_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        name: Optional[str] = None
    ):
        """Store conversation messages in memory.
        
        Args:
            conversation_id: Unique conversation identifier
            messages: List of message dictionaries with 'role', 'content', and optionally 'timestamp'
            name: Optional conversation name to set
        """
        await self._initialize_db()
        
        now = datetime.utcnow().isoformat()
        
        # Store in vector store (for semantic search)
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
                
                # Generate message_id to pass to vector store
                message_id = f"{conversation_id}_{message_timestamp.isoformat()}_{hash(message_content) % 1000000}"
                await self.vector_store.add_message(
                    conversation_id=conversation_id,
                    message=message_content,
                    role=message.get("role", "user"),
                    timestamp=message_timestamp,
                    db_message_id=message_id
                )
        
        # Store metadata in SQLite
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Check if conversation exists to preserve name
            async with db.execute("SELECT name FROM conversations WHERE conversation_id = ?", (conversation_id,)) as cursor:
                existing = await cursor.fetchone()
                existing_name = existing[0] if existing and existing[0] else None
            
            # Use provided name, or preserve existing, or None
            final_name = name if name else existing_name
            
            # Get existing created_at to preserve it
            async with db.execute("SELECT created_at FROM conversations WHERE conversation_id = ?", (conversation_id,)) as cursor:
                existing_created = await cursor.fetchone()
                created_at = existing_created[0] if existing_created and existing_created[0] else now
            
            # Update or create conversation record
            await db.execute("""
                INSERT OR REPLACE INTO conversations 
                (conversation_id, name, created_at, updated_at, message_count)
                VALUES (?, ?, ?, ?, ?)
            """, (conversation_id, final_name, created_at, now, len(messages)))
            
            # Store individual messages
            for message in messages:
                message_id = f"{conversation_id}_{message.get('timestamp', now)}_{hash(message.get('content', '')) % 1000000}"
                message_timestamp = message.get("timestamp", now)
                if isinstance(message_timestamp, datetime):
                    message_timestamp = message_timestamp.isoformat()
                elif not isinstance(message_timestamp, str):
                    message_timestamp = now
                
                await db.execute("""
                    INSERT OR REPLACE INTO messages 
                    (message_id, conversation_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    message_id,
                    conversation_id,
                    message.get("role", "user"),
                    message.get("content", ""),
                    message_timestamp
                ))
            
            await db.commit()
    
    async def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        exclude_conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve relevant context for a query.
        
        Args:
            query: Search query (typically the current user message)
            top_k: Number of results to retrieve (default from settings)
            exclude_conversation_id: Conversation ID to exclude from results
        
        Returns:
            Dictionary with retrieved messages, scores, and metadata
        """
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
        
        Args:
            conversation_id: Conversation ID to retrieve
            limit: Maximum number of messages to retrieve (None = all)
        
        Returns:
            List of message dictionaries, or None if conversation not found
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            
            query = """
                SELECT role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            async with db.execute(query, (conversation_id,)) as cursor:
                rows = await cursor.fetchall()
                
                if not rows:
                    return None
                
                return [
                    {
                        "role": row["role"],
                        "content": row["content"],
                        "timestamp": row["timestamp"]
                    }
                    for row in rows
                ]
    
    async def list_conversations(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all conversations with metadata.
        
        Args:
            limit: Maximum number of conversations to return
            offset: Offset for pagination
        
        Returns:
            List of conversation dictionaries with metadata
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            
            query = """
                SELECT conversation_id, name, created_at, updated_at, message_count
                FROM conversations
                ORDER BY updated_at DESC
            """
            
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"
            
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                
                return [
                    {
                        "conversation_id": row["conversation_id"],
                        "name": row["name"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "message_count": row["message_count"]
                    }
                    for row in rows
                ]
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages.
        
        Args:
            conversation_id: Conversation ID to delete
        
        Returns:
            True if deletion was successful, False otherwise
        """
        await self._initialize_db()
        
        try:
            # Delete from vector store
            await self.vector_store.delete_conversation(conversation_id)
            
            # Delete from SQLite
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
                await db.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
                await db.commit()
            
            return True
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            return False
    
    async def get_conversation_count(self) -> int:
        """Get the total number of conversations.
        
        Returns:
            Number of conversations
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute("SELECT COUNT(*) as count FROM conversations") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    
    async def set_conversation_name(self, conversation_id: str, name: str) -> bool:
        """Set the name of a conversation.
        
        Args:
            conversation_id: Conversation ID
            name: Name to set
            
        Returns:
            True if successful, False otherwise
        """
        await self._initialize_db()
        
        try:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute(
                    "UPDATE conversations SET name = ? WHERE conversation_id = ?",
                    (name, conversation_id)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"Error setting conversation name: {e}")
            return False
    
    async def update_message(
        self,
        conversation_id: str,
        message_index: int,
        new_content: str,
        role: Optional[str] = None
    ) -> bool:
        """Update a message in a conversation by index.
        
        Args:
            conversation_id: Conversation ID
            message_index: Zero-based index of message to update
            new_content: New message content
            role: Optional new role (if changing role)
            
        Returns:
            True if message was updated, False if not found
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Get all messages for this conversation
            async with db.execute(
                "SELECT message_id, role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp",
                (conversation_id,)
            ) as cursor:
                messages = await cursor.fetchall()
                
            if message_index < 0 or message_index >= len(messages):
                return False
            
            message_id, current_role, old_content, timestamp = messages[message_index]
            role_to_use = role if role else current_role
            
            # Update message in database
            await db.execute(
                "UPDATE messages SET content = ?, role = ? WHERE message_id = ?",
                (new_content, role_to_use, message_id)
            )
            
            # Update vector store if it's a user or assistant message
            if current_role in ("user", "assistant") or role_to_use in ("user", "assistant"):
                # Remove old embedding if it existed
                try:
                    await self.vector_store.delete_message(message_id)
                except Exception:
                    pass  # Message might not be in vector store
                
                # Add new embedding if it's a user or assistant message
                if role_to_use in ("user", "assistant") and new_content.strip():
                    timestamp_obj = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if isinstance(timestamp, str) else (timestamp if isinstance(timestamp, datetime) else datetime.now())
                    # Use the same message_id so we can update it properly
                    await self.vector_store.add_message(
                        conversation_id=conversation_id,
                        message=new_content,
                        role=role_to_use,
                        timestamp=timestamp_obj,
                        db_message_id=message_id
                    )
            
            # Update conversation timestamp
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (datetime.now().isoformat(), conversation_id)
            )
            
            await db.commit()
            return True
    
    async def delete_last_message(self, conversation_id: str) -> bool:
        """Delete the last message from a conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            True if message was deleted, False if conversation not found or empty
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Get the last message
            async with db.execute(
                "SELECT message_id, role FROM messages WHERE conversation_id = ? ORDER BY timestamp DESC LIMIT 1",
                (conversation_id,)
            ) as cursor:
                result = await cursor.fetchone()
                
            if not result:
                return False
            
            message_id, role = result
            
            # Delete from vector store if it's a user or assistant message
            if role in ("user", "assistant"):
                try:
                    await self.vector_store.delete_message(message_id)
                except Exception:
                    pass  # Message might not be in vector store
            
            # Delete from database
            await db.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
            
            # Update conversation message count and timestamp
            await db.execute(
                "UPDATE conversations SET message_count = (SELECT COUNT(*) FROM messages WHERE conversation_id = ?), updated_at = ? WHERE conversation_id = ?",
                (conversation_id, datetime.now().isoformat(), conversation_id)
            )
            
            await db.commit()
            return True
    
    async def truncate_conversation_at(
        self,
        conversation_id: str,
        message_index: int
    ) -> bool:
        """Truncate conversation at a specific message index (delete all messages after this index).
        
        Args:
            conversation_id: Conversation ID
            message_index: Keep messages up to and including this index (0-based)
            
        Returns:
            True if truncation was successful
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            # Get all messages
            async with db.execute(
                "SELECT message_id, role FROM messages WHERE conversation_id = ? ORDER BY timestamp",
                (conversation_id,)
            ) as cursor:
                messages = await cursor.fetchall()
                
            if message_index < 0 or message_index >= len(messages):
                return False
            
            # Get message IDs to delete (everything after message_index)
            messages_to_delete = [msg[0] for msg in messages[message_index + 1:]]
            
            if not messages_to_delete:
                return True  # Nothing to delete
            
            # Delete from vector store
            for message_id, role in messages[message_index + 1:]:
                if role in ("user", "assistant"):
                    try:
                        await self.vector_store.delete_message(message_id)
                    except Exception:
                        pass  # Message might not be in vector store
            
            # Delete from database
            placeholders = ",".join("?" * len(messages_to_delete))
            await db.execute(
                f"DELETE FROM messages WHERE message_id IN ({placeholders})",
                messages_to_delete
            )
            
            # Update conversation message count and timestamp
            await db.execute(
                "UPDATE conversations SET message_count = (SELECT COUNT(*) FROM messages WHERE conversation_id = ?), updated_at = ? WHERE conversation_id = ?",
                (conversation_id, datetime.now().isoformat(), conversation_id)
            )
            
            await db.commit()
            return True

    async def get_message_count(self) -> int:
        """Get the total number of messages.
        
        Returns:
            Number of messages
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute("SELECT COUNT(*) as count FROM messages") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_last_entry_timestamp(self) -> Optional[str]:
        """Get timestamp of last entry in memory database.
        
        Returns:
            ISO timestamp string or None
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute("SELECT MAX(timestamp) as last_entry FROM messages") as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] else None
    
    async def get_db_size(self) -> int:
        """Get size of database file in bytes.
        
        Returns:
            Size in bytes
        """
        if self.db_path.exists():
            return self.db_path.stat().st_size
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
        """Get a setting value from the database.
        
        Args:
            key: Setting key
            default: Default value if setting doesn't exist
            
        Returns:
            Setting value (decrypted if encrypted)
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                "SELECT value, encrypted FROM app_settings WHERE key = ?",
                (key,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if row is None:
                    return default
                
                value, encrypted = row
                
                if encrypted:
                    # Decrypt the value
                    value = self._fernet.decrypt(value.encode()).decode()
                
                return value
    
    async def set_setting(self, key: str, value: str, encrypted: bool = False):
        """Set a setting value in the database.
        
        Args:
            key: Setting key
            value: Setting value
            encrypted: Whether to encrypt the value
        """
        await self._initialize_db()
        
        if encrypted:
            # Encrypt the value
            value = self._fernet.encrypt(value.encode()).decode()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO app_settings (key, value, encrypted)
                VALUES (?, ?, ?)
                """,
                (key, value, 1 if encrypted else 0)
            )
            await db.commit()
    
    # System prompt management methods
    async def get_system_prompt(self, prompt_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a system prompt by ID, or the default prompt.
        
        Args:
            prompt_id: Prompt ID to retrieve (None = get default)
        
        Returns:
            Dictionary with prompt data, or None if not found
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            
            if prompt_id:
                async with db.execute(
                    "SELECT id, name, content, is_default, created_at, updated_at FROM system_prompts WHERE id = ?",
                    (prompt_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "id": row["id"],
                            "name": row["name"],
                            "content": row["content"],
                            "is_default": bool(row["is_default"]),
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"]
                        }
            else:
                # Get default prompt
                async with db.execute(
                    "SELECT id, name, content, is_default, created_at, updated_at FROM system_prompts WHERE is_default = 1 LIMIT 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "id": row["id"],
                            "name": row["name"],
                            "content": row["content"],
                            "is_default": bool(row["is_default"]),
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"]
                        }
        
        return None
    
    async def set_system_prompt(
        self,
        content: str,
        name: Optional[str] = None,
        prompt_id: Optional[str] = None,
        is_default: bool = False
    ) -> str:
        """Create or update a system prompt.
        
        Args:
            content: Prompt content
            name: Optional prompt name
            prompt_id: Optional prompt ID (for updates)
            is_default: Whether this should be the default prompt
        
        Returns:
            Prompt ID
        """
        await self._initialize_db()
        
        import uuid
        from datetime import datetime
        
        if not prompt_id:
            prompt_id = str(uuid.uuid4())
        
        now = datetime.utcnow().isoformat()
        
        # If setting as default, unset other defaults
        if is_default:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute("UPDATE system_prompts SET is_default = 0")
                await db.commit()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("""
                INSERT OR REPLACE INTO system_prompts 
                (id, name, content, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, 
                    COALESCE((SELECT created_at FROM system_prompts WHERE id = ?), ?),
                    ?)
            """, (prompt_id, name, content, 1 if is_default else 0, prompt_id, now, now))
            await db.commit()
        
        return prompt_id
    
    async def list_system_prompts(self) -> List[Dict[str, Any]]:
        """List all system prompts.
        
        Returns:
            List of prompt dictionaries
        """
        await self._initialize_db()
        
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute(
                "SELECT id, name, content, is_default, created_at, updated_at FROM system_prompts ORDER BY is_default DESC, updated_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                
                return [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "content": row["content"],
                        "is_default": bool(row["is_default"]),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                    for row in rows
                ]
    
    async def delete_system_prompt(self, prompt_id: str) -> bool:
        """Delete a system prompt.
        
        Args:
            prompt_id: Prompt ID to delete
        
        Returns:
            True if successful, False otherwise
        """
        await self._initialize_db()
        
        try:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
                await db.commit()
                return True
        except Exception as e:
            print(f"Error deleting system prompt: {e}")
            return False

    async def reset_all_data(self, keep_models: bool = True) -> Dict[str, Any]:
        """Reset all app data (conversations, settings, vector store).
        
        Args:
            keep_models: If True, keeps downloaded models (not used here, but for API compatibility)
        
        Returns:
            Dictionary with counts of deleted items
        """
        import logging
        logger = logging.getLogger(__name__)
        results = {
            "conversations_deleted": 0,
            "settings_cleared": False,
            "vector_store_cleared": False
        }
        
        try:
            await self._initialize_db()
            
            async with aiosqlite.connect(str(self.db_path)) as db:
                # Delete all conversations and messages
                async with db.execute("SELECT COUNT(*) FROM conversations") as cursor:
                    row = await cursor.fetchone()
                    results["conversations_deleted"] = row[0] if row else 0
                
                await db.execute("DELETE FROM messages")
                await db.execute("DELETE FROM conversations")
                
                # Clear all settings
                await db.execute("DELETE FROM app_settings")
                
                await db.commit()
                results["settings_cleared"] = True
            
            # Clear vector store
            if self.vector_store.collection and self.vector_store.store_type == "chromadb":
                try:
                    all_results = self.vector_store.collection.get()
                    if all_results and "ids" in all_results and all_results["ids"]:
                        self.vector_store.collection.delete(ids=all_results["ids"])
                        logger.info(f"Deleted {len(all_results['ids'])} entries from vector store")
                    results["vector_store_cleared"] = True
                except Exception as e:
                    logger.error(f"Error clearing vector store: {e}")
                    results["vector_store_cleared"] = False
            else:
                results["vector_store_cleared"] = True
            
            logger.info(f"Reset all app data: {results}")
            return results
        except Exception as e:
            logger.error(f"Error resetting app data: {e}", exc_info=True)
            raise

