"""Conversation management routes."""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request

from ..schemas import ConversationHistory
from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])


@router.post("/api/conversations/new")
async def create_conversation():
    """Create a new conversation."""
    logger.info("POST /api/conversations/new - Creating new conversation")
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        conversation_id = await service_manager.chat_manager.create_conversation()
        name = await service_manager.chat_manager.get_conversation_name(conversation_id)
        logger.info(f"Created conversation: {conversation_id} ({name})")
        return {
            "conversation_id": conversation_id,
            "name": name,
            "status": "created"
        }
    except Exception as e:
        logger.error(f"Error creating conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}") from e


@router.get("/api/conversations", response_model=List[ConversationHistory])
async def list_conversations(limit: Optional[int] = None, offset: int = 0, include_names: bool = True):
    """List all conversations with optional pagination."""
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        stored_conversations = await service_manager.memory_store.list_conversations(limit=limit, offset=offset)
        
        logger.debug(f"Found {len(stored_conversations)} conversations in database")
        
        conversations = []
        
        for conv_data in stored_conversations:
            conv_id = conv_data["conversation_id"]
            try:
                name = conv_data.get("name")
                
                if not name and include_names and service_manager.chat_manager:
                    name = await service_manager.chat_manager.get_conversation_name(conv_id)
                
                conversations.append(ConversationHistory(
                    conversation_id=conv_id,
                    messages=[],
                    name=name,
                    created_at=conv_data.get("created_at"),
                    updated_at=conv_data.get("updated_at"),
                    total_messages=conv_data.get("message_count", 0),
                    pinned=conv_data.get("pinned", False)
                ))
            except Exception as e:
                logger.error(f"Error processing conversation {conv_id}: {e}", exc_info=True)
                continue
        
        # Sort by pinned first, then by updated_at descending
        conversations.sort(
            key=lambda x: (
                not x.pinned,
                -(x.updated_at.timestamp() if x.updated_at else 0)
            ),
            reverse=False
        )
        logger.info(f"Returning {len(conversations)} conversations")
        return conversations
    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list conversations: {str(e)}"
        ) from e


@router.get("/api/conversations/{conversation_id}", response_model=ConversationHistory)
async def get_conversation(conversation_id: str):
    """Get conversation by ID."""
    if not service_manager.memory_store:
        logger.error("Memory store not initialized")
        raise HTTPException(
            status_code=503,
            detail="Memory store not initialized"
        )
    
    try:
        messages = await service_manager.memory_store.get_conversation(conversation_id)
        if messages is None:
            logger.warning(f"Conversation {conversation_id} not found")
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found"
            )
        
        stored_conversations = await service_manager.memory_store.list_conversations()
        conv_metadata = next((c for c in stored_conversations if c["conversation_id"] == conversation_id), None)
        
        chat_messages = [
            {
                "role": msg.get("role", "unknown"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp")
            }
            for msg in messages
        ]
        
        name = conv_metadata.get("name") if conv_metadata else None
        if not name and service_manager.chat_manager:
            name = await service_manager.chat_manager.get_conversation_name(conversation_id)
        
        pinned = conv_metadata.get("pinned", False) if conv_metadata else False
        
        return ConversationHistory(
            conversation_id=conversation_id,
            messages=chat_messages,
            name=name,
            created_at=conv_metadata.get("created_at") if conv_metadata else (messages[0].get("timestamp") if messages else None),
            updated_at=conv_metadata.get("updated_at") if conv_metadata else (messages[-1].get("timestamp") if messages else None),
            pinned=pinned
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation: {str(e)}"
        ) from e


@router.put("/api/conversations/{conversation_id}/messages/{message_index}")
async def update_message(
    conversation_id: str,
    message_index: int,
    request: Request
):
    """Update a message in a conversation."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    body = await request.json()
    new_content = body.get("content")
    role = body.get("role")
    
    if not new_content:
        raise HTTPException(status_code=400, detail="content is required")
    
    try:
        success = await service_manager.memory_store.update_message(
            conversation_id=conversation_id,
            message_index=message_index,
            new_content=new_content,
            role=role
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update message: {str(e)}") from e


@router.put("/api/conversations/{conversation_id}/rename")
async def rename_conversation(conversation_id: str, request: Request):
    """Rename a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    
    try:
        body = await request.json()
        new_name = body.get("name")
        
        if not new_name:
            raise HTTPException(status_code=400, detail="Name is required in request body")
        
        success = await service_manager.chat_manager.set_conversation_name(
            conversation_id,
            new_name
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
        
        return {
            "status": "success",
            "conversation_id": conversation_id,
            "new_name": new_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename conversation: {str(e)}")


@router.put("/api/conversations/{conversation_id}/pin")
async def pin_conversation(conversation_id: str, request: Request):
    """Pin or unpin a conversation."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not initialized"
        )
    
    try:
        body = await request.json()
        pinned = body.get("pinned", True)
        
        success = await service_manager.memory_store.set_conversation_pinned(
            conversation_id,
            pinned
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found"
            )
        
        action = "pinned" if pinned else "unpinned"
        return {
            "status": "success",
            "message": f"Conversation {conversation_id} {action}",
            "conversation_id": conversation_id,
            "pinned": pinned
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pinning conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pin conversation: {str(e)}"
        ) from e


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    deleted = await service_manager.chat_manager.delete_conversation(conversation_id)
    
    if deleted:
        return {
            "status": "success",
            "message": f"Conversation {conversation_id} deleted"
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )


@router.delete("/api/conversations/all")
async def delete_all_conversations():
    """Delete all conversations (excluding pinned ones)."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not initialized"
        )
    
    try:
        stored_conversations = await service_manager.memory_store.list_conversations()
        logger.info(f"Found {len(stored_conversations)} total conversations")
        
        conversation_ids = [
            conv["conversation_id"] 
            for conv in stored_conversations 
            if not conv.get("pinned", False)
        ]
        
        logger.info(f"Will delete {len(conversation_ids)} unpinned conversations")
        
        if not conversation_ids:
            logger.info("No unpinned conversations to delete")
            return {
                "status": "success",
                "message": "No unpinned conversations to delete",
                "deleted_count": 0,
                "total_count": 0,
                "pinned_preserved": len(stored_conversations)
            }
        
        deleted_count = 0
        file_store = service_manager.memory_store.file_store
        
        if not file_store:
            raise RuntimeError("File store not available in memory store")
        
        logger.info(f"Starting deletion of {len(conversation_ids)} conversations...")
        
        for conv_id in conversation_ids:
            try:
                logger.debug(f"Deleting conversation {conv_id}...")
                
                success = await file_store.delete_conversation(conv_id)
                if success:
                    deleted_count += 1
                    
                    try:
                        await service_manager.memory_store.vector_store.delete_conversation(conv_id)
                        logger.debug(f"Successfully deleted conversation {conv_id} from vector store")
                    except Exception as e:
                        logger.warning(f"Error deleting conversation {conv_id} from vector store: {e}")
                    
                    if service_manager.chat_manager:
                        if conv_id in service_manager.chat_manager.conversations:
                            del service_manager.chat_manager.conversations[conv_id]
                        if conv_id in service_manager.chat_manager._conversation_names:
                            del service_manager.chat_manager._conversation_names[conv_id]
                else:
                    logger.warning(f"Failed to delete conversation {conv_id}")
            except Exception as e:
                logger.error(f"Error deleting conversation {conv_id}: {e}", exc_info=True)
        
        pinned_count = len(stored_conversations) - len(conversation_ids)
        logger.info(f"Deleted {deleted_count} out of {len(conversation_ids)} conversations")
        
        remaining_conversations = await service_manager.memory_store.list_conversations()
        remaining_unpinned = [c for c in remaining_conversations if not c.get("pinned", False)]
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} conversations",
            "deleted_count": deleted_count,
            "total_count": len(conversation_ids),
            "pinned_preserved": pinned_count,
            "remaining_unpinned": len(remaining_unpinned)
        }
    except Exception as e:
        logger.error(f"Error deleting all conversations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete all conversations: {str(e)}"
        ) from e


@router.post("/api/conversations/cleanup")
async def cleanup_conversations():
    """Clean up stale conversation entries."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not initialized"
        )
    
    try:
        conversations = await service_manager.memory_store.list_conversations()
        
        return {
            "status": "success",
            "message": "Conversations cleaned up",
            "valid_conversations": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error cleaning up conversations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup conversations: {str(e)}"
        ) from e
