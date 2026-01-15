"""Streaming response handling for proxy."""
import json
import logging
from typing import List, Dict, Any
from fastapi.responses import StreamingResponse
import httpx

from ....services.service_manager import service_manager

logger = logging.getLogger(__name__)


async def save_messages_to_vector_store(
    conversation_id: str,
    user_messages: List[Dict[str, Any]],
    assistant_content: str
):
    """Helper function to save messages to vector store."""
    if not service_manager.memory_store:
        return
    
    try:
        from datetime import datetime
        user_content = ""
        for msg in user_messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break
        
        messages = []
        if user_content:
            messages.append({
                "role": "user",
                "content": user_content,
                "timestamp": datetime.utcnow().isoformat()
            })
        if assistant_content:
            messages.append({
                "role": "assistant",
                "content": assistant_content,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        if messages:
            await service_manager.memory_store.store_conversation(
                conversation_id=conversation_id,
                messages=messages
            )
    except Exception as e:
        logger.error(f"Error saving to vector store: {e}", exc_info=True)


async def create_streaming_response(
    response: httpx.Response,
    conversation_id: str,
    messages: List[Dict[str, Any]],
    background_tasks
) -> StreamingResponse:
    """Create a streaming response with vector store saving.
    
    Args:
        response: HTTPX streaming response
        conversation_id: Conversation ID for saving
        messages: Original messages
        background_tasks: FastAPI background tasks
        
    Returns:
        StreamingResponse with save functionality
    """
    accumulated_content = []
    
    async def stream_with_save():
        async for chunk in response.aiter_bytes():
            try:
                chunk_text = chunk.decode('utf-8')
                if 'data: ' in chunk_text:
                    for line in chunk_text.split('\n'):
                        if line.startswith('data: '):
                            data_str = line[6:].strip()
                            if data_str and data_str != '[DONE]':
                                try:
                                    data = json.loads(data_str)
                                    if 'choices' in data and len(data['choices']) > 0:
                                        delta = data['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            accumulated_content.append(delta['content'])
                                except (json.JSONDecodeError, KeyError):
                                    pass
            except (UnicodeDecodeError, Exception):
                pass
            yield chunk
        
        # Save to vector store after streaming completes
        if conversation_id and service_manager.memory_store:
            full_content = ''.join(accumulated_content)
            if full_content:
                background_tasks.add_task(
                    save_messages_to_vector_store,
                    conversation_id,
                    messages,
                    full_content
                )
    
    return StreamingResponse(
        stream_with_save(),
        media_type=response.headers.get("content-type", "text/event-stream"),
        status_code=response.status_code
    )


