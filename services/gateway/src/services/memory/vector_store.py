"""Vector store for semantic search."""
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import logging
from collections import defaultdict

# Disable ChromaDB telemetry before importing
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Suppress ChromaDB telemetry errors in logging
chromadb_logger = logging.getLogger("chromadb.telemetry.product.posthog")
chromadb_logger.setLevel(logging.CRITICAL)
chromadb_logger.disabled = True

import chromadb
from chromadb.config import Settings as ChromaSettings
from .embeddings import EmbeddingModel
from ...config.settings import settings


class VectorStore:
    """Vector store using ChromaDB.
    
    Supports user-specific collections: each user profile has its own collection
    to keep vector memory separate between users.
    """
    
    def __init__(self, user_profile_id: Optional[str] = None):
        logger = logging.getLogger(__name__)
        logger.info("      Initializing vector store (type: %s, user: %s)...", 
                   settings.vector_store_type, user_profile_id or "default")
        self.store_type = settings.vector_store_type
        self.user_profile_id = user_profile_id or "default"
        # Lazy initialization - don't load embedding model until needed
        # This prevents blocking during startup
        self.embedder: Optional[EmbeddingModel] = None
        self.collection: Optional[Any] = None
        self.client: Optional[Any] = None
        self._collections_cache: Dict[str, Any] = {}  # Cache collections per user
        logger.info("      Calling _initialize_store()...")
        self._initialize_store()
        logger.info("      Initialization complete (embedding model will load on first use)")
    
    def _get_collection_name(self, user_profile_id: Optional[str] = None) -> str:
        """Get collection name for a user profile.
        
        Args:
            user_profile_id: User profile ID, or None to use current user
        
        Returns:
            Collection name
        """
        profile_id = user_profile_id or self.user_profile_id
        return f"conversations_user_{profile_id}"
    
    def _initialize_store(self):
        """Initialize vector store (ChromaDB)."""
        logger = logging.getLogger(__name__)
        if self.store_type == "chromadb":
            try:
                logger.info("      Initializing ChromaDB at: %s", settings.vector_store_dir)
                # Initialize ChromaDB with persistent storage
                self.client = chromadb.PersistentClient(
                    path=str(settings.vector_store_dir),
                    settings=ChromaSettings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                logger.info("      ChromaDB client created, getting/creating collection...")
                # Get or create collection for current user
                collection_name = self._get_collection_name()
                self.collection = self.client.get_or_create_collection(
                    name=collection_name,
                    metadata={"description": f"Conversation messages and context for user {self.user_profile_id}"}
                )
                self._collections_cache[self.user_profile_id] = self.collection
                logger.info("      ChromaDB collection ready for user: %s", self.user_profile_id)
            except Exception as e:
                logger.error("      Error initializing ChromaDB: %s", e, exc_info=True)
                self.collection = None
                self.client = None
        elif self.store_type == "faiss":
            # FAISS support not implemented - using ChromaDB only
            logger.warning("FAISS store type requested but not implemented, using ChromaDB")
            self.store_type = "chromadb"
            # Re-initialize with ChromaDB
            self._initialize_chromadb()
    
    def _get_collection(self, user_profile_id: Optional[str] = None) -> Optional[Any]:
        """Get collection for a specific user profile.
        
        Args:
            user_profile_id: User profile ID, or None to use current user
        
        Returns:
            ChromaDB collection or None
        """
        if not self.client:
            return None
        
        profile_id = user_profile_id or self.user_profile_id
        
        # Check cache first
        if profile_id in self._collections_cache:
            return self._collections_cache[profile_id]
        
        # Get or create collection for this user
        try:
            collection_name = self._get_collection_name(profile_id)
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"description": f"Conversation messages and context for user {profile_id}"}
            )
            self._collections_cache[profile_id] = collection
            return collection
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting collection for user {profile_id}: {e}", exc_info=True)
            return None
    
    async def add_message(
        self,
        conversation_id: str,
        message: str,
        role: str,
        timestamp: datetime,
        user_profile_id: Optional[str] = None
    ):
        """Add a message to the vector store.
        
        Args:
            conversation_id: Unique conversation identifier
            message: Message text content
            role: Message role (user/assistant/system)
            timestamp: Message timestamp
            user_profile_id: User profile ID (uses current user if None)
        """
        if not message or not message.strip():
            return  # Skip empty messages
        
        # Lazy initialize embedder if needed
        if self.embedder is None:
            logger = logging.getLogger(__name__)
            logger.info("Lazy loading embedding model...")
            self.embedder = EmbeddingModel()
        
        # Generate embedding
        embedding = await self.embedder.encode(message)
        
        # Get user-specific collection
        collection = self._get_collection(user_profile_id)
        
        # Store in vector database
        if self.store_type == "chromadb" and collection:
            try:
                # Create unique ID for this message
                message_id = f"{conversation_id}_{timestamp.isoformat()}_{hash(message) % 1000000}"
                
                # Add to ChromaDB
                collection.add(
                    embeddings=[embedding.tolist()],
                    documents=[message],
                    ids=[message_id],
                    metadatas=[{
                        "conversation_id": conversation_id,
                        "role": role,
                        "timestamp": timestamp.isoformat()
                    }]
                )
            except Exception as e:
                print(f"Error adding message to vector store: {e}")
        elif self.store_type == "faiss":
            # FAISS not implemented - should not reach here
            raise NotImplementedError("FAISS store type is not implemented")
            pass
    
    async def search(self, query: str, top_k: int = 5, user_profile_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for similar messages.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            user_profile_id: User profile ID (uses current user if None)
        
        Returns:
            List of dictionaries with text, score, and metadata
        """
        if not query or not query.strip():
            return []
        
        # Generate query embedding
        # Lazy initialize embedder if needed
        if self.embedder is None:
            logger = logging.getLogger(__name__)
            logger.info("Lazy loading embedding model...")
            self.embedder = EmbeddingModel()
        
        query_embedding = await self.embedder.encode(query)
        
        # Get user-specific collection
        collection = self._get_collection(user_profile_id)
        
        # Search in vector database
        if self.store_type == "chromadb" and collection:
            try:
                results = collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"]
                )
                
                # Format results
                formatted_results = []
                if results["documents"] and len(results["documents"]) > 0:
                    documents = results["documents"][0]
                    metadatas = results["metadatas"][0]
                    distances = results["distances"][0]
                    
                    for doc, meta, dist in zip(documents, metadatas, distances):
                        # Convert distance to similarity score (ChromaDB uses cosine distance)
                        # Cosine distance: 0 = identical, 2 = opposite
                        # Similarity: 1 - (distance / 2) gives range [0, 1]
                        similarity_score = max(0.0, 1.0 - (dist / 2.0))
                        
                        formatted_results.append({
                            "text": doc,
                            "score": similarity_score,
                            "metadata": meta
                        })
                
                return formatted_results
            except Exception as e:
                print(f"Error searching vector store: {e}")
                return []
        elif self.store_type == "faiss":
            # FAISS not implemented - should not reach here
            raise NotImplementedError("FAISS store type is not implemented")
            return []
        
        return []
    
    async def delete_conversation(self, conversation_id: str, user_profile_id: Optional[str] = None) -> bool:
        """Delete all messages for a conversation.
        
        Args:
            conversation_id: Conversation ID to delete
            user_profile_id: User profile ID (uses current user if None)
        
        Returns:
            True if deletion was successful, False otherwise
        """
        collection = self._get_collection(user_profile_id)
        if self.store_type == "chromadb" and collection:
            try:
                # Get all messages for this conversation
                results = collection.get(
                    where={"conversation_id": conversation_id}
                )
                
                if results["ids"]:
                    # Delete by IDs
                    collection.delete(ids=results["ids"])
                    logger = logging.getLogger(__name__)
                    logger.info(f"Deleted {len(results['ids'])} messages from vector store for conversation {conversation_id}")
                
                return True
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error deleting conversation from vector store: {e}", exc_info=True)
                return False
        
        return False
    
    async def delete_messages_after_index(
        self, 
        conversation_id: str, 
        message_index: int,
        user_profile_id: Optional[str] = None
    ) -> bool:
        """Delete messages from vector store that are after a certain index.
        
        Args:
            conversation_id: Conversation ID
            message_index: Index of the last message to keep (inclusive)
            user_profile_id: User profile ID (uses current user if None)
        
        Returns:
            True if deletion was successful, False otherwise
        """
        collection = self._get_collection(user_profile_id)
        if self.store_type == "chromadb" and collection:
            try:
                logger = logging.getLogger(__name__)
                # Get all messages for this conversation from vector store
                results = collection.get(
                    where={"conversation_id": conversation_id},
                    include=["metadatas"]
                )
                
                ids_to_delete = []
                if results["ids"] and results["metadatas"]:
                    # Sort messages by timestamp to ensure correct indexing
                    messages_with_index = []
                    for i, msg_id in enumerate(results["ids"]):
                        metadata = results["metadatas"][i]
                        try:
                            timestamp = datetime.fromisoformat(metadata["timestamp"].replace("Z", "+00:00"))
                            messages_with_index.append((timestamp, msg_id))
                        except (ValueError, KeyError):
                            # Fallback if timestamp is missing or invalid
                            messages_with_index.append((datetime.min, msg_id)) # Use min datetime to put at start
                    
                    messages_with_index.sort(key=lambda x: x[0])
                    
                    # Collect IDs to delete (messages after the specified index)
                    for i in range(message_index + 1, len(messages_with_index)):
                        ids_to_delete.append(messages_with_index[i][1])
                
                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
                    logger.info(f"Deleted {len(ids_to_delete)} messages from vector store after index {message_index} for conversation {conversation_id}")
                
                return True
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Error deleting messages from vector store: {e}", exc_info=True)
                return False
        
        return False
    
    def get_collection_count(self, user_profile_id: Optional[str] = None) -> int:
        """Get the number of items in the collection.
        
        Args:
            user_profile_id: User profile ID (uses current user if None)
        
        Returns:
            Number of items in collection, or 0 if unavailable
        """
        collection = self._get_collection(user_profile_id)
        if self.store_type == "chromadb" and collection:
            try:
                return collection.count()
            except Exception:
                return 0
        return 0
    
    def cleanup(self):
        """Cleanup resources and close connections."""
        if self.store_type == "chromadb" and self.client:
            try:
                # ChromaDB client cleanup - close any open connections
                # The client should handle cleanup, but we ensure it
                self.collection = None
                self.client = None
            except Exception:
                pass