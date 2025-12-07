"""Chat endpoint routes."""
import time
import logging
from fastapi import APIRouter, HTTPException, Request

from ..schemas import ChatRequest, ChatResponse, MessageMetadata
from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


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
        
        # DRY (Dynamic Repetition Penalty)
        if request.dry_multiplier is not None:
            sampler_params["dry_multiplier"] = request.dry_multiplier
        if request.dry_base is not None:
            sampler_params["dry_base"] = request.dry_base
        if request.dry_allowed_length is not None:
            sampler_params["dry_allowed_length"] = request.dry_allowed_length
        
        # Update LLM manager settings for metadata
        service_manager.llm_manager.update_settings({
            "temperature": sampler_params["temperature"],
            "top_p": sampler_params["top_p"],
            "top_k": sampler_params["top_k"],
            "max_tokens": sampler_params["max_tokens"],
        })
        
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
    """Regenerate the last assistant response in a conversation."""
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
        
        # Find the last user message
        last_user_index = -1
        for i in range(len(conversation) - 1, -1, -1):
            if conversation[i].get("role") == "user":
                last_user_index = i
                break
        
        if last_user_index == -1:
            raise HTTPException(status_code=400, detail="No user message found to regenerate from")
        
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
        start_time = time.time()
        
        result = await service_manager.chat_manager.send_message(
            message=user_message,
            conversation_id=conversation_id,
            sampler_params=sampler_params
        )
        
        generation_time_ms = (time.time() - start_time) * 1000
        
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
