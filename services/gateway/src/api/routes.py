"""API route handlers."""
from typing import List, Optional, Dict, Any
import logging
import httpx
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, BackgroundTasks, Request, Header
from fastapi.responses import Response, StreamingResponse

from ..api.schemas import (
    ChatRequest, ChatResponse, ConversationHistory,
    STTResponse, TTSRequest,
    AISettings, AISettingsResponse, ModelInfo, ModelLoadOptions, CharacterCard, UserProfile,
    ModelMetadata, MemoryEstimate, MessageMetadata, ConversationRenameRequest
)
from ..services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint - simple and fast, no blocking operations."""
    # Keep this endpoint simple and fast - don't check services that might block
    return {
        "status": "healthy",
        "service": "personal-assistant",
        "message": "Backend is running"
    }


@router.get("/api/services/status")
async def get_services_status():
    """Get real-time status for all services from cached polling data."""
    if not service_manager.status_manager:
        raise HTTPException(
            status_code=503,
            detail="Status manager not initialized"
        )
    
    all_statuses = service_manager.status_manager.get_all_statuses()
    
    # Organize by service type for frontend consumption
    return {
        "stt": all_statuses.get("stt", {"status": "offline"}),
        "tts": {
            "piper": all_statuses.get("tts_piper", {"status": "offline"}),
            "chatterbox": all_statuses.get("tts_chatterbox", {"status": "offline"}),
            "kokoro": all_statuses.get("tts_kokoro", {"status": "offline"}),
        },
        "llm": all_statuses.get("llm", {"status": "offline"}),
        "last_poll": max(
            (s.get("last_check") for s in all_statuses.values() if s.get("last_check")),
            default=None
        )
    }


@router.get("/api/system/info")
async def get_system_info():
    """Get system information including CPU count and GPU info."""
    import os
    import multiprocessing
    
    cpu_count = os.cpu_count() or multiprocessing.cpu_count()
    
    # Get GPU information if available
    gpu_info = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpus = []
            for i in range(gpu_count):
                props = torch.cuda.get_device_properties(i)
                gpus.append({
                    "id": i,
                    "name": props.name,
                    "total_memory_gb": props.total_memory / (1024**3),
                    "compute_capability": f"{props.major}.{props.minor}"
                })
            gpu_info = {
                "available": True,
                "count": gpu_count,
                "cuda_version": torch.version.cuda,
                "devices": gpus
            }
            
            # Note: llama-cpp-python CUDA support is checked by the LLM service, not the gateway
                
        else:
            gpu_info = {"available": False, "reason": "CUDA not available"}
    except ImportError:
        gpu_info = {"available": False, "reason": "PyTorch not installed"}
    except Exception as e:
        gpu_info = {"available": False, "reason": str(e)}
    
    return {
        "cpu_count": cpu_count,
        "cpu_threads_available": cpu_count,  # Logical cores = thread count
        "platform": os.name,
        "system": os.uname().system if hasattr(os, 'uname') else "unknown",
        "gpu": gpu_info
    }


@router.get("/api/system/status")
async def get_system_status():
    """Get real-time system status including per-service RAM/VRAM usage."""
    from ..services.system_monitor import system_monitor
    return system_monitor.get_status()
@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat request."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded. Please load a model first."
        )
    
    try:
        import time
        start_time = time.time()
        
        # Apply settings from request if provided
        if request.character_card:
            character_card_dict = {
                "name": request.character_card.name,
                "personality": request.character_card.personality,
                "background": request.character_card.background,
                "instructions": request.character_card.instructions
            }
            service_manager.llm_manager.update_character_card(character_card_dict)
        
        if request.user_profile:
            user_profile_dict = {
                "name": request.user_profile.name,
                "about": request.user_profile.about,
                "preferences": request.user_profile.preferences
            }
            service_manager.llm_manager.update_user_profile(user_profile_dict)
        
        # Collect sampler settings from request (use saved settings as defaults)
        saved_settings = service_manager.llm_manager.get_settings()
        
        # Build sampler parameters for this request
        sampler_params = {
            "temperature": request.temperature if request.temperature is not None else saved_settings.get("temperature", 0.7),
            "top_p": request.top_p if request.top_p is not None else saved_settings.get("top_p", 0.9),
            "top_k": request.top_k if request.top_k is not None else saved_settings.get("top_k", 40),
            "max_tokens": request.max_tokens if request.max_tokens is not None else saved_settings.get("max_tokens", 512),
        }
        
        # Add optional parameters if provided in request
        if request.min_p is not None:
            sampler_params["min_p"] = request.min_p
        if request.repeat_penalty is not None:
            sampler_params["repeat_penalty"] = request.repeat_penalty
        if request.presence_penalty is not None:
            sampler_params["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            sampler_params["frequency_penalty"] = request.frequency_penalty
        if request.typical_p is not None:
            sampler_params["typical_p"] = request.typical_p
        if request.tfs_z is not None:
            sampler_params["tfs_z"] = request.tfs_z
        if request.mirostat_mode is not None:
            sampler_params["mirostat_mode"] = request.mirostat_mode
            if request.mirostat_tau is not None:
                sampler_params["mirostat_tau"] = request.mirostat_tau
            if request.mirostat_eta is not None:
                sampler_params["mirostat_eta"] = request.mirostat_eta
        if request.stop is not None:
            sampler_params["stop"] = request.stop
        if request.seed is not None:
            sampler_params["seed"] = request.seed
        if request.grammar is not None:
            sampler_params["grammar"] = request.grammar
        if request.logit_bias is not None:
            sampler_params["logit_bias"] = request.logit_bias
        if request.penalty_range is not None:
            sampler_params["penalty_range"] = request.penalty_range
        if request.penalty_alpha is not None:
            sampler_params["penalty_alpha"] = request.penalty_alpha
        if request.n_probs is not None:
            sampler_params["n_probs"] = request.n_probs
        
        # DRY (Dynamic Repetition Penalty) - sequence-based repetition control
        if request.dry_multiplier is not None:
            sampler_params["dry_multiplier"] = request.dry_multiplier
        if request.dry_base is not None:
            sampler_params["dry_base"] = request.dry_base
        if request.dry_allowed_length is not None:
            sampler_params["dry_allowed_length"] = request.dry_allowed_length
        
        # Update LLM manager settings for metadata (but actual request uses sampler_params)
        service_manager.llm_manager.update_settings({
            "temperature": sampler_params["temperature"],
            "top_p": sampler_params["top_p"],
            "top_k": sampler_params["top_k"],
            "max_tokens": sampler_params["max_tokens"],
        })
        
        # Get current settings for metadata
        current_settings = service_manager.llm_manager.get_settings()
        
        # Send message with sampler parameters
        result = await service_manager.chat_manager.send_message(
            message=request.message,
            conversation_id=request.conversation_id,
            sampler_params=sampler_params
        )
        
        # Calculate generation time
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Create metadata
        metadata = MessageMetadata(
            model_name=service_manager.llm_manager.current_model_name,
            generation_time_ms=round(generation_time_ms, 2),
            context_length=service_manager.llm_manager.loader._n_ctx if hasattr(service_manager.llm_manager.loader, '_n_ctx') else None,
            temperature=sampler_params.get("temperature"),
            top_p=sampler_params.get("top_p"),
            top_k=sampler_params.get("top_k"),
            repeat_penalty=sampler_params.get("repeat_penalty"),
            retrieved_context=result.get("context_used", [])
        )
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            context_used=result.get("context_used", []),
            tool_calls=result.get("tool_calls"),
            metadata=metadata
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


@router.post("/api/chat/regenerate")
async def regenerate_last_response(request: Request):
    """Regenerate the last assistant response in a conversation.
    
    This deletes the last assistant message and regenerates from that point.
    """
    from ..services.service_manager import service_manager
    
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded. Please load a model first."
        )
    
    body = await request.json()
    conversation_id = body.get("conversation_id")
    
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    
    try:
        # Get conversation to find the last user message
        conversation = await service_manager.memory_store.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Find the last user message (before the assistant response we want to regenerate)
        last_user_index = -1
        for i in range(len(conversation) - 1, -1, -1):
            if conversation[i].get("role") == "user":
                last_user_index = i
                break
        
        if last_user_index == -1:
            raise HTTPException(status_code=400, detail="No user message found to regenerate from")
        
        # Delete the last assistant message(s) - there might be multiple if tool calls happened
        # Delete all messages after the last user message
        success = await service_manager.memory_store.truncate_conversation_at(
            conversation_id, last_user_index
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to truncate conversation")
        
        # Get the user message to regenerate from
        user_message = conversation[last_user_index].get("content", "")
        
        # Get sampler settings from request or use saved
        saved_settings = service_manager.llm_manager.get_settings()
        sampler_params = body.get("sampler_params", {})
        if not sampler_params:
            sampler_params = {
                "temperature": saved_settings.get("temperature", 0.7),
                "top_p": saved_settings.get("top_p", 0.9),
                "top_k": saved_settings.get("top_k", 40),
                "max_tokens": saved_settings.get("max_tokens", 512),
            }
        
        # Regenerate response
        import time
        start_time = time.time()
        
        result = await service_manager.chat_manager.send_message(
            message=user_message,
            conversation_id=conversation_id,
            sampler_params=sampler_params
        )
        
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Create metadata
        metadata = MessageMetadata(
            model_name=service_manager.llm_manager.current_model_name,
            generation_time_ms=round(generation_time_ms, 2),
            context_length=service_manager.llm_manager.loader._n_ctx if hasattr(service_manager.llm_manager.loader, '_n_ctx') else None,
            temperature=sampler_params.get("temperature"),
            top_p=sampler_params.get("top_p"),
            top_k=sampler_params.get("top_k"),
            repeat_penalty=sampler_params.get("repeat_penalty"),
            retrieved_context=result.get("context_used", [])
        )
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            context_used=result.get("context_used", []),
            tool_calls=result.get("tool_calls"),
            metadata=metadata
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating response: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to regenerate: {str(e)}") from e


@router.put("/api/conversations/{conversation_id}/messages/{message_index}")
async def update_message(
    conversation_id: str,
    message_index: int,
    request: Request
):
    """Update a message in a conversation."""
    from ..services.service_manager import service_manager
    
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
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


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
async def list_conversations(limit: Optional[int] = None, offset: int = 0):
    """List all conversations with optional pagination.
    
    Args:
        limit: Maximum number of conversations to return (None = all)
        offset: Number of conversations to skip (for pagination)
    """
    if not service_manager.chat_manager:
        logger.error("Chat manager not initialized")
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        # OPTIMIZATION: Get only metadata from database - no message loading
        # This makes listing conversations extremely fast
        # Frontend will load messages when user selects a conversation
        stored_conversations = await service_manager.memory_store.list_conversations()
        
        # Apply pagination if requested
        if limit is not None:
            stored_conversations = stored_conversations[offset:offset + limit]
            logger.debug(f"Returning conversations {offset} to {offset + limit} of {len(stored_conversations)} total")
        else:
            logger.debug(f"Found {len(stored_conversations)} conversations in database")
        
        conversations = []
        
        for conv_data in stored_conversations:
            conv_id = conv_data["conversation_id"]
            try:
                # Get conversation name from metadata (no need to load messages)
                name = conv_data.get("name")
                if not name and service_manager.chat_manager:
                    # Only generate name if not set and chat manager is available
                    name = await service_manager.chat_manager.get_conversation_name(conv_id)
                
                # Return empty messages list - frontend will load when needed
                # This makes listing 10x faster
                conversations.append(ConversationHistory(
                    conversation_id=conv_id,
                    messages=[],  # Empty - frontend loads on selection
                    name=name,
                    created_at=conv_data.get("created_at"),
                    updated_at=conv_data.get("updated_at"),
                    total_messages=conv_data.get("message_count", 0),
                    pinned=conv_data.get("pinned", False)
                ))
            except Exception as e:
                logger.error(f"Error processing conversation {conv_id}: {e}", exc_info=True)
                # Skip conversations that fail to process
                continue
        
        # Sort by pinned first, then by updated_at descending (most recent first)
        # Use a key that inverts updated_at timestamp for descending sort while keeping pinned first
        conversations.sort(
            key=lambda x: (
                not x.pinned,  # False (pinned) sorts first when reverse=False
                -(x.updated_at.timestamp() if x.updated_at else 0)  # Negative timestamp for descending
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
        # Get messages directly from memory store (uses file store)
        messages = await service_manager.memory_store.get_conversation(conversation_id)
        if messages is None:  # None means conversation doesn't exist
            logger.warning(f"Conversation {conversation_id} not found")
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found"
            )
        
        # Get conversation metadata from index
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
        
        # Get conversation name from metadata or generate
        name = conv_metadata.get("name") if conv_metadata else None
        if not name and service_manager.chat_manager:
            name = await service_manager.chat_manager.get_conversation_name(conversation_id)
        
        # Get pinned status
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


@router.post("/api/voice/stt", response_model=STTResponse)
async def speech_to_text(
    audio: UploadFile = File(...),
    language: Optional[str] = None
):
    """Convert speech to text."""
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="STT service not initialized"
        )
    
    try:
        # Save uploaded file temporarily
        import tempfile
        import aiofiles
        from pathlib import Path
        
        # Get file extension
        file_ext = Path(audio.filename).suffix if audio.filename else ".wav"
        
        with tempfile.NamedTemporaryFile(
            suffix=file_ext,
            delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
        
        # Write uploaded file to temp file
        async with aiofiles.open(tmp_path, 'wb') as f:
            content = await audio.read()
            await f.write(content)
        
        try:
            # Transcribe audio
            text, detected_language = await service_manager.stt_service.transcribe(
                tmp_path,
                language=language
            )
            
            return STTResponse(
                text=text,
                language=detected_language
            )
        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()
    
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Audio file error: {str(e)}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"STT error: {str(e)}"
        ) from e


@router.post("/api/voice/tts")
async def text_to_speech(request: TTSRequest):
    """Convert text to speech."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty"
        )
    
    try:
        # Synthesize speech
        audio_data = await service_manager.tts_service.synthesize(
            text=request.text,
            voice=request.voice,
            output_format="wav"
        )
        
        # Return audio as streaming response
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"TTS error: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends")
async def get_tts_backends():
    """Get list of all available TTS backends with their status."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        backends = service_manager.tts_service.get_available_backends()
        return {"backends": backends}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backends: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}")
async def get_tts_backend_info(backend_name: str):
    """Get detailed information about a specific TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        info = await service_manager.tts_service.get_backend_info(backend_name)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backend info: {str(e)}"
        ) from e


@router.post("/api/voice/tts/backends/{backend_name}/switch")
async def switch_tts_backend(backend_name: str):
    """Switch to a different TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        success = await service_manager.tts_service.switch_backend(backend_name)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Save backend selection to settings
        await service_manager.memory_store.set_setting("tts_backend", backend_name)
        
        # Return updated backend info (even if initialization failed)
        info = await service_manager.tts_service.get_backend_info(backend_name)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Determine message based on backend status
        if info.get("status") == "ready":
            message = f"Switched to TTS backend: {backend_name}"
            status = "success"
        elif info.get("status") == "error":
            message = f"Switched to TTS backend: {backend_name} (initialization failed: {info.get('error_message', 'Unknown error')})"
            status = "warning"
        else:
            message = f"Switched to TTS backend: {backend_name}"
            status = "success"
        
        return {
            "status": status,
            "message": message,
            "backend_info": info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error switching TTS backend: {str(e)}"
        )

@router.post("/api/voice/tts/backends/{backend_name}/start")
async def start_tts_backend(backend_name: str):
    """Start a TTS backend service (if supported)."""
    backend = service_manager.tts_service.manager.get_backend(backend_name)
    if not backend:
        raise HTTPException(status_code=404, detail="Backend not found")
    
    if hasattr(backend, "start_service"):
        success = await backend.start_service()
        if success:
            # Re-initialize to update status
            await backend.initialize()
            return {"status": "success", "message": f"Started {backend_name} service"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to start {backend_name} service")
    
    return {"status": "ignored", "message": "Service control not supported for this backend"}





@router.get("/api/voice/tts/backends/{backend_name}/voices")
async def get_tts_voices(backend_name: str):
    """Get available voices for a TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        voices = await service_manager.tts_service.get_available_voices(backend_name)
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS voices: {str(e)}"
        ) from e


@router.put("/api/voice/tts/backends/{backend_name}/options")
async def set_tts_backend_options(backend_name: str, options: dict):
    """Set options for a TTS backend."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        success = service_manager.tts_service.set_backend_options(backend_name, options)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to set options for TTS backend '{backend_name}'"
            )
        
        # Return updated backend info
        info = service_manager.tts_service.get_backend_info(backend_name)
        return {
            "status": "success",
            "message": f"Options updated for TTS backend: {backend_name}",
            "backend": info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting TTS backend options: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}/models")
async def get_tts_backend_models(backend_name: str):
    """Get available models for a TTS backend (e.g., Coqui)."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        backend = service_manager.tts_service.manager.get_backend(backend_name)
        if not backend:
            raise HTTPException(
                status_code=404,
                detail=f"TTS backend '{backend_name}' not found"
            )
        
        # Check if backend has get_available_models method
        if hasattr(backend, 'get_available_models'):
            models = backend.get_available_models()
            return {"models": models}
        else:
            return {"models": []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS backend models: {str(e)}"
        ) from e


@router.get("/api/voice/tts/settings")
async def get_tts_settings():
    """Get all TTS settings including current backend, voices, and options."""
    if not service_manager.tts_service:
        raise HTTPException(
            status_code=503,
            detail="TTS service not initialized"
        )
    
    try:
        current_backend = service_manager.tts_service.get_current_backend_name()
        backends = service_manager.tts_service.get_available_backends()
        
        # Get detailed info for current backend
        current_info = None
        if service_manager.tts_service.manager.current_backend:
            current_info = await service_manager.tts_service.get_backend_info(current_backend)
        
        return {
            "current_backend": current_backend,
            "current_backend_info": current_info,
            "available_backends": backends
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting TTS settings: {str(e)}"
        ) from e


@router.get("/api/voice/tts/backends/{backend_name}/health")
async def check_tts_backend_health(backend_name: str):
    """Check if a TTS backend service is running and accessible."""
    # Map backend names to their service URLs
    service_urls = {
        "piper": "http://localhost:8004",
        "whisper": "http://localhost:8003",  # STT service for reference
        "chatterbox": "http://localhost:4123",
        "kokoro": "http://localhost:8880"
    }
    
    
    # Special handling for OpenAI backend - test actual API connectivity
    if backend_name == "openai":
        if service_manager.tts_service:
            backend = service_manager.tts_service.manager.backends.get("openai")
            if backend and hasattr(backend, 'api_url') and backend.api_url:
                # Test actual API connectivity with a minimal request
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        # Try to list models as a connectivity test
                        headers = {}
                        if hasattr(backend, 'api_key') and backend.api_key:
                            headers["Authorization"] = f"Bearer {backend.api_key}"
                        
                        test_url = f"{backend.api_url.rstrip('/')}/v1/models"
                        resp = await client.get(test_url, headers=headers)
                        
                        if resp.status_code == 200:
                            return {
                                "accessible": True,
                                "is_service": False,
                                "is_external": True,
                                "status": "API endpoint accessible",
                                "url": backend.api_url,
                                "authenticated": bool(backend.api_key)
                            }
                        elif resp.status_code == 401:
                            return {
                                "accessible": False,
                                "is_service": False,
                                "is_external": True,
                                "error": "Authentication failed - invalid API key",
                                "url": backend.api_url,
                                "status_code": 401
                            }
                        else:
                            return {
                                "accessible": False,
                                "is_service": False,
                                "is_external": True,
                                "error": f"API returned status {resp.status_code}",
                                "url": backend.api_url,
                                "status_code": resp.status_code
                            }
                except httpx.TimeoutException:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": "Connection timeout - API endpoint not responding",
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
                except httpx.ConnectError:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": "Connection failed - cannot reach API endpoint",
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
                except Exception as e:
                    return {
                        "accessible": False,
                        "is_service": False,
                        "is_external": True,
                        "error": str(e),
                        "url": backend.api_url if hasattr(backend, 'api_url') else None
                    }
            else:
                return {
                    "accessible": False,
                    "is_service": False,
                    "is_external": True,
                    "error": "OpenAI backend not configured - no API URL set",
                    "needs_configuration": True
                }
        return {
            "accessible": False,
            "is_service": False,
            "is_external": True,
            "reason": "TTS service not initialized"
        }
    
    # Other non-service backends (pyttsx3, etc.)
    if backend_name not in service_urls:
        # For pyttsx3, etc. - check if backend exists and is initialized
        if service_manager.tts_service:
            backend = service_manager.tts_service.manager.backends.get(backend_name)
            if backend:
                return {
                    "accessible": True,
                    "is_service": False,
                    "status": "Local backend - no service required"
                }
        return {
            "accessible": False,
            "is_service": False,
            "reason": "Backend not found"
        }

    
    # Check service-based backends
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{service_urls[backend_name]}/health")
            return {
                "accessible": resp.status_code == 200,
                "is_service": True,
                "status_code": resp.status_code,
                "url": service_urls[backend_name]
            }
    except httpx.TimeoutException:
        return {
            "accessible": False,
            "is_service": True,
            "error": "Connection timeout",
            "url": service_urls[backend_name]
        }
    except httpx.ConnectError:
        return {
            "accessible": False,
            "is_service": True,
            "error": "Service not running",
            "url": service_urls[backend_name]
        }
    except Exception as e:
        return {
            "accessible": False,
            "is_service": True,
            "error": str(e),
            "url": service_urls[backend_name]
        }


@router.get("/api/voice/tts/backends/chatterbox/service")
async def get_chatterbox_service_status():
    """Get Chatterbox TTS API service status."""
    try:
        from ..services.external.chatterbox_service import chatterbox_service
        return chatterbox_service.get_status()
    except Exception as e:
        logger.error(f"Error getting Chatterbox service status: {e}", exc_info=True)
        # Return a safe default status
        return {
            "status": "error",
            "is_running": False,
            "api_url": None,
            "frontend_url": None,
            "installed": False,
            "dependencies_installed": False,
            "device": "unknown",
            "cuda_available": False,
            "gpu_name": None,
            "pytorch_version": None,
            "error_message": str(e),
            "base_dir": None
        }


@router.post("/api/voice/tts/backends/chatterbox/service/install")
async def install_chatterbox_service(background_tasks: BackgroundTasks):
    """Install Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    
    # Check if already installing
    status = chatterbox_service.get_status()
    if status.get("is_installing"):
        return {"status": "started", "message": "Installation already in progress"}
    
    # Start installation in background
    background_tasks.add_task(chatterbox_service.install)
    
    return {"status": "started", "message": "Installation started in background"}


@router.post("/api/voice/tts/backends/chatterbox/service/start")
async def start_chatterbox_service():
    """Start Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.start()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/stop")
async def stop_chatterbox_service():
    """Stop Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.stop()
    return result


@router.post("/api/voice/tts/backends/chatterbox/service/restart")
async def restart_chatterbox_service():
    """Restart Chatterbox TTS API server."""
    from ..services.external.chatterbox_service import chatterbox_service
    result = await chatterbox_service.restart()
    return result


@router.get("/api/voice/tts/backends/chatterbox/service/logs")
async def get_chatterbox_service_logs():
    """Get Chatterbox TTS API service logs."""
    from ..services.external.chatterbox_service import chatterbox_service
    return {"logs": chatterbox_service.get_logs()}


@router.get("/api/voice/stt/settings")
async def get_stt_settings():
    """Get all STT settings from cached status."""
    try:
        # Ensure proxy exists (it should be always on now)
        if not service_manager.stt_service:
            service_manager.enable_stt()
        
        if not service_manager.status_manager:
            # Fallback if status manager not initialized
            return {
                "status": "offline",
                "provider": "Whisper",
                "model_size": True,
                "available_languages": ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "hi"],
                "default_language": "en",
                "model_initialized": False
            }
        
        stt_service = service_manager.stt_service
        
        # Get cached status instead of real-time check
        cached_status = service_manager.status_manager.get_service_status("stt") or {}
        is_healthy = cached_status.get("status") == "ready"
            
        # Return info with cached status
        return {
            "status": "ready" if is_healthy else "offline",
            "provider": stt_service.provider,
            "model_size": True,
            "available_languages": ["en", "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "hi"],
            "default_language": "en",
            "model_initialized": is_healthy,
            "last_check": cached_status.get("last_check"),
            "response_time_ms": cached_status.get("response_time_ms")
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting STT settings: {str(e)}"
        ) from e


@router.post("/api/voice/stt/initialize")
async def initialize_stt():
    """Initialize STT service (loads model on demand)."""
    # Enable STT service if not already enabled
    service_manager.enable_stt()
    
    # Persist setting so it auto-starts next time
    if service_manager.memory_store:
        await service_manager.memory_store.update_setting("stt_enabled", "true")
    
    if not service_manager.stt_service:
        raise HTTPException(
            status_code=503,
            detail="Failed to enable STT service"
        )
    
    try:
        stt_service = service_manager.stt_service
        # For remote service, we assume it's initialized if the object exists
        # The actual remote service (Whisper) should be running
        
        return {
            "status": "success",
            "message": "STT service initialized successfully",
            "initialized": True,
            "provider": stt_service.provider
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error initializing STT service: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error initializing STT service: {error_msg}"
        ) from e


@router.post("/api/voice/tts/backends/openai/config")
async def configure_openai_tts(config: Dict[str, str]):
    """Configure OpenAI TTS backend."""
    api_url = config.get("api_url")
    api_key = config.get("api_key")
    
    if not api_url or not api_key:
        raise HTTPException(status_code=400, detail="api_url and api_key are required")
    
    # Save to settings
    await service_manager.memory_store.set_setting("tts_openai_url", api_url)
    await service_manager.memory_store.set_setting("tts_openai_key", api_key, encrypted=True)
    
    # Configure the backend
    backend = service_manager.tts_service.manager.backends.get("openai")
    if backend:
        backend.configure(api_url, api_key)
        await backend.initialize()
    
    return {"status": "success", "message": "OpenAI TTS configured"}


@router.post("/api/voice/stt/config")
async def configure_stt(config: Dict[str, str]):
    """Configure STT service (Whisper or OpenAI)."""
    provider = config.get("provider", "whisper")
    enabled = config.get("enabled", "true")
    
    # Save settings
    await service_manager.memory_store.set_setting("stt_provider", provider)
    await service_manager.memory_store.set_setting("stt_enabled", enabled)
    
    if provider == "openai":
        api_url = config.get("api_url")
        api_key = config.get("api_key")
        
        if api_url and api_key:
            await service_manager.memory_store.set_setting("stt_openai_url", api_url)
            await service_manager.memory_store.set_setting("stt_openai_key", api_key, encrypted=True)
    
    return {"status": "success", "message": "STT configured", "provider": provider, "enabled": enabled}


@router.get("/api/voice/config")
async def get_voice_config():
    """Get current voice service configuration."""
    tts_backend = await service_manager.memory_store.get_setting("tts_backend", "pyttsx3")
    stt_enabled = await service_manager.memory_store.get_setting("stt_enabled", "false")
    stt_provider = await service_manager.memory_store.get_setting("stt_provider", "whisper")
    
    # Get OpenAI config (don't expose keys, just indicate if configured)
    tts_openai_url = await service_manager.memory_store.get_setting("tts_openai_url")
    stt_openai_url = await service_manager.memory_store.get_setting("stt_openai_url")
    
    return {
        "tts": {
            "backend": tts_backend,
            "openai_configured": bool(tts_openai_url)
        },
        "stt": {
            "enabled": stt_enabled == "true",
            "provider": stt_provider,
            "openai_configured": bool(stt_openai_url)
        }
    }



@router.get("/api/settings", response_model=AISettingsResponse)
async def get_settings():
    """Get current AI settings."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Load settings from file stores
    settings_dict = service_manager.llm_manager.get_settings()
    
    # Load system prompt from file store
    system_prompt_data = await service_manager.memory_store.get_system_prompt()
    system_prompt = system_prompt_data.get("content", "") if system_prompt_data else service_manager.llm_manager.get_system_prompt()
    
    # Load character card and user profile from file stores
    character_card = await service_manager.memory_store.get_character_card()
    user_profile = await service_manager.memory_store.get_user_profile()
    model_loaded = service_manager.llm_manager.is_model_loaded()  # Not async
    current_model = service_manager.llm_manager.get_current_model_path()
    
    default_load_options = service_manager.llm_manager.get_default_load_options()
    
    # Get tool calling support status
    supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
    
    return AISettingsResponse(
        settings=AISettings(
            temperature=settings_dict["temperature"],
            top_p=settings_dict["top_p"],
            top_k=settings_dict["top_k"],
            repeat_penalty=settings_dict["repeat_penalty"],
            system_prompt=system_prompt,
            character_card=CharacterCard(**character_card) if character_card else None,
            user_profile=UserProfile(**user_profile) if user_profile else None,
            default_load_options=ModelLoadOptions(**default_load_options) if default_load_options else None
        ),
        model_loaded=model_loaded,
        current_model=current_model,
        supports_tool_calling=supports_tool_calling
    )


@router.put("/api/settings", response_model=AISettingsResponse)
async def update_settings(settings_update: AISettings):
    """Update AI settings."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Update sampler settings
    settings_dict = {}
    if settings_update.temperature is not None:
        settings_dict["temperature"] = settings_update.temperature
    if settings_update.top_p is not None:
        settings_dict["top_p"] = settings_update.top_p
    if settings_update.top_k is not None:
        settings_dict["top_k"] = settings_update.top_k
    if settings_update.repeat_penalty is not None:
        settings_dict["repeat_penalty"] = settings_update.repeat_penalty
    
    if settings_dict:
        service_manager.llm_manager.update_settings(settings_dict)
    
    # Update system prompt if provided (save to file store)
    if settings_update.system_prompt is not None:
        # Update in-memory for LLM manager
        service_manager.llm_manager.update_system_prompt(settings_update.system_prompt)
        # Persist to file store
        await service_manager.memory_store.set_system_prompt(
            content=settings_update.system_prompt,
            is_default=True
        )
    
    # Update character card if provided (save to file store)
    if settings_update.character_card is not None:
        character_card_dict = {
            "name": settings_update.character_card.name,
            "personality": settings_update.character_card.personality,
            "background": settings_update.character_card.background,
            "instructions": settings_update.character_card.instructions
        }
        # Update in-memory for LLM manager
        service_manager.llm_manager.update_character_card(character_card_dict)
        # Persist to file store
        await service_manager.memory_store.set_character_card(character_card_dict)
    
    # Update user profile if provided (save to file store)
    if settings_update.user_profile is not None:
        user_profile_dict = {
            "name": settings_update.user_profile.name,
            "about": settings_update.user_profile.about,
            "preferences": settings_update.user_profile.preferences
        }
        # Update in-memory for LLM manager
        service_manager.llm_manager.update_user_profile(user_profile_dict)
        # Persist to file store
        await service_manager.memory_store.set_user_profile(user_profile_dict)
    
    # Update sampler settings if provided (save to file store)
    if settings_dict:
        await service_manager.memory_store.update_sampler_settings(settings_dict)
    
    # Return updated settings
    return await get_settings()


@router.get("/api/models", response_model=List[ModelInfo])
async def list_models():
    """List available/downloaded models with metadata from model_info.json files."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_infos = []
    
    for model_path in downloaded_models:
        try:
            # Get model info including metadata from model_info.json
            info = service_manager.llm_manager.downloader.get_model_info(model_path)
            
            # Use repo name if available from metadata, otherwise use filename
            if info.get("has_metadata") and info.get("repo_name"):
                display_name = info["repo_name"]
            else:
                display_name = info["name"]
            
            # Create unique model_id that includes path for models in subfolders
            # This helps distinguish between same-named files from different repos
            model_folder = service_manager.llm_manager.downloader.get_model_folder(model_path)
            if model_folder:
                # Include author/repo in the ID
                relative_path = model_path.relative_to(service_manager.llm_manager.downloader.models_dir)
                model_id = str(relative_path)
            else:
                model_id = model_path.name
            
            model_infos.append(ModelInfo(
                model_id=model_id,
                name=display_name,
                size=f"{info['size_gb']} GB" if info['size_gb'] >= 1 else f"{info['size_mb']} MB",
                format="gguf",
                downloaded=True,
                repo_id=info.get("repo_id"),
                author=info.get("author"),
                description=info.get("description"),
                huggingface_url=info.get("huggingface_url"),
                downloaded_at=info.get("downloaded_at"),
                has_metadata=info.get("has_metadata", False)
            ))
        except Exception as e:
            logger.warning(f"Error getting model info for {model_path.name}: {e}")
            # Skip models that can't be read
            continue
    
    return model_infos


@router.post("/api/models/discover")
async def discover_models(force_refresh: bool = Query(False, description="Re-discover already cataloged models")):
    """Discover manually added GGUF models and find their HuggingFace repositories.
    
    Scans the data/models directory for GGUF files, extracts metadata,
    and attempts to match each file to its HuggingFace repository.
    """
    from ..services.llm.discovery import ModelDiscovery
    from ..config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        results = await discovery.discover_all(force_refresh=force_refresh)
        
        return {
            "status": "success",
            "message": f"Discovered {len(results)} models",
            "models": results
        }
    except Exception as e:
        logger.error(f"Model discovery failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}") from e


@router.post("/api/models/{model_id}/discover")
async def discover_single_model(model_id: str):
    """Discover/rediscover a specific model and find its HuggingFace repository.
    
    Args:
        model_id: Model filename (e.g., "MistralRP-Noromaid-NSFW-7B-Q4_0.gguf")
    """
    from ..services.llm.discovery import ModelDiscovery
    from ..config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        metadata = await discovery.discover_model(model_path)
        
        return {
            "status": "success",
            "message": f"Discovered model: {model_id}",
            "metadata": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model discovery failed for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}") from e


@router.get("/api/models/{model_id}/metadata")
async def get_model_metadata(model_id: str):
    """Get discovered metadata for a model.
    
    Returns the stored metadata including HuggingFace repo info if discovered.
    """
    from ..services.llm.discovery import ModelDiscovery
    from ..config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        metadata = await discovery.get_model_metadata(model_id)
        
        if not metadata:
            raise HTTPException(status_code=404, detail=f"No metadata found for model: {model_id}")
        
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metadata for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}") from e


@router.put("/api/models/{model_id:path}/metadata")
async def set_model_metadata(model_id: str, request: Request):
    """Manually set or update metadata for a model.
    
    Use this for models that were manually downloaded or need custom metadata.
    Creates/updates model_info.json in the model's directory.
    
    Args:
        model_id: Model path (e.g., "model.gguf" or "author/repo/model.gguf")
        
    Body:
        name: Display name for the model
        author: Author/creator name  
        description: Model description
        repo_id: HuggingFace repository ID (optional)
        huggingface_url: Direct URL to model page (optional)
        tags: List of tags (optional)
    """
    from ..config.settings import settings
    import json
    from datetime import datetime
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        # Find the model file
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            # Try as just filename in flat structure
            flat_path = settings.models_dir / Path(model_id).name
            if flat_path.exists():
                model_path = flat_path
            else:
                raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        # Determine where to save metadata
        model_folder = model_path.parent
        metadata_file = model_folder / "model_info.json"
        
        # Load existing metadata if present
        existing_metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    existing_metadata = json.load(f)
            except Exception:
                pass
        
        # Build new metadata (merge with existing)
        new_metadata = {
            **existing_metadata,
            "filename": model_path.name,
            "name": body.get("name") or existing_metadata.get("name") or model_path.stem,
            "author": body.get("author") or existing_metadata.get("author") or "Unknown",
            "description": body.get("description") or existing_metadata.get("description") or "",
            "repo_id": body.get("repo_id") or existing_metadata.get("repo_id"),
            "huggingface_url": body.get("huggingface_url") or existing_metadata.get("huggingface_url"),
            "tags": body.get("tags") or existing_metadata.get("tags") or [],
            "source": body.get("source") or existing_metadata.get("source") or "manual",
            "updated_at": datetime.now().isoformat(),
        }
        
        # Set downloaded_at if not already present
        if "downloaded_at" not in new_metadata:
            new_metadata["downloaded_at"] = datetime.now().isoformat()
        
        # Generate huggingface_url from repo_id if not provided
        if new_metadata.get("repo_id") and not new_metadata.get("huggingface_url"):
            new_metadata["huggingface_url"] = f"https://huggingface.co/{new_metadata['repo_id']}"
        
        # Save metadata
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(new_metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved metadata for model: {model_id}")
        
        return {
            "status": "success",
            "message": f"Metadata updated for {model_id}",
            "metadata": new_metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set metadata for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set metadata: {str(e)}") from e


@router.post("/api/models/{model_id:path}/link")
async def link_and_organize_model(
    model_id: str,
    repo_id: str = Query(..., description="HuggingFace repository ID"),
    filename: Optional[str] = Query(None, description="New filename (optional)")
):
    """Link a model to a HuggingFace repo and move it to the correct folder.
    
    This is used to "fix" manually downloaded models by:
    1. Moving the model to the correct folder structure (author/repo/)
    2. Fetching and saving full metadata from HuggingFace
    
    Args:
        model_id: Current model path/identifier
        repo_id: HuggingFace repository ID (e.g., "TheBloke/Mistral-7B-GGUF")
        filename: Optional new filename
    """
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    try:
        result = await service_manager.llm_manager.downloader.link_and_organize_model(
            model_id=model_id,
            repo_id=repo_id,
            target_filename=filename
        )
        
        return {
            "status": "success",
            "message": f"Model linked and organized to {result['new_path']}",
            **result
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to link model {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to link model: {str(e)}") from e


@router.put("/api/models/{model_id}/repo")
async def set_model_repo(model_id: str, repo_id: str = Query(..., description="HuggingFace repository ID")):
    """Manually set the HuggingFace repository for a model and fetch its metadata.
    
    Use this if automatic discovery didn't find the correct repository.
    This will fetch full metadata from HuggingFace.
    
    Args:
        model_id: Model filename
        repo_id: HuggingFace repository ID (e.g., "TheBloke/MistralRP-Noromaid-7B-GGUF")
    """
    from ..services.llm.discovery import ModelDiscovery
    from ..config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        # First, ensure the model is in the database
        existing = await discovery.get_model_metadata(model_id)
        if not existing:
            await discovery.discover_model(model_path)
        
        # Update with the specified repo
        metadata = await discovery.update_model_repo(model_id, repo_id)
        
        return {
            "status": "success",
            "message": f"Updated repository for {model_id} to {repo_id}",
            "metadata": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set repo for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set repository: {str(e)}") from e


@router.get("/api/models/all-metadata")
async def get_all_model_metadata():
    """Get discovered metadata for all models."""
    from ..services.llm.discovery import ModelDiscovery
    from ..config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        all_metadata = await discovery.get_all_metadata()
        
        return {
            "status": "success",
            "count": len(all_metadata),
            "models": all_metadata
        }
    except Exception as e:
        logger.error(f"Failed to get all metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}") from e


@router.get("/api/models/files")
async def get_model_files(repo_id: str = Query(..., description="HuggingFace repository ID")):
    """Get list of files in a HuggingFace model repository (independent of LLM service)."""
    logger.info("get_model_files called with repo_id: %s", repo_id)
    
    try:
        from ..services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        
        # URL decode the repo_id in case it was double-encoded
        from urllib.parse import unquote
        decoded_repo_id = unquote(repo_id)
        logger.info("Decoded repo_id: %s", decoded_repo_id)
        
        # Additional validation: ensure repo_id has proper format
        if not decoded_repo_id or not decoded_repo_id.strip():
            logger.warning("Empty repo_id after decoding")
            raise HTTPException(
                status_code=400,
                detail="Repository ID cannot be empty"
            )
        
        # Validate format (should contain at least one slash)
        if '/' not in decoded_repo_id:
            logger.warning("Invalid repo_id format (no slash): %s", decoded_repo_id)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repository ID format: '{decoded_repo_id}'. Expected format: 'username/model-name'"
            )
        
        logger.info("Calling downloader.get_model_files with: %s", decoded_repo_id)
        files = await downloader.get_model_files(repo_id=decoded_repo_id)
        logger.info("Successfully retrieved %d files", len(files) if files else 0)
        return files
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Repository not found or invalid format
        error_msg = str(e)
        logger.warning("Invalid repository ID or not found: %s (decoded: %s) - %s", repo_id, decoded_repo_id, error_msg)
        # Check if it's actually a 404 or just a validation error
        if "not found" in error_msg.lower() or "not found on HuggingFace" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from e
        else:
            # Validation error, return 400
            raise HTTPException(status_code=400, detail=error_msg) from e
    except Exception as e:
        import traceback
        error_detail = f"Failed to list files for repository '{repo_id}': {str(e)}"
        logger.error("Error listing files: %s\n%s", error_detail, traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail) from e


@router.post("/api/models/download")
async def download_model(
    repo_id: str = Query(..., description="HuggingFace repository ID"),
    filename: Optional[str] = Query(None, description="Specific GGUF filename to download")
):
    """Start a model download with progress tracking.
    
    Returns a download ID that can be used to track progress.
    """
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = await manager.start_download(repo_id, filename)
        
        return {
            "status": "started",
            "message": f"Download started for {filename}",
            "download_id": download.id,
            "download": download.to_dict()
        }
    except Exception as e:
        logger.error(f"Failed to start download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start download: {str(e)}") from e


@router.get("/api/downloads")
async def list_downloads():
    """Get all active downloads and recent history."""
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        
        # Get active downloads
        active = [d.to_dict() for d in manager.get_active_downloads()]
        
        # Get history
        history = await manager.get_download_history(limit=20)
        
        return {
            "active": active,
            "history": history,
            "active_count": len(active)
        }
    except Exception as e:
        logger.error(f"Failed to list downloads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/downloads/{download_id}")
async def get_download_status(download_id: str):
    """Get status of a specific download."""
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = manager.get_download(download_id)
        
        if download:
            return download.to_dict()
        
        # Check history
        history = await manager.get_download_history(limit=100)
        for record in history:
            if record['id'] == download_id:
                return record
        
        raise HTTPException(status_code=404, detail=f"Download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get download status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/api/downloads/{download_id}")
async def cancel_download(download_id: str):
    """Cancel an active download."""
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        cancelled = await manager.cancel_download(download_id)
        
        if cancelled:
            return {"status": "cancelled", "download_id": download_id}
        else:
            raise HTTPException(status_code=404, detail=f"Active download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/downloads/{download_id}/retry")
async def retry_download(download_id: str):
    """Retry a failed download."""
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = await manager.retry_download(download_id)
        
        if download:
            return {
                "status": "started",
                "message": "Download retry started",
                "download_id": download.id,
                "download": download.to_dict()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Failed download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/api/downloads/history")
async def clear_download_history(keep_days: int = Query(7, description="Keep records from last N days")):
    """Clear old download history."""
    from ..services.llm.download_manager import get_download_manager
    from ..config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        deleted = await manager.clear_history(keep_days)
        
        return {
            "status": "success",
            "deleted_count": deleted,
            "kept_days": keep_days
        }
    except Exception as e:
        logger.error(f"Failed to clear history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/models/{model_id}/load")
async def load_model_by_id(
    model_id: str,
    options: Optional[ModelLoadOptions] = None
):
    """Load a model for inference with optional configuration.
    
    Args:
        model_id: Model identifier or filename
        options: Optional model loading configuration (llama-cpp-python parameters)
    """
    from ..config.settings import settings
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        # Match by filename, relative path, or full identifier
        try:
            relative_path = path.relative_to(settings.models_dir) if path.is_relative_to(settings.models_dir) else path
        except (ValueError, AttributeError):
            relative_path = path
        if (path.name == model_id or 
            str(path) == model_id or 
            str(relative_path) == model_id):
            model_path = path
            break
    
    if not model_path:
        # Try as direct path
        from pathlib import Path
        potential_path = Path(model_id)
        if potential_path.exists() and potential_path.suffix == ".gguf":
            model_path = potential_path
        else:
            # Also check in models directory
            potential_path = settings.models_dir / model_id
            if potential_path.exists() and potential_path.suffix == ".gguf":
                model_path = potential_path
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model {model_id} not found. Please download it first."
                )
    
    try:
        # Unload current model if loaded
        if service_manager.llm_manager.is_model_loaded():
            await service_manager.llm_manager.unload_model()
        
        # Build load options from ModelLoadOptions schema
        # Only include parameters that are explicitly set
        load_options: Dict[str, Any] = {}
        
        # Get auto-detected GPU layers as default
        auto_gpu_layers = service_manager.llm_manager.loader._gpu_layers
        
        if options:
            # Core parameters
            if options.n_ctx is not None:
                load_options['n_ctx'] = options.n_ctx
            if options.n_batch is not None:
                load_options['n_batch'] = options.n_batch
            if options.n_threads is not None:
                load_options['n_threads'] = options.n_threads
            if options.n_threads_batch is not None:
                load_options['n_threads_batch'] = options.n_threads_batch
                
            # GPU settings
            if options.n_gpu_layers is not None:
                load_options['n_gpu_layers'] = options.n_gpu_layers
                logger.info("GPU layers explicitly set to: %d", options.n_gpu_layers)
            else:
                load_options['n_gpu_layers'] = auto_gpu_layers
                logger.info("GPU layers not specified, using auto-detected: %d", auto_gpu_layers)
            if options.main_gpu is not None:
                load_options['main_gpu'] = options.main_gpu
            if options.tensor_split is not None:
                load_options['tensor_split'] = options.tensor_split
                
            # Memory settings
            if options.use_mmap is not None:
                load_options['use_mmap'] = options.use_mmap
            if options.use_mlock is not None:
                load_options['use_mlock'] = options.use_mlock
                
            # Performance - use flash_attn (correct name for llama-cpp-python)
            if options.flash_attn is not None:
                load_options['flash_attn'] = options.flash_attn
            elif options.use_flash_attention is not None:
                # Handle deprecated parameter
                load_options['flash_attn'] = options.use_flash_attention
                logger.warning("use_flash_attention is deprecated, use flash_attn")
                
            # RoPE settings
            if options.rope_freq_base is not None:
                load_options['rope_freq_base'] = options.rope_freq_base
            if options.rope_freq_scale is not None:
                load_options['rope_freq_scale'] = options.rope_freq_scale
            if options.rope_scaling_type is not None:
                load_options['rope_scaling_type'] = options.rope_scaling_type
                
            # YaRN settings
            if options.yarn_ext_factor is not None:
                load_options['yarn_ext_factor'] = options.yarn_ext_factor
            if options.yarn_attn_factor is not None:
                load_options['yarn_attn_factor'] = options.yarn_attn_factor
            if options.yarn_beta_fast is not None:
                load_options['yarn_beta_fast'] = options.yarn_beta_fast
            if options.yarn_beta_slow is not None:
                load_options['yarn_beta_slow'] = options.yarn_beta_slow
            if options.yarn_orig_ctx is not None:
                load_options['yarn_orig_ctx'] = options.yarn_orig_ctx
                
            # KV cache settings
            if options.cache_type_k is not None:
                load_options['cache_type_k'] = options.cache_type_k
            if options.cache_type_v is not None:
                load_options['cache_type_v'] = options.cache_type_v
                
            # MoE settings
            if options.n_cpu_moe is not None:
                load_options['n_cpu_moe'] = options.n_cpu_moe
                
            # Warn about deprecated/ignored parameters
            if options.offload_kqv is not None:
                logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
        else:
            # No options provided, use auto-detected GPU layers
            load_options['n_gpu_layers'] = auto_gpu_layers
            logger.info("No load options provided, using auto-detected GPU layers: %d", auto_gpu_layers)
        
        logger.info("=" * 60)
        logger.info("API: Loading model %s", model_id)
        logger.info("Options: %s", load_options)
        logger.info("=" * 60)
        
        # Convert to absolute path
        from pathlib import Path
        absolute_model_path = Path(model_path).resolve()
        
        # Load model via LLM manager
        success = await service_manager.llm_manager.load_model(
            str(absolute_model_path),
            **load_options
        )
        
        if success:
            logger.info("API: Model %s loaded successfully", model_id)
            supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
            return {
                "status": "success",
                "message": f"Model {model_id} loaded successfully",
                "model_path": str(model_path),
                "options_used": load_options,
                "supports_tool_calling": supports_tool_calling
            }
        else:
            error_msg = f"Failed to load model {model_id}"
            logger.error("API: %s", error_msg)
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Load failed: {str(e)}") from e


@router.get("/api/models/{model_id}/info", response_model=ModelMetadata)
async def get_model_info(model_id: str):
    """Get detailed model metadata including architecture, parameters, context length, MoE info."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        return ModelMetadata(**info)
    except Exception as e:
        logger.error(f"Error extracting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract model info: {str(e)}")


@router.get("/api/models/{model_id}/memory-estimate", response_model=MemoryEstimate)
async def get_memory_estimate(
    model_id: str,
    context_length: int = Query(2048, ge=512, le=32768),
    batch_size: int = Query(1, ge=1, le=32)
):
    """Get memory requirement estimate for a model with given context length."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    from ..services.llm.memory_calculator import memory_calculator
    
    # Find model file
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        # Extract model info
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        # Calculate memory estimate
        model_params = {
            "num_parameters": info.get("num_parameters"),
            "num_layers": info.get("num_layers", 32),
            "hidden_size": info.get("hidden_size", 4096),
            "quantization": info.get("quantization"),
            "model_name": info.get("name")
        }
        
        estimate = memory_calculator.estimate_total_memory(
            model_params,
            context_length=context_length,
            batch_size=batch_size
        )
        
        # Get recommended VRAM
        recommended_vram = memory_calculator.get_recommended_vram(estimate["total_gb"])
        estimate["recommended_vram_gb"] = recommended_vram
        
        # Check if it will fit
        try:
            import torch
            if torch.cuda.is_available():
                available_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                estimate["will_fit"] = estimate["total_gb"] <= available_vram
            else:
                estimate["will_fit"] = None
        except:
            estimate["will_fit"] = None
        
        return MemoryEstimate(**estimate)
    except Exception as e:
        logger.error(f"Error calculating memory estimate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate memory estimate: {str(e)}")


@router.get("/api/models/{model_id}/config")
async def get_model_config(model_id: str):
    """Get configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    return service_manager.llm_manager.get_model_config(model_id)

@router.put("/api/models/{model_id}/config")
async def save_model_config(model_id: str, config: ModelLoadOptions):
    """Save configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    service_manager.llm_manager.save_model_config(model_id, config.model_dump(exclude_unset=True))
    return {"status": "success"}

@router.post("/api/models/load")
async def load_model_direct(request: Dict[str, Any]):
    """Load a model by path (simplified endpoint).
    
    Accepts a JSON body with model_path and optional llama-cpp-python parameters.
    """
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
        
    model_path = request.get("model_path")
    if not model_path:
        raise HTTPException(status_code=400, detail="model_path is required")
        
    # Build clean options dict, mapping deprecated params
    clean_options: Dict[str, Any] = {}
    
    # Copy valid parameters
    valid_params = [
        'n_ctx', 'n_batch', 'n_threads', 'n_threads_batch',
        'n_gpu_layers', 'main_gpu', 'tensor_split',
        'use_mmap', 'use_mlock', 'flash_attn',
        'rope_freq_base', 'rope_freq_scale', 'rope_scaling_type',
        'yarn_ext_factor', 'yarn_attn_factor', 'yarn_beta_fast', 'yarn_beta_slow', 'yarn_orig_ctx',
        'cache_type_k', 'cache_type_v'
    ]
    
    for param in valid_params:
        if param in request and request[param] is not None:
            clean_options[param] = request[param]
    
    # Handle deprecated use_flash_attention -> flash_attn
    if 'use_flash_attention' in request and 'flash_attn' not in clean_options:
        clean_options['flash_attn'] = request['use_flash_attention']
        logger.warning("use_flash_attention is deprecated, use flash_attn")
    
    # Warn about ignored parameters
    if 'offload_kqv' in request:
        logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
    
    try:
        success = await service_manager.llm_manager.load_model(model_path, **clean_options)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to load model")
            
        return {"status": "success", "message": f"Loaded {model_path}", "options_used": clean_options}
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}") from e

@router.put("/api/conversations/{conversation_id}/rename")
async def rename_conversation(conversation_id: str, request: Request):
    """Rename a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    
    try:
        # Get request body
        body = await request.json()
        new_name = body.get("name")
        
        if not new_name:
            raise HTTPException(status_code=400, detail="Name is required in request body")
        
        # Update conversation name
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
        # Get request body
        body = await request.json()
        pinned = body.get("pinned", True)
        
        # Update pinned status
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


@router.post("/api/models/install-llama-cuda")
async def install_llama_cuda():
    """Install llama-cpp-python with CUDA support."""
    from ..services.llm.cuda_installer import install_llama_cuda, check_cuda_available, check_llama_cuda_support
    
    # Check if CUDA is available
    if not check_cuda_available():
        raise HTTPException(
            status_code=400,
            detail="No CUDA GPU detected. Cannot install CUDA-enabled llama-cpp-python."
        )
    
    # Check if already installed with CUDA
    has_cuda, error = check_llama_cuda_support()
    if has_cuda:
        return {
            "status": "success",
            "message": "llama-cpp-python already has CUDA support",
            "cuda_available": True
        }
    
    try:
        # Get Python executable
        import sys
        python_exe = sys.executable
        
        # Install with CUDA
        success, message = install_llama_cuda(python_exe)
        
        if success:
            return {
                "status": "success",
                "message": message,
                "cuda_available": True
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Installation failed: {message}"
            )
    except Exception as e:
        logger.error("Failed to install llama-cpp-python with CUDA: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Installation error: {str(e)}"
        ) from e


@router.delete("/api/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a downloaded model.
    
    Args:
        model_id: Model identifier or filename
    """
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Check if model is currently loaded
    current_model_path = service_manager.llm_manager.get_current_model_path()
    if current_model_path:
        from pathlib import Path
        current_model_name = Path(current_model_path).name
        if current_model_name == model_id or str(current_model_path) == model_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete model '{model_id}' - it is currently loaded. Please unload it first."
            )
    
    try:
        success = service_manager.llm_manager.downloader.delete_model(model_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Model {model_id} deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} not found"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("Delete failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}") from e


@router.get("/api/models/search")
async def search_models(
    query: str = Query(..., description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results")
):
    """Search for models on HuggingFace (independent of LLM service)."""
    try:
        # Use downloader directly - works independently
        from ..services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        results = await downloader.search_models(
            query=query,
            limit=limit
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}") from e


@router.get("/api/models/{model_id:path}/files")
async def get_model_files(model_id: str):
    """Get list of GGUF files for a specific model repository (independent of LLM service)."""
    try:
        from ..services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        logger.info(f"Fetching model files for: {model_id}")
        files = await downloader.get_model_files(model_id)
        return {"files": files}
    except ValueError as e:
        logger.error(f"ValueError getting model files for {model_id}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Exception getting model files for {model_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch model files: {str(e)}"
        ) from e


@router.get("/api/models/{model_id:path}/details")
async def get_model_details(model_id: str):
    """Get detailed information for a specific model repository (independent of LLM service)."""
    try:
        from ..services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        details = await downloader.get_model_details(model_id)
        return details
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch model details: {str(e)}"
        ) from e


@router.get("/api/tools")
async def list_tools():
    """List all available tools with their schemas."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        tools = await service_manager.tool_manager.list_tools()
        return {
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}") from e


@router.get("/api/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get information about a specific tool."""
    if not service_manager.tool_manager:
        raise HTTPException(
            status_code=503,
            detail="Tool service not initialized"
        )
    
    try:
        tool_schema = await service_manager.tool_manager.get_tool_schema(tool_name)
        if not tool_schema:
            raise HTTPException(
                status_code=404,
                detail=f"Tool '{tool_name}' not found"
            )
        
        return tool_schema
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tool info: {str(e)}") from e


# System Prompt Management (proxied to Memory service)
@router.get("/api/settings/system-prompt")
async def get_system_prompt(prompt_id: Optional[str] = Query(None)):
    """Get system prompt from Memory service.
    
    Returns empty/default prompt if none exists (instead of 404).
    """
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        prompt = await service_manager.memory_store.get_system_prompt(prompt_id=prompt_id)
        if prompt is None:
            # Return empty/default prompt instead of 404
            return {
                "id": None,
                "content": "",
                "name": None,
                "is_default": False
            }
        return prompt
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system prompt: {str(e)}") from e


@router.post("/api/settings/system-prompt")
async def set_system_prompt(request: Request):
    """Create or update system prompt in Memory service."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        prompt_id = await service_manager.memory_store.set_system_prompt(
            content=body.get("content", ""),
            name=body.get("name"),
            is_default=body.get("is_default", False)
        )
        return {"id": prompt_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set system prompt: {str(e)}") from e


@router.put("/api/settings/system-prompt/{prompt_id}")
async def update_system_prompt(prompt_id: str, request: Request):
    """Update system prompt in Memory service."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        updated_id = await service_manager.memory_store.set_system_prompt(
            content=body.get("content", ""),
            name=body.get("name"),
            prompt_id=prompt_id,
            is_default=body.get("is_default", False)
        )
        return {"id": updated_id, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update system prompt: {str(e)}") from e


@router.get("/api/settings/system-prompts")
async def list_system_prompts():
    """List all system prompts from Memory service."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        prompts = await service_manager.memory_store.list_system_prompts()
        return prompts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list system prompts: {str(e)}") from e


@router.delete("/api/settings/system-prompt/{prompt_id}")
async def delete_system_prompt(prompt_id: str):
    """Delete system prompt from Memory service."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        success = await service_manager.memory_store.delete_system_prompt(prompt_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="System prompt not found"
            )
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete system prompt: {str(e)}") from e


# Memory/Context Settings Endpoints
@router.get("/api/settings/vector-memory")
async def get_vector_memory_settings():
    """Get global vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        settings = await service_manager.memory_store.get_vector_memory_settings()
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vector memory settings: {str(e)}") from e


@router.put("/api/settings/vector-memory")
async def set_vector_memory_settings(request: Request):
    """Update global vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        await service_manager.memory_store.set_vector_memory_settings(body)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set vector memory settings: {str(e)}") from e


@router.get("/api/conversations/{conversation_id}/vector-memory")
async def get_conversation_vector_memory_settings(conversation_id: str):
    """Get per-conversation vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        settings = await service_manager.memory_store.get_conversation_vector_memory_settings(conversation_id)
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversation vector memory settings: {str(e)}") from e


@router.put("/api/conversations/{conversation_id}/vector-memory")
async def set_conversation_vector_memory_settings(conversation_id: str, request: Request):
    """Update per-conversation vector memory settings."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        await service_manager.memory_store.set_conversation_vector_memory_settings(conversation_id, body)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set conversation vector memory settings: {str(e)}") from e


@router.get("/api/settings/memory")
async def get_memory_settings():
    """Get memory/context retrieval settings (similarity threshold, top-k).
    
    These settings control HOW vector memory retrieval works:
    - similarity_threshold: Minimum similarity score (0-1) for context retrieval
    - top_k: Maximum number of relevant past messages to retrieve
    """
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        # Get persisted settings from memory store
        similarity_threshold = await service_manager.memory_store.get_setting("memory_similarity_threshold", "0.7")
        top_k = await service_manager.memory_store.get_setting("memory_top_k", "5")
        
        return {
            "similarity_threshold": float(similarity_threshold),
            "top_k": int(top_k)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get memory settings: {str(e)}") from e


@router.put("/api/settings/memory")
async def update_memory_settings(request: Request):
    """Update memory/context retrieval settings (similarity threshold, top-k).
    
    These settings control HOW vector memory retrieval works:
    - similarity_threshold: Minimum similarity score (0-1) for context retrieval
    - top_k: Maximum number of relevant past messages to retrieve
    """
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        body = await request.json()
        
        # Validate and persist settings
        if "similarity_threshold" in body:
            threshold = float(body["similarity_threshold"])
            if not 0 <= threshold <= 1:
                raise HTTPException(status_code=400, detail="similarity_threshold must be between 0 and 1")
            await service_manager.memory_store.set_setting("memory_similarity_threshold", str(threshold))
        
        if "top_k" in body:
            top_k = int(body["top_k"])
            if top_k < 1:
                raise HTTPException(status_code=400, detail="top_k must be at least 1")
            await service_manager.memory_store.set_setting("memory_top_k", str(top_k))
        
        return {
            "status": "success",
            "message": "Memory retrieval settings updated"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update memory settings: {str(e)}") from e


# File Upload Endpoints (for data/files/ directory)
@router.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload file to data/files/ directory."""
    from pathlib import Path
    import aiofiles
    from ..config.settings import settings
    
    # Ensure data/files/ directory exists
    files_dir = settings.data_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename
    filename = file.filename or "uploaded_file"
    # Remove path traversal attempts
    filename = Path(filename).name
    # Allow only safe characters
    safe_filename = "".join(c for c in filename if c.isalnum() or c in ('-', '_', '.')).strip()
    
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    file_path = files_dir / safe_filename
    
    # Check if file already exists, add number suffix
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = files_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    
    try:
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        return {
            "status": "success",
            "filename": file_path.name,
            "path": str(file_path.relative_to(settings.base_dir)),
            "size": len(content)
        }
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}") from e


@router.get("/api/files")
async def list_files():
    """List files in data/files/ directory."""
    from pathlib import Path
    from ..config.settings import settings
    
    files_dir = settings.data_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        files = []
        for file_path in files_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"Error listing files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}") from e


@router.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """Delete file from data/files/ directory."""
    from pathlib import Path
    from ..config.settings import settings
    
    files_dir = settings.data_dir / "files"
    
    # Sanitize filename
    safe_filename = Path(filename).name
    file_path = files_dir / safe_filename
    
    # Ensure file is within files_dir (prevent path traversal)
    try:
        file_path.resolve().relative_to(files_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        file_path.unlink()
        return {"status": "success", "message": f"File {filename} deleted"}
    except Exception as e:
        logger.error(f"Error deleting file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}") from e


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    # Delete from chat manager (which also deletes from memory store)
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
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    try:
        # Get all conversation IDs (excluding pinned ones)
        stored_conversations = await service_manager.memory_store.list_conversations()
        conversation_ids = [
            conv["conversation_id"] 
            for conv in stored_conversations 
            if not conv.get("pinned", False)
        ]
        
        # Delete each conversation
        deleted_count = 0
        for conv_id in conversation_ids:
            deleted = await service_manager.chat_manager.delete_conversation(conv_id)
            if deleted:
                deleted_count += 1
        
        pinned_count = len(stored_conversations) - len(conversation_ids)
        logger.info(f"Deleted {deleted_count} out of {len(conversation_ids)} conversations ({pinned_count} pinned conversations preserved)")
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} conversations",
            "deleted_count": deleted_count,
            "total_count": len(conversation_ids),
            "pinned_preserved": pinned_count
        }
    except Exception as e:
        logger.error(f"Error deleting all conversations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete all conversations: {str(e)}"
        ) from e


@router.post("/api/reset")
async def reset_app_state(keep_models: bool = True):
    """Reset all app state (conversations, settings, vector store).
    
    This will delete:
    - All conversations
    - All settings
    - Vector store data
    
    But will keep:
    - Downloaded models (if keep_models=True)
    """
    from ..services.memory.file_store import FileConversationStore
    from ..services.memory.settings_store import FileSettingsStore
    from ..services.memory.vector_store import VectorStore
    from ..config.settings import settings
    
    try:
        results = {
            "conversations_deleted": 0,
            "settings_cleared": False,
            "vector_store_cleared": False
        }
        
        # Clear conversations
        file_store = FileConversationStore(settings.memory_dir)
        results["conversations_deleted"] = await file_store.clear_all()
        
        # Clear settings
        settings_store = FileSettingsStore(settings.memory_dir)
        results["settings_cleared"] = await settings_store.clear_all()
        
        # Clear vector store
        try:
            vector_store = VectorStore()
            if vector_store.collection and vector_store.store_type == "chromadb":
                all_results = vector_store.collection.get()
                if all_results and "ids" in all_results and all_results["ids"]:
                    vector_store.collection.delete(ids=all_results["ids"])
                    logger.info(f"Deleted {len(all_results['ids'])} entries from vector store")
            results["vector_store_cleared"] = True
        except Exception as e:
            logger.warning(f"Could not clear vector store: {e}")
            results["vector_store_cleared"] = False
        
        logger.info(f"App state reset completed: {results}")
        return {
            "status": "success",
            "message": "App state reset successfully",
            **results
        }
    except Exception as e:
        logger.error(f"Error resetting app state: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset app state: {str(e)}"
        ) from e


@router.post("/api/conversations/cleanup")
async def cleanup_conversations():
    """Clean up stale conversation entries (removes entries from index where files don't exist)."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not initialized"
        )
    
    try:
        # List conversations - this automatically cleans up stale entries
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


@router.get("/api/debug/info")
async def get_debug_info():
    """Get debug information about system status."""
    logger.info("GET /api/debug/info - Fetching debug information")
    debug_info = {
        "services": {},
        "model": {},
        "memory": {},
        "conversations": {}
    }
    
    # Service status
    debug_info["services"] = {
        "llm_manager": service_manager.llm_manager is not None,
        "chat_manager": service_manager.chat_manager is not None,
        "memory_store": service_manager.memory_store is not None,
        "tool_manager": service_manager.tool_manager is not None,
        "stt_service": service_manager.stt_service is not None,
        "tts_service": service_manager.tts_service is not None
    }
    
    # Model information
    if service_manager.llm_manager:
        sampler_settings = service_manager.llm_manager.get_settings()
        debug_info["model"] = {
            "loaded": service_manager.llm_manager.is_model_loaded(),
            "current_model": service_manager.llm_manager.get_current_model_path(),
            "gpu_layers": getattr(service_manager.llm_manager.loader, '_gpu_layers', 0) if hasattr(service_manager.llm_manager, 'loader') else 0,
            "last_request_time": getattr(service_manager.llm_manager, '_last_request_time', None),
            "last_request_info": getattr(service_manager.llm_manager, '_last_request_info', None),
            "sampler_settings": sampler_settings
        }
    
    # Memory information
    if service_manager.memory_store:
        debug_info["memory"] = {
            "conversation_count": await service_manager.memory_store.get_conversation_count(),
            "message_count": await service_manager.memory_store.get_message_count(),
            "db_size_bytes": await service_manager.memory_store.get_db_size(),
            "last_entry": await service_manager.memory_store.get_last_entry_timestamp(),
            "vector_store": await service_manager.memory_store.get_vector_store_stats()
        }
    
    # Conversation information
    if service_manager.chat_manager:
        try:
            conversation_ids = await service_manager.chat_manager.list_conversations()
            debug_info["conversations"] = {
                "active_count": len(conversation_ids),
                "conversation_ids": conversation_ids
            }
        except Exception as e:
            logger.error(f"Error getting conversation info: {e}", exc_info=True)
            debug_info["conversations"] = {
                "active_count": 0,
                "conversation_ids": [],
                "error": str(e)
            }
    
    return debug_info


# OpenAI-compatible proxy endpoints
@router.get("/v1/models")
async def proxy_list_models():
    """Proxy GET /v1/models to LLM service."""
    try:
        from ..services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        service_url = service_mgr.get_service_url()
        
        # Check if service is running
        if not await service_mgr.is_service_running():
            raise HTTPException(
                status_code=503,
                detail="LLM service not running. Please start it via the launcher."
            )
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{service_url}/v1/models")
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "application/json")
            )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LLM service not available")
    except Exception as e:
        logger.error(f"Error proxying /v1/models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")


@router.get("/api/llm/status")
async def get_llm_status():
    """Get LLM service status."""
    try:
        from ..services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        status = await service_mgr.get_service_status()
        return status
    except Exception as e:
        logger.error(f"Error getting LLM service status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/models/{model_id}")
async def proxy_get_model(model_id: str):
    """Proxy GET /v1/models/:id to LLM service."""
    try:
        from ..services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        service_url = service_mgr.get_service_url()
        
        if not await service_mgr.is_service_running():
            raise HTTPException(
                status_code=503,
                detail="LLM service not running. Please start it via the launcher."
            )
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{service_url}/v1/models/{model_id}")
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "application/json")
            )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LLM service not available")
    except Exception as e:
        logger.error(f"Error proxying /v1/models/{model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")


async def save_messages_to_vector_store(
    conversation_id: str,
    user_messages: List[Dict[str, Any]],
    assistant_content: str
):
    """Helper function to save messages to vector store."""
    if not service_manager.memory_store:
        return
    
    try:
        # Extract user message content
        user_content = ""
        for msg in user_messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break
        
        # Create messages for storage
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


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    x_conversation_id: Optional[str] = Header(None, alias="X-Conversation-ID")
):
    """Proxy POST /v1/chat/completions to llama-cpp-python server with vector store integration."""
    try:
        # Parse request body
        body = await request.json()
        messages = body.get("messages", [])
        stream = body.get("stream", False)
        
        # Extract conversation_id from header or body
        conversation_id = x_conversation_id or body.get("conversation_id")
        
        # Check if model supports tool calling - remove tools from request if not supported
        if service_manager.llm_manager and not service_manager.llm_manager.supports_tool_calling:
            if "tools" in body and body.get("tools"):
                logger.debug("Removing tools from request - model does not support tool calling")
                # Create new body dict without tools
                body = {k: v for k, v in body.items() if k != "tools"}
        
        # Retrieve context from vector store if conversation_id provided
        if conversation_id and service_manager.memory_store:
            try:
                # Get system prompt from Memory service
                system_prompt_data = await service_manager.memory_store.get_system_prompt()
                system_prompt = system_prompt_data.get("content", "") if system_prompt_data else ""
                
                # Get last user message for context retrieval
                last_user_message = None
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        last_user_message = msg.get("content", "")
                        break
                
                # Retrieve context from Memory service
                context_str = ""
                if last_user_message:
                    context = await service_manager.memory_store.retrieve_context(
                        query=last_user_message,
                        exclude_conversation_id=conversation_id
                    )
                    
                    # Format context for injection
                    if context and context.get("retrieved_messages"):
                        context_str = "\n\nRelevant context from past conversations:\n" + "\n".join(
                            f"- {msg}" for msg in context["retrieved_messages"][:5]
                        )
                
                # Combine system prompt and context
                combined_system_content = system_prompt
                if context_str:
                    combined_system_content += context_str
                
                # Add or update system message
                if combined_system_content:
                    system_msg_found = False
                    for msg in messages:
                        if msg.get("role") == "system":
                            msg["content"] = combined_system_content
                            system_msg_found = True
                            break
                    
                    if not system_msg_found:
                        messages.insert(0, {
                            "role": "system",
                            "content": combined_system_content
                        })
            except Exception as e:
                logger.warning(f"Error retrieving context or system prompt: {e}", exc_info=True)
        
        # Get LLM service URL
        from ..services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        service_url = service_mgr.get_service_url()
        
        # Check if service is running
        if not await service_mgr.is_service_running():
            raise HTTPException(
                status_code=503,
                detail="LLM service not running. Please start it via the launcher."
            )
        
        # Proxy to LLM service
        async with httpx.AsyncClient(timeout=300.0) as client:
            if stream:
                # Streaming response
                async with client.stream(
                    "POST",
                    f"{service_url}/v1/chat/completions",
                    json={**body, "messages": messages},
                    headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
                ) as response:
                    # Accumulate streamed content for saving
                    accumulated_content = []
                    accumulated_chunks = []
                    
                    async def stream_with_save():
                        async for chunk in response.aiter_bytes():
                            accumulated_chunks.append(chunk)
                            # Try to extract content from SSE chunks
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
                                                except:
                                                    pass
                            except:
                                pass
                            yield chunk
                        
                        # Save after stream completes
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
            else:
                # Non-streaming response
                resp = await client.post(
                    f"{service_url}/v1/chat/completions",
                    json={**body, "messages": messages},
                    headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
                )
                
                # Parse response and handle function calls
                resp_data = resp.json()
                
                # Check if response contains function calls as text (needs parsing)
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    message_obj = resp_data["choices"][0].get("message", {})
                    content = message_obj.get("content", "")
                    
                    # If no tool_calls in response but content contains function call syntax, parse it
                    if not message_obj.get("tool_calls") and content:
                        from ..services.tools.parser import ToolCallParser
                        parser = ToolCallParser()
                        
                        # Try to parse function calls from content
                        parsed_tool_calls = parser.parse(content)
                        
                        if parsed_tool_calls:
                            # Convert to OpenAI format
                            tool_calls = []
                            for i, tc in enumerate(parsed_tool_calls):
                                tool_calls.append({
                                    "id": f"call_{i}_{hash(str(tc))}",
                                    "type": "function",
                                    "function": {
                                        "name": tc.get("name"),
                                        "arguments": json.dumps(tc.get("arguments", {}))
                                    }
                                })
                            
                            # Remove function call text from content, but preserve any natural language
                            # Use the parser's JSON extraction to find and remove the exact JSON objects
                            cleaned_content = content
                            for tc in parsed_tool_calls:
                                tool_name = tc.get("name", "")
                                # Try to find and remove the exact JSON object
                                import re
                                # More robust: find opening brace, then match until closing brace
                                start_idx = cleaned_content.find(f'{{"name": "{tool_name}"')
                                if start_idx == -1:
                                    start_idx = cleaned_content.find(f'{{ "name": "{tool_name}"')
                                if start_idx != -1:
                                    # Find matching closing brace
                                    brace_count = 0
                                    end_idx = start_idx
                                    for i in range(start_idx, len(cleaned_content)):
                                        if cleaned_content[i] == '{':
                                            brace_count += 1
                                        elif cleaned_content[i] == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                end_idx = i + 1
                                                break
                                    if end_idx > start_idx:
                                        # Remove the JSON object but preserve surrounding text
                                        # Check if there's text before or after
                                        before = cleaned_content[:start_idx].strip()
                                        after = cleaned_content[end_idx:].strip()
                                        # Remove the JSON and join remaining parts
                                        parts = []
                                        if before:
                                            parts.append(before)
                                        if after:
                                            parts.append(after)
                                        cleaned_content = ' '.join(parts)
                                        # Clean up extra whitespace/newlines
                                        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
                            
                            # Update response - preserve content if there's any natural language left
                            message_obj["tool_calls"] = tool_calls
                            # Only set content to None if there's truly no natural language
                            final_content = cleaned_content.strip() if cleaned_content.strip() else None
                            message_obj["content"] = final_content
                            resp_data["choices"][0]["message"] = message_obj
                            
                            # Update finish_reason if tool calls found
                            if tool_calls:
                                resp_data["choices"][0]["finish_reason"] = "tool_calls"
                
                # Save to vector store
                if conversation_id and service_manager.memory_store:
                    try:
                        assistant_content = ""
                        if "choices" in resp_data and len(resp_data["choices"]) > 0:
                            assistant_content = resp_data["choices"][0].get("message", {}).get("content", "")
                        
                        if assistant_content:
                            background_tasks.add_task(
                                save_messages_to_vector_store,
                                conversation_id,
                                messages,
                                assistant_content
                            )
                    except Exception as e:
                        logger.warning(f"Error parsing response for vector store: {e}")
                
                # Return modified response if we parsed tool calls
                if "choices" in resp_data and resp_data["choices"][0].get("message", {}).get("tool_calls"):
                    return Response(
                        content=json.dumps(resp_data).encode('utf-8'),
                        status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json")
                    )
                else:
                    return Response(
                        content=resp.content,
                        status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json")
                    )
                
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LLM service not available")
    except Exception as e:
        logger.error(f"Error proxying /v1/chat/completions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")


@router.post("/v1/completions")
async def proxy_completions(request: Request):
    """Proxy POST /v1/completions to LLM service."""
    try:
        from ..services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        service_url = service_mgr.get_service_url()
        
        if not await service_mgr.is_service_running():
            raise HTTPException(
                status_code=503,
                detail="LLM service not running. Please start it via the launcher."
            )
        
        body = await request.body()
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{service_url}/v1/completions",
                content=body,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type", "application/json")
            )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="LLM service not available")
    except Exception as e:
        logger.error(f"Error proxying /v1/completions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")
