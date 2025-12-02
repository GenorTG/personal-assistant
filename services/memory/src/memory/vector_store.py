"""Vector store for semantic search."""
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import logging

# Disable ChromaDB telemetry before importing
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Suppress ChromaDB telemetry errors in logging
chromadb_logger = logging.getLogger("chromadb.telemetry.product.posthog")
chromadb_logger.setLevel(logging.CRITICAL)
chromadb_logger.disabled = True

import chromadb
from chromadb.config import Settings as ChromaSettings
from .embeddings import EmbeddingModel
from ..config.settings import settings


class VectorStore:
    """Vector store using ChromaDB or FAISS."""
    
    def __init__(self):
        logger = logging.getLogger(__name__)
        logger.info("      Initializing vector store (type: %s)...", settings.vector_store_type)
        self.store_type = settings.vector_store_type
        # Lazy initialization - don't load embedding model until needed
        # This prevents blocking during startup
        self.embedder: Optional[EmbeddingModel] = None
        self.collection: Optional[Any] = None
        self.client: Optional[Any] = None
        logger.info("      Calling _initialize_store()...")
        self._initialize_store()
        logger.info("      Initialization complete (embedding model will load on first use)")
    
    def _initialize_store(self):
        """Initialize vector store (ChromaDB or FAISS)."""
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
                # Get or create collection for conversations
                self.collection = self.client.get_or_create_collection(
                    name="conversations",
                    metadata={"description": "Conversation messages and context"}
                )
                logger.info("      ChromaDB collection ready")
            except Exception as e:
                logger.error("      Error initializing ChromaDB: %s", e, exc_info=True)
                self.collection = None
                self.client = None
        elif self.store_type == "faiss":
            # TODO: Initialize FAISS (fallback option)
            # FAISS requires manual persistence handling
            pass
    
    async def add_message(
        self,
        conversation_id: str,
        message: str,
        role: str,
        timestamp: datetime,
        db_message_id: Optional[str] = None
    ):
        """Add a message to the vector store.
        
        Args:
            conversation_id: Unique conversation identifier
            message: Message text content
            role: Message role (user/assistant/system)
            timestamp: Message timestamp
            db_message_id: Optional database message_id to store in metadata for easier deletion
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
        
        # Store in vector database
        if self.store_type == "chromadb" and self.collection:
            try:
                # Create unique ID for this message
                # Use db_message_id if provided, otherwise generate one
                if db_message_id:
                    message_id = db_message_id
                else:
                    message_id = f"{conversation_id}_{timestamp.isoformat()}_{hash(message) % 1000000}"
                
                # Add to ChromaDB
                metadata = {
                    "conversation_id": conversation_id,
                    "role": role,
                    "timestamp": timestamp.isoformat()
                }
                if db_message_id:
                    metadata["db_message_id"] = db_message_id
                
                self.collection.add(
                    embeddings=[embedding.tolist()],
                    documents=[message],
                    ids=[message_id],
                    metadatas=[metadata]
                )
            except Exception as e:
                print(f"Error adding message to vector store: {e}")
        elif self.store_type == "faiss":
            # TODO: Add to FAISS
            pass
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar messages.
        
        Args:
            query: Search query text
            top_k: Number of results to return
        
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
        
        # Search in vector database
        if self.store_type == "chromadb" and self.collection:
            try:
                results = self.collection.query(
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
            # TODO: Search FAISS
            return []
        
        return []
    
    async def delete_message(self, message_id: str) -> bool:
        """Delete a specific message by ID.
        
        Args:
            message_id: Message ID to delete
        
        Returns:
            True if deletion was successful, False otherwise
        """
        if self.store_type == "chromadb" and self.collection:
            try:
                self.collection.delete(ids=[message_id])
                return True
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Error deleting message from vector store: {e}")
                return False
        
        return False
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete all messages for a conversation.
        
        Args:
            conversation_id: Conversation ID to delete
        
        Returns:
            True if deletion was successful, False otherwise
        """
        if self.store_type == "chromadb" and self.collection:
            try:
                # Get all messages for this conversation
                results = self.collection.get(
                    where={"conversation_id": conversation_id}
                )
                
                if results["ids"]:
                    # Delete by IDs
                    self.collection.delete(ids=results["ids"])
                
                return True
            except Exception as e:
                print(f"Error deleting conversation from vector store: {e}")
                return False
        
        return False
    
    def get_collection_count(self) -> int:
        """Get the number of items in the collection.
        
        Returns:
            Number of items in collection, or 0 if unavailable
        """
        if self.store_type == "chromadb" and self.collection:
            try:
                return self.collection.count()
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

