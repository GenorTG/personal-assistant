"""API routes for Memory service."""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


# Request/Response models
class RetrieveContextRequest(BaseModel):
    query: str
    top_k: Optional[int] = None
    min_score: Optional[float] = None
    exclude_conversation_id: Optional[str] = None


class SaveMessageRequest(BaseModel):
    conversation_id: str
    messages: List[Dict[str, Any]]
    name: Optional[str] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    name: Optional[str]
    created_at: str
    updated_at: str
    message_count: int


class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: str


class SystemPromptRequest(BaseModel):
    content: str
    name: Optional[str] = None
    is_default: bool = False


class SystemPromptResponse(BaseModel):
    id: str
    name: Optional[str]
    content: str
    is_default: bool
    created_at: str
    updated_at: str


# Memory/Context endpoints
@router.post("/memory/retrieve-context")
async def retrieve_context(request: Request, body: RetrieveContextRequest):
    """Retrieve relevant context for a query."""
    memory_store = request.app.state.memory_store
    
    try:
        context = await memory_store.retrieve_context(
            query=body.query,
            top_k=body.top_k,
            exclude_conversation_id=body.exclude_conversation_id
        )
        return context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/save-message")
async def save_message(request: Request, body: SaveMessageRequest):
    """Save messages to memory."""
    memory_store = request.app.state.memory_store
    
    try:
        await memory_store.store_conversation(
            conversation_id=body.conversation_id,
            messages=body.messages,
            name=body.name
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Conversation endpoints
@router.get("/conversations")
async def list_conversations(request: Request, limit: Optional[int] = None, offset: int = 0):
    """List all conversations."""
    memory_store = request.app.state.memory_store
    
    try:
        conversations = await memory_store.list_conversations(limit=limit, offset=offset)
        return conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str, limit: Optional[int] = None):
    """Get a specific conversation."""
    memory_store = request.app.state.memory_store
    
    try:
        messages = await memory_store.get_conversation(conversation_id, limit=limit)
        if messages is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return messages
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(request: Request, conversation_id: str):
    """Delete a conversation."""
    memory_store = request.app.state.memory_store
    
    try:
        success = await memory_store.delete_conversation(conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConversationNameRequest(BaseModel):
    name: str


@router.put("/conversations/{conversation_id}/name")
async def set_conversation_name(request: Request, conversation_id: str, body: ConversationNameRequest):
    """Set the name of a conversation."""
    memory_store = request.app.state.memory_store
    
    try:
        success = await memory_store.set_conversation_name(conversation_id, body.name)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateMessageRequest(BaseModel):
    content: str
    role: Optional[str] = None


@router.put("/conversations/{conversation_id}/messages/{message_index}")
async def update_message(
    request: Request,
    conversation_id: str,
    message_index: int,
    body: UpdateMessageRequest
):
    """Update a message in a conversation by index."""
    memory_store = request.app.state.memory_store
    
    try:
        success = await memory_store.update_message(
            conversation_id=conversation_id,
            message_index=message_index,
            new_content=body.content,
            role=body.role
        )
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{conversation_id}/messages/last")
async def delete_last_message(request: Request, conversation_id: str):
    """Delete the last message from a conversation."""
    memory_store = request.app.state.memory_store
    
    try:
        success = await memory_store.delete_last_message(conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found or empty")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{conversation_id}/truncate")
async def truncate_conversation(request: Request, conversation_id: str, body: Dict[str, int]):
    """Truncate conversation at a specific message index."""
    memory_store = request.app.state.memory_store
    
    try:
        message_index = body.get("message_index", -1)
        if message_index < 0:
            raise HTTPException(status_code=400, detail="message_index must be >= 0")
        
        success = await memory_store.truncate_conversation_at(conversation_id, message_index)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found or invalid index")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# System prompt endpoints
@router.get("/settings/system-prompt")
async def get_system_prompt(request: Request, prompt_id: Optional[str] = None):
    """Get system prompt (default if prompt_id not provided)."""
    memory_store = request.app.state.memory_store
    
    try:
        prompt = await memory_store.get_system_prompt(prompt_id=prompt_id)
        if prompt is None:
            raise HTTPException(status_code=404, detail="System prompt not found")
        return prompt
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/system-prompt")
async def set_system_prompt(request: Request, body: SystemPromptRequest):
    """Create or update system prompt."""
    memory_store = request.app.state.memory_store
    
    try:
        prompt_id = await memory_store.set_system_prompt(
            content=body.content,
            name=body.name,
            is_default=body.is_default
        )
        return {"id": prompt_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/system-prompt/{prompt_id}")
async def update_system_prompt(request: Request, prompt_id: str, body: SystemPromptRequest):
    """Update an existing system prompt."""
    memory_store = request.app.state.memory_store
    
    try:
        updated_id = await memory_store.set_system_prompt(
            content=body.content,
            name=body.name,
            prompt_id=prompt_id,
            is_default=body.is_default
        )
        return {"id": updated_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/system-prompts")
async def list_system_prompts(request: Request):
    """List all system prompts."""
    memory_store = request.app.state.memory_store
    
    try:
        prompts = await memory_store.list_system_prompts()
        return prompts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/system-prompt/{prompt_id}")
async def delete_system_prompt(request: Request, prompt_id: str):
    """Delete a system prompt."""
    memory_store = request.app.state.memory_store
    
    try:
        success = await memory_store.delete_system_prompt(prompt_id)
        if not success:
            raise HTTPException(status_code=404, detail="System prompt not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Profile endpoints (placeholder - to be implemented)
@router.get("/profiles/characters")
async def list_characters(request: Request):
    """List all character profiles."""
    # TODO: Implement character profile management
    return []


@router.post("/profiles/characters")
async def create_character(request: Request):
    """Create a character profile."""
    # TODO: Implement character profile creation
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/profiles/user")
async def get_user_profile(request: Request):
    """Get user profile."""
    # TODO: Implement user profile management
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/profiles/user")
async def set_user_profile(request: Request):
    """Set user profile."""
    # TODO: Implement user profile management
    raise HTTPException(status_code=501, detail="Not implemented yet")


# Reset endpoint
@router.post("/api/reset")
async def reset_app_state(request: Request, keep_models: bool = True):
    """Reset all app state (conversations, settings, vector store).
    
    This will delete:
    - All conversations
    - All settings
    - Vector store data
    
    But will keep:
    - Downloaded models (if keep_models=True)
    """
    memory_store = request.app.state.memory_store
    
    try:
        results = await memory_store.reset_all_data(keep_models=keep_models)
        return {
            "status": "success",
            "message": "App state reset successfully",
            **results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset app state: {str(e)}")

