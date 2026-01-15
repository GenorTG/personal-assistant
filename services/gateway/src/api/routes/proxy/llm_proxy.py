"""LLM service proxy routes."""
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, Header, Response, BackgroundTasks
import httpx

from ....services.service_manager import service_manager
from .streaming import create_streaming_response, save_messages_to_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy", "llm"])


async def _handle_direct_llm_call(body: Dict[str, Any], messages: List[Dict[str, Any]], stream: bool, conversation_id: Optional[str], background_tasks):
    """Handle LLM call using HTTP requests to the OpenAI-compatible server."""
    try:
        # Get LLM manager
        llm_manager = service_manager.llm_manager

        # Prepare tools if present
        tools = body.get("tools")
        if tools and not llm_manager.supports_tool_calling:
            # Remove tools if model doesn't support tool calling
            tools = None

        # Get server URL
        server_url = llm_manager.server_manager.get_server_url()
        
        # Build request payload
        # For chatml-function-calling, use simple model name like "test" (as per working manual test)
        model_name = "test" if (hasattr(llm_manager, 'current_chat_format') and llm_manager.current_chat_format == "chatml-function-calling") else (llm_manager.current_model_name or "default")
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": body.get("temperature", 0.7),
            "top_p": body.get("top_p", 0.9),
            "max_tokens": body.get("max_tokens", 1024),
            "frequency_penalty": body.get("frequency_penalty", 0.0),
            "stream": stream
        }
        
        if tools:
            payload["tools"] = tools
            # Add tool_choice for chatml-function-calling format
            # NOTE: tool_choice is NOT supported with streaming in llama-cpp-python
            # Only add tool_choice for non-streaming requests
            if not stream:
                if hasattr(llm_manager, 'current_chat_format') and llm_manager.current_chat_format == "chatml-function-calling":
                    # Use "auto" to let model choose, or can specify specific tool
                    if "tool_choice" not in body:
                        payload["tool_choice"] = "auto"
                    else:
                        payload["tool_choice"] = body.get("tool_choice")

        # Make HTTP request to OpenAI-compatible server
        async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced from 300s to 30s
            if stream:
                # Handle streaming response
                async with client.stream(
                    "POST",
                    f"{server_url}/v1/chat/completions",
                    json=payload
                ) as response:
                    response.raise_for_status()
                    return await create_streaming_response(
                        response,
                        conversation_id,
                        messages,
                        background_tasks
                    )
            else:
                # Handle non-streaming response
                response = await client.post(
                    f"{server_url}/v1/chat/completions",
                    json=payload
                )
                response.raise_for_status()
                resp_data = response.json()

            # Handle tool call parsing for models that don't support native tool calling
            if "choices" in resp_data and len(resp_data["choices"]) > 0:
                message_obj = resp_data["choices"][0].get("message", {})
                content = message_obj.get("content", "")

                # Tool calls should come in OpenAI format from the LLM
                # No fallback parsing - keep it simple

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

            return Response(
                content=json.dumps(resp_data).encode('utf-8'),
                status_code=200,
                media_type="application/json"
            )

    except Exception as e:
        logger.error(f"Error in direct LLM call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM call error: {str(e)}") from e


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    x_conversation_id: Optional[str] = Header(None, alias="X-Conversation-ID")
):
    """Proxy POST /v1/chat/completions to OpenAI-compatible server with vector store integration."""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        stream = body.get("stream", False)
        
        conversation_id = x_conversation_id or body.get("conversation_id")
        
        # Remove tools if model doesn't support tool calling
        if service_manager.llm_manager and not service_manager.llm_manager.supports_tool_calling:
            if "tools" in body and body.get("tools"):
                logger.debug("Removing tools from request - model does not support tool calling")
                body = {k: v for k, v in body.items() if k != "tools"}
        
        # Add context and system prompt if conversation_id is provided
        if conversation_id and service_manager.memory_store:
            try:
                system_prompt_data = await service_manager.memory_store.get_system_prompt()
                system_prompt = system_prompt_data.get("content", "") if system_prompt_data else ""
                
                last_user_message = None
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        last_user_message = msg.get("content", "")
                        break
                
                context_str = ""
                if last_user_message:
                    context = await service_manager.memory_store.retrieve_context(
                        query=last_user_message,
                        exclude_conversation_id=conversation_id
                    )
                    
                    if context and context.get("retrieved_messages"):
                        context_str = "\n\nRelevant context from past conversations:\n" + "\n".join(
                            f"- {msg}" for msg in context["retrieved_messages"][:5]
                        )
                
                combined_system_content = system_prompt
                if context_str:
                    combined_system_content += context_str
                
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
        
        # Determine LLM endpoint (local or remote)
        llm_endpoint_mode = await service_manager.memory_store.settings_store.get_setting("llm_endpoint_mode", "local")
        
        if llm_endpoint_mode == "remote":
            remote_url = await service_manager.memory_store.settings_store.get_setting("llm_remote_url", None)
            remote_api_key = await service_manager.memory_store.settings_store.get_setting("llm_remote_api_key", None)
            remote_model = await service_manager.memory_store.settings_store.get_setting("llm_remote_model", None)
            
            if not remote_url:
                raise HTTPException(
                    status_code=400,
                    detail="Remote LLM endpoint URL is not configured. Please configure it in settings."
                )
            
            service_url = remote_url.rstrip('/')
            
            remote_headers = {
                "Content-Type": "application/json",
            }
            if remote_api_key:
                remote_headers["Authorization"] = f"Bearer {remote_api_key}"
                remote_headers["X-API-Key"] = remote_api_key
            
            if remote_model:
                body["model"] = remote_model
        else:
            # Use direct LLMManager client instead of HTTP service
            if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
                raise HTTPException(
                    status_code=503,
                    detail="LLM service not running. Please load a model first."
                )
            
            # Use direct client call instead of HTTP proxy
            return await _handle_direct_llm_call(body, messages, stream, conversation_id, background_tasks)
        
        # Build full URL
        if llm_endpoint_mode == "remote":
            if service_url.endswith('/v1'):
                full_url = f"{service_url}/chat/completions"
            elif '/v1' in service_url:
                full_url = f"{service_url}/chat/completions"
            else:
                full_url = f"{service_url}/v1/chat/completions"
        else:
            full_url = f"{service_url}/v1/chat/completions"
        
        async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced from 300s to 30s
            if stream:
                # Handle streaming response
                stream_headers = {k: v for k, v in request.headers.items() 
                                if k.lower() not in ["host", "content-length", "authorization", "x-api-key"]}
                stream_headers.update(remote_headers)
                
                async with client.stream(
                    "POST",
                    full_url,
                    json={**body, "messages": messages},
                    headers=stream_headers
                ) as response:
                    return await create_streaming_response(
                        response,
                        conversation_id,
                        messages,
                        background_tasks
                    )
            else:
                # Handle non-streaming response
                request_headers = {k: v for k, v in request.headers.items() 
                                if k.lower() not in ["host", "content-length", "authorization", "x-api-key"]}
                request_headers.update(remote_headers)
                
                resp = await client.post(
                    full_url,
                    json={**body, "messages": messages},
                    headers=request_headers
                )
                
                resp_data = resp.json()
                
                # Handle tool call parsing for models that don't support native tool calling
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    message_obj = resp_data["choices"][0].get("message", {})
                    content = message_obj.get("content", "")
                    
                    # Tool calls should come in OpenAI format from the LLM
                    # No fallback parsing - keep it simple
                
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
                
                # Return response
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
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}") from e


@router.post("/v1/completions")
async def proxy_completions(request: Request):
    """Proxy POST /v1/completions to LLM service."""
    try:
        # Use direct LLMManager client instead of HTTP service
        if not service_manager.llm_manager or not service_manager.llm_manager.is_model_loaded():
            raise HTTPException(
                status_code=503,
                detail="LLM service not running. Please load a model first."
            )
        
        body = await request.json()
        llm_manager = service_manager.llm_manager
        server_url = llm_manager.server_manager.get_server_url()

        # Build request payload for completions endpoint
        payload = {
            "model": llm_manager.current_model_name or "default",
            "prompt": body.get("prompt", ""),
            "temperature": body.get("temperature", 0.7),
            "top_p": body.get("top_p", 0.9),
            "max_tokens": body.get("max_tokens", 1024),
            "frequency_penalty": body.get("frequency_penalty", 0.0),
            "stream": body.get("stream", False)
        }

        # Make HTTP request to OpenAI-compatible server
        async with httpx.AsyncClient(timeout=30.0) as client:  # Reduced from 300s to 30s
            response = await client.post(
                f"{server_url}/v1/completions",
                json=payload
            )
            response.raise_for_status()
            resp_data = response.json()

        return Response(
            content=json.dumps(resp_data).encode("utf-8"),
            status_code=200,
            media_type="application/json",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying /v1/completions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}") from e


