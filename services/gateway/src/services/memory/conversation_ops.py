"""Conversation operations for gateway memory store."""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from .user_facts_extractor import UserFactsExtractor

logger = logging.getLogger(__name__)


async def store_conversation_with_vector(
    file_store,
    vector_store,
    conversation_id: str,
    messages: List[Dict[str, Any]],
    name: Optional[str] = None,
    should_save_vector_func=None,
    user_profile_id: Optional[str] = None
) -> None:
    """Store conversation messages in memory with optional vector storage.
    
    Args:
        file_store: File conversation store instance
        vector_store: Vector store instance
        conversation_id: Unique conversation identifier
        messages: List of message dictionaries
        name: Optional conversation name
        should_save_vector_func: Optional async function to check if vector saving is enabled
    """
    # Get existing metadata to preserve created_at and pinned status
    index = await file_store._load_index()
    existing_meta = index.get("conversations", {}).get(conversation_id, {})
    
    # Preserve name if not provided
    final_name = name if name else existing_meta.get("name")
    
    # Store in file store (primary storage - fast and simple)
    metadata = {
        "created_at": existing_meta.get("created_at") or datetime.utcnow().isoformat(),
        "pinned": existing_meta.get("pinned", False)
    }
    await file_store.save_conversation(
        conversation_id=conversation_id,
        messages=messages,
        name=final_name,
        metadata=metadata
    )
    
    # Check if vector memory saving is enabled for this conversation
    save_enabled = True
    if should_save_vector_func:
        save_enabled = await should_save_vector_func(conversation_id)
    
    # Store in vector store (for semantic search) only if enabled
    # IMPORTANT: Only save user facts/preferences, not random conversation
    if save_enabled:
        for message in messages:
            message_content = message.get("content", "")
            message_role = message.get("role", "user")
            
            # Only save messages that contain user facts/preferences
            if not UserFactsExtractor.should_save_message(message_content, message_role):
                continue
            
            if message_content and message_content.strip():
                message_timestamp = message.get("timestamp")
                if isinstance(message_timestamp, str):
                    try:
                        message_timestamp = datetime.fromisoformat(message_timestamp.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        message_timestamp = datetime.utcnow()
                elif not isinstance(message_timestamp, datetime):
                    message_timestamp = datetime.utcnow()
                
                logger.debug(f"Saving user fact to vector memory: {message_content[:100]}...")
                await vector_store.add_message(
                    conversation_id=conversation_id,
                    message=message_content,
                    role=message_role,
                    timestamp=message_timestamp,
                    user_profile_id=user_profile_id
                )

