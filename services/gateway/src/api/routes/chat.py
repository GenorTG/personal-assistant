"""Chat endpoint routes."""
# Standard library
import asyncio
import json
import logging
import time

# Third-party
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

# Local
from ..schemas import ChatRequest, ChatResponse, MessageMetadata
from ...config.settings import settings
from ...services.service_manager import service_manager
from ...utils.request_logger import get_request_log_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat(request: ChatRequest, stream: bool = True):
    """Handle chat request with optional streaming support."""
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
    
    # Validate request
    if not request.message or not isinstance(request.message, str) or len(request.message.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="Message must be a non-empty string"
        )
    
    try:
        start_time = time.time()
        logger.debug(f"Chat request received: message='{request.message[:50]}...', conversation_id={request.conversation_id}")
        
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
        try:
            saved_settings = service_manager.llm_manager.get_settings()
            logger.debug(f"get_settings() returned: {type(saved_settings)}, keys: {list(saved_settings.keys()) if isinstance(saved_settings, dict) else 'N/A'}")
        except Exception as e:
            logger.error(f"Error calling get_settings(): {e}", exc_info=True)
            saved_settings = {}
        
        # Validate saved_settings
        if saved_settings is None:
            logger.warning("get_settings() returned None, using defaults")
            saved_settings = {}
        if not isinstance(saved_settings, dict):
            logger.warning(f"get_settings() returned invalid type: {type(saved_settings)}, using defaults")
            saved_settings = {}
        
        # Build sampler parameters for this request
        try:
            sampler_params = {
                "temperature": request.temperature if request.temperature is not None else saved_settings.get("temperature", 0.7),
                "top_p": request.top_p if request.top_p is not None else saved_settings.get("top_p", 0.9),
                "top_k": request.top_k if request.top_k is not None else saved_settings.get("top_k", 40),
                "max_tokens": request.max_tokens if request.max_tokens is not None else saved_settings.get("max_tokens", 512),
            }
            logger.debug(f"Created sampler_params with keys: {list(sampler_params.keys())}")
        except Exception as e:
            logger.error(f"Error creating sampler_params: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error creating sampler parameters: {str(e)}"
            ) from e
        
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
        #if request.dry_multiplier is not None:
        #    sampler_params["dry_multiplier"] = request.dry_multiplier
        #if request.dry_base is not None:
        #    sampler_params["dry_base"] = request.dry_base
        #if request.dry_allowed_length is not None:
        #    sampler_params["dry_allowed_length"] = request.dry_allowed_length
        
        # Validate sampler_params
        if sampler_params is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to create sampler parameters"
            )
        if not isinstance(sampler_params, dict):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid sampler_params type: {type(sampler_params)}"
            )
        
        # Update LLM manager settings for metadata
        # Include stop tokens if provided in request
        update_dict = {
            "temperature": sampler_params["temperature"],
            "top_p": sampler_params["top_p"],
            "top_k": sampler_params["top_k"],
            "max_tokens": sampler_params["max_tokens"],
        }
        # Add stop tokens if provided in request
        if request.stop is not None:
            update_dict["stop"] = request.stop
        service_manager.llm_manager.update_settings(update_dict)
        
        # Send message with sampler parameters
        try:
            logger.debug(f"Calling send_message with sampler_params type: {type(sampler_params)}")
            result = await service_manager.chat_manager.send_message(
                message=request.message,
                conversation_id=request.conversation_id,
                sampler_params=sampler_params
            )
            logger.debug(f"send_message returned type: {type(result)}, value: {result}")
        except Exception as e:
            logger.error(f"Error in send_message: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error calling send_message: {str(e)}"
            ) from e
        
        # Validate result
        if result is None:
            logger.error("send_message returned None")
            raise HTTPException(
                status_code=500,
                detail="Chat manager returned None response"
            )
        if not isinstance(result, dict):
            logger.error(f"send_message returned invalid type: {type(result)}, value: {result}")
            raise HTTPException(
                status_code=500,
                detail=f"Chat manager returned invalid response type: {type(result)}"
            )
        
        # Calculate generation time
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Create metadata - ensure sampler_params is valid before accessing
        try:
            if sampler_params is None or not isinstance(sampler_params, dict):
                logger.error(f"sampler_params is invalid: {sampler_params}")
                raise HTTPException(
                    status_code=500,
                    detail="Invalid sampler_params when creating metadata"
                )
            
            if result is None or not isinstance(result, dict):
                logger.error(f"result is invalid: {result}")
                raise HTTPException(
                    status_code=500,
                    detail="Invalid result when creating metadata"
                )
            
            logger.debug(f"Creating metadata with sampler_params keys: {list(sampler_params.keys())}")
            logger.debug(f"Creating metadata with result keys: {list(result.keys())}")
            
            metadata = MessageMetadata(
                model_name=service_manager.llm_manager.current_model_name if service_manager.llm_manager else None,
                generation_time_ms=round(generation_time_ms, 2),
                context_length=settings.llm_context_size if service_manager.llm_manager else None,
                temperature=sampler_params.get("temperature") if sampler_params else None,
                top_p=sampler_params.get("top_p") if sampler_params else None,
                top_k=sampler_params.get("top_k") if sampler_params else None,
                repeat_penalty=sampler_params.get("repeat_penalty") if sampler_params else None,
                retrieved_context=result.get("context_used", []) if result else []
            )
            
            logger.debug("Metadata created successfully")
            
            # Get logs if available
            log_store = get_request_log_store()
            logs = log_store.get_logs() if log_store else None
            
            return ChatResponse(
                response=result.get("response", "") if result else "",
                conversation_id=result.get("conversation_id", "") if result else "",
                context_used=result.get("context_used", []) if result else [],
                tool_calls=result.get("tool_calls") if result else None,
                metadata=metadata,
                logs=logs
            )
        except AttributeError as e:
            logger.error(f"AttributeError creating metadata: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error creating metadata: {str(e)}"
            ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}") from e


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Handle streaming chat request with configurable modes.
    
    Modes:
    - "streaming": Real-time streaming, no tool calling
    - "non-streaming": Full response with tool calling (simulated streaming)
    - "experimental": Pre-check for tool calls, then choose mode
    """
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
    
    # Validate request
    if not request.message or not isinstance(request.message, str) or len(request.message.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="Message must be a non-empty string"
        )
    
    async def generate_stream():
        try:
            # Get streaming mode from settings store
            streaming_mode = await service_manager.memory_store.settings_store.get_setting("streaming_mode", "non-streaming")
            
            # Get sampler settings
            saved_settings = service_manager.llm_manager.get_settings() or {}
            sampler_params = {
                "temperature": request.temperature if request.temperature is not None else saved_settings.get("temperature", 0.7),
                "top_p": request.top_p if request.top_p is not None else saved_settings.get("top_p", 0.9),
                "top_k": request.top_k if request.top_k is not None else saved_settings.get("top_k", 40),
                "max_tokens": request.max_tokens if request.max_tokens is not None else saved_settings.get("max_tokens", 512),
            }
            
            conversation_id = request.conversation_id
            if not conversation_id:
                from ...services.chat.manager import generate_conversation_id
                conversation_id = generate_conversation_id()
            
            # EXPERIMENTAL MODE: Pre-check if tool call is needed
            if streaming_mode == "experimental":
                logger.info("[CHAT STREAM] Experimental mode: Pre-checking for tool call necessity")
                needs_tool_call = await _check_if_tool_call_needed(request.message)
                if needs_tool_call:
                    logger.info("[CHAT STREAM] Experimental mode: Tool call detected, using non-streaming with tool calling")
                    streaming_mode = "non-streaming"
                else:
                    logger.info("[CHAT STREAM] Experimental mode: No tool call needed, using real streaming")
                    streaming_mode = "streaming"
            
            # STREAMING MODE: Real-time streaming, no tool calling
            if streaming_mode == "streaming":
                logger.info("[CHAT STREAM] Using real streaming mode (no tool calling)")
                async for chunk in _stream_real_time(request.message, conversation_id, sampler_params):
                    yield chunk
            
            # NON-STREAMING MODE: Full response with tool calling (simulated streaming)
            else:
                logger.info("[CHAT STREAM] Using non-streaming mode with tool calling (simulated streaming)")
                result = await service_manager.chat_manager.send_message(
                    message=request.message,
                    conversation_id=conversation_id,
                    sampler_params=sampler_params
                )
                
                final_response = result.get("response", "")
                tool_calls = result.get("tool_calls", [])
                conversation_id = result.get("conversation_id", "")
                
                logger.info(f"[CHAT STREAM] Got response (length: {len(final_response)}, tool_calls: {len(tool_calls)})")
                
                # Stream the final response in chunks (simulated streaming)
                chunk_size = 10
                for i in range(0, len(final_response), chunk_size):
                    chunk = final_response[i:i + chunk_size]
                    yield f"data: {json.dumps({'content': chunk, 'done': False})}\n\n"
                    await asyncio.sleep(0.01)
                
                yield f"data: {json.dumps({'content': '', 'done': True, 'conversation_id': conversation_id, 'tool_calls': tool_calls if tool_calls else None})}\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming chat: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


async def _check_if_tool_call_needed(message: str) -> bool:
    """Pre-check if a tool call is likely needed based on the message.
    
    Uses a quick LLM call to determine if tools are needed.
    """
    if not service_manager.llm_manager or not service_manager.llm_manager.supports_tool_calling:
        return False
    
    if not service_manager.tool_manager:
        return False
    
    try:
        # Get available tools
        tools = await service_manager.tool_manager.list_tools()
        if not tools:
            return False
        
        tool_names = [t.get('function', {}).get('name', '') for t in tools]
        tool_list = ', '.join(tool_names)
            
        # Quick check prompt
        check_prompt = f"""Analyze this user message and determine if it requires using any of these tools: {tool_list}

User message: "{message}"

Respond with ONLY "YES" if a tool is needed, or "NO" if no tool is needed. Do not explain."""
        
        # Make a quick, low-token call to check
        server_url = service_manager.llm_manager.server_manager.get_server_url()
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{server_url}/v1/chat/completions",
                json={
                    "model": service_manager.llm_manager.current_model_name or "default",
                    "messages": [
                        {"role": "system", "content": "You are a tool detection assistant. Answer only YES or NO."},
                        {"role": "user", "content": check_prompt}
                    ],
                    "max_tokens": 10,
                    "temperature": 0.0
                }
            )
            response.raise_for_status()
            result = response.json()
            answer = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            return answer.startswith("YES")
    except Exception as e:
        logger.warning(f"Error in tool call pre-check: {e}, defaulting to non-streaming")
        return True  # Default to non-streaming if check fails


async def _stream_real_time(message: str, conversation_id: str, sampler_params: dict):
    """Stream response in real-time from LLM server (no tool calling)."""
    # Get conversation history
    await service_manager.chat_manager._initialize()
    if conversation_id in service_manager.chat_manager.conversations:
        history = service_manager.chat_manager.conversations[conversation_id]
    else:
        history = []
        service_manager.chat_manager.conversations[conversation_id] = []
            
    # Store user message
    user_msg = {
        "role": "user",
        "content": message,
        "timestamp": time.time()
    }
    history.append(user_msg)
    
    # Build OpenAI-compatible messages (filter assistant messages without tool_calls)
    openai_messages = []
    system_prompt = service_manager.llm_manager._build_system_prompt()
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    
    for msg in history[:-1]:
        if not isinstance(msg, dict) or "role" not in msg:
            continue
        role = msg.get("role")
        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if not tool_calls or (isinstance(tool_calls, list) and len(tool_calls) == 0):
                continue
            openai_messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls
            })
        elif role == "tool":
            openai_messages.append({
                "role": "tool",
                "content": msg.get("content", ""),
                "tool_call_id": msg.get("tool_call_id")
            })
        elif role in ("system", "user"):
            openai_messages.append({
                "role": role,
                "content": msg.get("content", "")
            })
            
    openai_messages.append({"role": "user", "content": message})
    
    # Stream from LLM server (NO tools)
    server_url = service_manager.llm_manager.server_manager.get_server_url()
    payload = {
        "model": service_manager.llm_manager.current_model_name or "default",
        "messages": openai_messages,
        "temperature": sampler_params["temperature"],
        "top_p": sampler_params["top_p"],
        "max_tokens": sampler_params["max_tokens"],
        "stream": True
    }
    
    import httpx
    accumulated_content = []
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{server_url}/v1/chat/completions",
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                            delta = chunk_data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                accumulated_content.append(content)
                                yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
                    except json.JSONDecodeError:
                        continue
    
    # Store assistant message
    full_content = ''.join(accumulated_content)
    assistant_msg = {
        "role": "assistant",
        "content": full_content,
        "timestamp": time.time()
    }
    service_manager.chat_manager.conversations[conversation_id].append(assistant_msg)
    
    # Save to memory store
    if service_manager.chat_manager.memory_store:
        conv_name = service_manager.chat_manager._conversation_names.get(conversation_id)
        await service_manager.chat_manager.memory_store.store_conversation(
            conversation_id=conversation_id,
                    messages=[user_msg, assistant_msg],
                    name=conv_name
                )
            
    yield f"data: {json.dumps({'content': '', 'done': True, 'conversation_id': conversation_id, 'tool_calls': None})}\n\n"


@router.post("/api/chat/regenerate")
async def regenerate_last_response(request: Request):
    """Regenerate the last assistant response in a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(
            status_code=503,
            detail="Chat service not initialized"
        )
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=400,
            detail="LLM manager not initialized"
        )
    
    # Check if model is loaded
    if not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded. Please load a model first."
        )
    
    # Check server health (but don't fail if it's just slow - try the request anyway)
    # The actual request will fail if the server is truly down
    try:
        health_ok = await service_manager.llm_manager.server_manager.health_check()
        if not health_ok:
            logger.warning("Health check failed, but proceeding with regenerate request")
    except Exception as e:
        logger.warning(f"Health check error (proceeding anyway): {e}")
    
    body = await request.json()
    conversation_id = body.get("conversation_id")
    
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    
    try:
        # Initialize chat manager to ensure conversations are loaded
        await service_manager.chat_manager._initialize()
        
        # Get conversation from chat manager (includes cache)
        conversation = await service_manager.chat_manager.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Find the last user message and remove all assistant messages after it
        last_user_index = -1
        for i in range(len(conversation) - 1, -1, -1):
            if conversation[i].get("role") == "user":
                last_user_index = i
                break
        
        if last_user_index == -1:
            raise HTTPException(status_code=400, detail="No user message found to regenerate from")
        
        # Truncate conversation to only include messages up to (but NOT including) the last user message
        # This removes all assistant messages after the last user message, and the last user message itself
        # (since send_message will add it again)
        truncated_conversation = conversation[:last_user_index]
        
        # Delete messages from vector store that are being removed (everything after last_user_index)
        if service_manager.memory_store and service_manager.memory_store.vector_store:
            # Get current user profile ID for vector store
            user_profile_id = await service_manager.memory_store._get_current_user_profile_id()
            await service_manager.memory_store.vector_store.delete_messages_after_index(
                conversation_id=conversation_id,
                message_index=last_user_index,
                user_profile_id=user_profile_id
            )
        
        # Update the conversation in the chat manager's cache BEFORE calling send_message
        # This ensures send_message uses the truncated history (without the previous assistant message)
        service_manager.chat_manager.conversations[conversation_id] = truncated_conversation
        
        # Save the truncated conversation to persistent storage
        conv_name = service_manager.chat_manager._conversation_names.get(conversation_id)
        await service_manager.memory_store.store_conversation(
            conversation_id=conversation_id,
            messages=truncated_conversation,
            name=conv_name
        )
        
        # Get the user message to regenerate from (from the original conversation before truncation)
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
            context_length=settings.llm_context_size,
            temperature=sampler_params.get("temperature"),
            top_p=sampler_params.get("top_p"),
            top_k=sampler_params.get("top_k"),
            repeat_penalty=sampler_params.get("repeat_penalty"),
            retrieved_context=result.get("context_used", [])
        )
        
        # Get logs if available
        log_store = get_request_log_store()
        logs = log_store.get_logs() if log_store else None
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            context_used=result.get("context_used", []),
            tool_calls=result.get("tool_calls"),
            metadata=metadata,
            logs=logs
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating response: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to regenerate: {str(e)}") from e
