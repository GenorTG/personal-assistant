"""Context retrieval and ranking system."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .vector_store import VectorStore
from ...config.settings import settings


class ContextRetriever:
    """Retrieves and ranks relevant context from memory."""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.similarity_threshold = settings.context_similarity_threshold
        self.default_top_k = settings.context_retrieval_top_k
    
    async def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        exclude_conversation_id: Optional[str] = None,
        recency_bias: bool = True,
        user_profile_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve relevant context for a query.
        
        Args:
            query: Search query (typically the current user message)
            top_k: Number of results to retrieve (default from settings)
            min_score: Minimum similarity score threshold (default from settings)
            exclude_conversation_id: Conversation ID to exclude from results
            recency_bias: Whether to apply recency bias to ranking
            user_profile_id: User profile ID (uses current user if None)
        
        Returns:
            Dictionary with retrieved messages, scores, and metadata
        """
        top_k = top_k or self.default_top_k
        min_score = min_score or self.similarity_threshold
        
        # Perform semantic search
        results = await self.vector_store.search(query=query, top_k=top_k * 2, user_profile_id=user_profile_id)  # Get more for filtering
        
        # Filter by similarity threshold and exclude conversation if needed
        filtered_results = []
        for result in results:
            score = result.get("score", 0.0)
            metadata = result.get("metadata", {})
            conversation_id = metadata.get("conversation_id")
            
            # Skip if below threshold
            if score < min_score:
                continue
            
            # Skip if excluded conversation
            if exclude_conversation_id and conversation_id == exclude_conversation_id:
                continue
            
            filtered_results.append(result)
        
        # Apply recency bias if enabled
        if recency_bias:
            filtered_results = self._apply_recency_bias(filtered_results)
        
        # Limit to top_k
        filtered_results = filtered_results[:top_k]
        
        # Format results
        retrieved_messages = [r["text"] for r in filtered_results]
        similarity_scores = [r["score"] for r in filtered_results]
        metadata_list = [r.get("metadata", {}) for r in filtered_results]
        
        return {
            "retrieved_messages": retrieved_messages,
            "similarity_scores": similarity_scores,
            "metadata": metadata_list,
            "count": len(retrieved_messages)
        }
    
    def _apply_recency_bias(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply recency bias to search results.
        
        Recent conversations are weighted higher than older ones.
        
        Args:
            results: List of search results with metadata
        
        Returns:
            Re-ranked results with recency bias applied
        """
        now = datetime.utcnow()
        
        # Calculate recency-adjusted scores
        for result in results:
            metadata = result.get("metadata", {})
            timestamp_str = metadata.get("timestamp")
            
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    # Calculate days since message
                    days_ago = (now - timestamp.replace(tzinfo=None)).days
                    
                    # Apply recency multiplier (decay over 30 days)
                    # Messages from today get 1.2x boost, messages from 30+ days ago get 0.8x
                    recency_multiplier = max(0.8, 1.2 - (days_ago / 30.0) * 0.4)
                    
                    # Adjust score
                    original_score = result.get("score", 0.0)
                    result["score"] = min(1.0, original_score * recency_multiplier)
                except (ValueError, TypeError):
                    # If timestamp parsing fails, keep original score
                    pass
        
        # Re-sort by adjusted score
        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        
        return results
    
    def format_context_for_prompt(
        self,
        context_data: Dict[str, Any],
        max_length: Optional[int] = None,
        format_style: str = "simple"
    ) -> str:
        """Format retrieved context for injection into LLM prompt.
        
        Args:
            context_data: Context data from retrieve_context()
            max_length: Maximum character length (None = no limit)
            format_style: Format style ("simple", "detailed", "compact")
        
        Returns:
            Formatted context string for prompt injection
        """
        retrieved_messages = context_data.get("retrieved_messages", [])
        similarity_scores = context_data.get("similarity_scores", [])
        metadata_list = context_data.get("metadata", [])
        
        if not retrieved_messages:
            return ""
        
        formatted_parts = []
        
        if format_style == "simple":
            # Simple format: just the messages
            for msg in retrieved_messages:
                # Truncate long messages
                if max_length and len(msg) > max_length:
                    msg = msg[:max_length] + "..."
                formatted_parts.append(f"- {msg}")
        
        elif format_style == "detailed":
            # Detailed format: messages with scores and metadata
            for msg, score, meta in zip(retrieved_messages, similarity_scores, metadata_list):
                role = meta.get("role", "unknown")
                timestamp = meta.get("timestamp", "")
                # Truncate long messages
                if max_length and len(msg) > max_length:
                    msg = msg[:max_length] + "..."
                formatted_parts.append(
                    f"- [{role}] (relevance: {score:.2f}) {msg}"
                )
        
        elif format_style == "compact":
            # Compact format: minimal formatting
            formatted_parts = [f"{msg}" for msg in retrieved_messages]
        
        formatted_text = "\n".join(formatted_parts)
        
        # Truncate overall context if needed
        if max_length and len(formatted_text) > max_length:
            formatted_text = formatted_text[:max_length] + "..."
        
        return formatted_text
    
    async def retrieve_conversation_context(
        self,
        conversation_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Retrieve all messages from a specific conversation.
        
        Args:
            conversation_id: Conversation ID to retrieve
            limit: Maximum number of messages to retrieve
        
        Returns:
            List of message dictionaries
        """
        # This would require querying by conversation_id
        # For now, we'll use a generic query and filter
        # In a production system, you might want to add a direct conversation lookup
        
        # Use a generic search and filter by conversation_id
        results = await self.vector_store.search(query="", top_k=1000)  # Get many results
        
        # Filter by conversation_id
        conversation_messages = [
            {
                "text": r["text"],
                "metadata": r.get("metadata", {}),
                "score": r.get("score", 1.0)
            }
            for r in results
            if r.get("metadata", {}).get("conversation_id") == conversation_id
        ]
        
        # Sort by timestamp if available
        try:
            conversation_messages.sort(
                key=lambda x: x.get("metadata", {}).get("timestamp", ""),
                reverse=False  # Oldest first
            )
        except (ValueError, TypeError):
            pass
        
        return conversation_messages[:limit]
