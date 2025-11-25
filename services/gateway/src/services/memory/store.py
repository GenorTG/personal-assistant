"""Memory storage service."""
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiosqlite
from pathlib import Path
from .vector_store import VectorStore
from .retrieval import ContextRetriever
from ...config.settings import settings


class MemoryStore:
    """Persistent memory storage with vector search and SQLite metadata."""
    
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.info("      Creating VectorStore (embedding model loads on first use)...")
        self.vector_store = VectorStore()
        logger.info("      VectorStore created")
        logger.info("      Creating ContextRetriever...")
        self.retriever = ContextRetriever(self.vector_store)
        logger.info("      ContextRetriever created")
        self.db_path = settings.memory_dir / "conversations.db"
        self._db_initialized = False
        logger.info(f"      Database path: {self.db_path}")
    
    async def initialize(self):
        """Initialize memory store resources."""
        await self._initialize_db()

    async def _initialize_db(self):
        """Initialize SQLite database for conversation metadata."""
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
            
            await db.commit()
        
        # Initialize encryption key
        self._init_encryption_key()
        
        self._db_initialized = True
    
    def _init_encryption_key(self):
        """Initialize encryption key for storing sensitive settings."""
        from cryptography.fernet import Fernet
        key_file = settings.memory_dir / ".encryption_key"
        
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
                
                await self.vector_store.add_message(
                    conversation_id=conversation_id,
                    message=message_content,
                    role=message.get("role", "user"),
                    timestamp=message_timestamp
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