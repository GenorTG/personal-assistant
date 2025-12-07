"""OpenAI-compatible proxy routes for LLM service."""
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Header, Response, BackgroundTasks
from fastapi.responses import StreamingResponse
import httpx

from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])


async def save_messages_to_vector_store(
    conversation_id: str,
    user_messages: List[Dict[str, Any]],
    assistant_content: str
):
    """Helper function to save messages to vector store."""
    if not service_manager.memory_store:
        return
    
    try:
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


@router.get("/v1/models")
async def proxy_list_models():
    """Proxy GET /v1/models to LLM service."""
    try:
        from ...services.llm.service_manager import LLMServiceManager
        service_mgr = LLMServiceManager()
        service_url = service_mgr.get_service_url()
        
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
        from ...services.llm.service_manager import LLMServiceManager
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
        from ...services.llm.service_manager import LLMServiceManager
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


@router.post("/v1/chat/completions")
async def proxy_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    x_conversation_id: Optional[str] = Header(None, alias="X-Conversation-ID")
):
    """Proxy POST /v1/chat/completions to llama-cpp-python server with vector store integration."""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        stream = body.get("stream", False)
        
        conversation_id = x_conversation_id or body.get("conversation_id")
        
        if service_manager.llm_manager and not service_manager.llm_manager.supports_tool_calling:
            if "tools" in body and body.get("tools"):
                logger.debug("Removing tools from request - model does not support tool calling")
                body = {k: v for k, v in body.items() if k != "tools"}
        
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
            from ...services.llm.service_manager import LLMServiceManager
            service_mgr = LLMServiceManager()
            service_url = service_mgr.get_service_url()
            
            if not await service_mgr.is_service_running():
                raise HTTPException(
                    status_code=503,
                    detail="LLM service not running. Please start it via the launcher."
                )
            
            remote_headers = {}
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            if stream:
                stream_headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length", "authorization", "x-api-key"]}
                stream_headers.update(remote_headers)
                
                if llm_endpoint_mode == "remote":
                    if service_url.endswith('/v1'):
                        full_url = f"{service_url}/chat/completions"
                    elif '/v1' in service_url:
                        full_url = f"{service_url}/chat/completions"
                    else:
                        full_url = f"{service_url}/v1/chat/completions"
                else:
                    full_url = f"{service_url}/v1/chat/completions"
                
                async with client.stream(
                    "POST",
                    full_url,
                    json={**body, "messages": messages},
                    headers=stream_headers
                ) as response:
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
                                                except:
                                                    pass
                            except:
                                pass
                            yield chunk
                        
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
                request_headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length", "authorization", "x-api-key"]}
                request_headers.update(remote_headers)
                
                if llm_endpoint_mode == "remote":
                    if service_url.endswith('/v1'):
                        full_url = f"{service_url}/chat/completions"
                    elif '/v1' in service_url:
                        full_url = f"{service_url}/chat/completions"
                    else:
                        full_url = f"{service_url}/v1/chat/completions"
                else:
                    full_url = f"{service_url}/v1/chat/completions"
                
                resp = await client.post(
                    full_url,
                    json={**body, "messages": messages},
                    headers=request_headers
                )
                
                resp_data = resp.json()
                
                if "choices" in resp_data and len(resp_data["choices"]) > 0:
                    message_obj = resp_data["choices"][0].get("message", {})
                    content = message_obj.get("content", "")
                    
                    if not message_obj.get("tool_calls") and content:
                        from ...services.tools.parser import ToolCallParser
                        parser = ToolCallParser()
                        
                        parsed_tool_calls = parser.parse(content)
                        
                        if parsed_tool_calls:
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
                            
                            cleaned_content = content
                            for tc in parsed_tool_calls:
                                tool_name = tc.get("name", "")
                                import re
                                start_idx = cleaned_content.find(f'{{"name": "{tool_name}"')
                                if start_idx == -1:
                                    start_idx = cleaned_content.find(f'{{ "name": "{tool_name}"')
                                if start_idx != -1:
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
                                        before = cleaned_content[:start_idx].strip()
                                        after = cleaned_content[end_idx:].strip()
                                        parts = []
                                        if before:
                                            parts.append(before)
                                        if after:
                                            parts.append(after)
                                        cleaned_content = ' '.join(parts)
                                        cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
                            
                            message_obj["tool_calls"] = tool_calls
                            final_content = cleaned_content.strip() if cleaned_content.strip() else None
                            message_obj["content"] = final_content
                            resp_data["choices"][0]["message"] = message_obj
                            
                            if tool_calls:
                                resp_data["choices"][0]["finish_reason"] = "tool_calls"
                
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
        from ...services.llm.service_manager import LLMServiceManager
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
