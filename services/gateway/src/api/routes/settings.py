"""Settings and configuration routes."""
import time
import asyncio
import logging
from typing import Dict, Optional, Any
from fastapi import APIRouter, HTTPException, Request

from ..schemas import AISettings, AISettingsResponse, ModelLoadOptions, CharacterCard, UserProfile
from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])

# Cache for settings endpoint (5 second TTL)
_settings_cache: Optional[Dict[str, Any]] = None
_settings_cache_time: float = 0
_SETTINGS_CACHE_TTL = 5.0


@router.get("/api/settings", response_model=AISettingsResponse)
async def get_settings():
    """Get current AI settings."""
    global _settings_cache, _settings_cache_time
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    current_time = time.time()
    if _settings_cache and (current_time - _settings_cache_time) < _SETTINGS_CACHE_TTL:
        logger.debug("Returning cached settings")
        cache_data = _settings_cache
        return AISettingsResponse(
            settings=cache_data["settings"],
            model_loaded=cache_data["model_loaded"],
            current_model=cache_data["current_model"],
            supports_tool_calling=cache_data["supports_tool_calling"]
        )
    
    settings_dict = service_manager.llm_manager.get_settings()
    
    system_prompt_data, character_card, user_profile = await asyncio.gather(
        service_manager.memory_store.get_system_prompt(),
        service_manager.memory_store.get_character_card(),
        service_manager.memory_store.get_user_profile(),
        return_exceptions=True
    )
    
    if isinstance(system_prompt_data, Exception):
        logger.warning(f"Error loading system prompt: {system_prompt_data}")
        system_prompt_data = None
    if isinstance(character_card, Exception):
        logger.warning(f"Error loading character card: {character_card}")
        character_card = None
    if isinstance(user_profile, Exception):
        logger.warning(f"Error loading user profile: {user_profile}")
        user_profile = None
    
    system_prompt = system_prompt_data.get("content", "") if system_prompt_data else service_manager.llm_manager.get_system_prompt()
    
    model_loaded = service_manager.llm_manager.is_model_loaded()
    current_model = service_manager.llm_manager.get_current_model_path()
    
    default_load_options = service_manager.llm_manager.get_default_load_options()
    
    supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
    
    llm_endpoint_mode = await service_manager.memory_store.settings_store.get_setting("llm_endpoint_mode", "local")
    llm_remote_url = await service_manager.memory_store.settings_store.get_setting("llm_remote_url", None)
    llm_remote_api_key = await service_manager.memory_store.settings_store.get_setting("llm_remote_api_key", None)
    llm_remote_model = await service_manager.memory_store.settings_store.get_setting("llm_remote_model", None)
    
    response = AISettingsResponse(
        settings=AISettings(
            temperature=settings_dict["temperature"],
            top_p=settings_dict["top_p"],
            top_k=settings_dict["top_k"],
            repeat_penalty=settings_dict["repeat_penalty"],
            system_prompt=system_prompt,
            character_card=CharacterCard(**character_card) if character_card else None,
            user_profile=UserProfile(**user_profile) if user_profile else None,
            default_load_options=ModelLoadOptions(**default_load_options) if default_load_options else None,
            llm_endpoint_mode=llm_endpoint_mode,
            llm_remote_url=llm_remote_url,
            llm_remote_api_key=llm_remote_api_key,
            llm_remote_model=llm_remote_model
        ),
        model_loaded=model_loaded,
        current_model=current_model,
        supports_tool_calling=supports_tool_calling
    )
    
    _settings_cache = {
        "settings": response.settings,
        "model_loaded": response.model_loaded,
        "current_model": response.current_model,
        "supports_tool_calling": response.supports_tool_calling
    }
    _settings_cache_time = current_time
    
    return response


@router.put("/api/settings", response_model=AISettingsResponse)
async def update_settings(settings_update: AISettings):
    """Update AI settings."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
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
    
    if settings_update.system_prompt is not None:
        service_manager.llm_manager.update_system_prompt(settings_update.system_prompt)
        await service_manager.memory_store.set_system_prompt(
            content=settings_update.system_prompt,
            is_default=True
        )
    
    if settings_update.character_card is not None:
        character_card_dict = {
            "name": settings_update.character_card.name,
            "personality": settings_update.character_card.personality,
            "background": settings_update.character_card.background,
            "instructions": settings_update.character_card.instructions
        }
        service_manager.llm_manager.update_character_card(character_card_dict)
        await service_manager.memory_store.set_character_card(character_card_dict)
    
    if settings_update.user_profile is not None:
        user_profile_dict = {
            "name": settings_update.user_profile.name,
            "about": settings_update.user_profile.about,
            "preferences": settings_update.user_profile.preferences
        }
        service_manager.llm_manager.update_user_profile(user_profile_dict)
        await service_manager.memory_store.set_user_profile(user_profile_dict)
    
    if settings_dict:
        await service_manager.memory_store.update_sampler_settings(settings_dict)
    
    if settings_update.llm_endpoint_mode is not None:
        await service_manager.memory_store.settings_store.set_setting("llm_endpoint_mode", settings_update.llm_endpoint_mode)
    if settings_update.llm_remote_url is not None:
        await service_manager.memory_store.settings_store.set_setting("llm_remote_url", settings_update.llm_remote_url)
    if settings_update.llm_remote_api_key is not None:
        await service_manager.memory_store.settings_store.set_setting("llm_remote_api_key", settings_update.llm_remote_api_key, encrypted=True)
    if settings_update.llm_remote_model is not None:
        await service_manager.memory_store.settings_store.set_setting("llm_remote_model", settings_update.llm_remote_model)
    
    return await get_settings()


# System Prompt Management
@router.get("/api/settings/system-prompt")
async def get_system_prompt(prompt_id: Optional[str] = None):
    """Get system prompt from Memory service."""
    if not service_manager.memory_store:
        raise HTTPException(
            status_code=503,
            detail="Memory service not available"
        )
    
    try:
        prompt = await service_manager.memory_store.get_system_prompt(prompt_id=prompt_id)
        if prompt is None:
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
