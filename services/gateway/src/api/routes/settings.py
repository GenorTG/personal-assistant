"""Settings and configuration routes."""
# Standard library
import asyncio
import logging
import time
from typing import Dict, Optional, Any

# Third-party
from fastapi import APIRouter, HTTPException, Request

# Local
from ..schemas import AISettings, AISettingsResponse, ModelLoadOptions, CharacterCard, UserProfile
from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])

# Cache for settings endpoint (5 second TTL)
_settings_cache: Optional[Dict[str, Any]] = None
_settings_cache_time: float = 0
_SETTINGS_CACHE_TTL = 5.0

def invalidate_settings_cache():
    """Invalidate the settings cache (called when model is loaded/unloaded)."""
    global _settings_cache, _settings_cache_time
    _settings_cache = None
    _settings_cache_time = 0
    logger.debug("Settings cache invalidated")


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
    # Get current model - prefer model name for display, fallback to path
    current_model_path = service_manager.llm_manager.get_current_model_path()
    current_model_name = getattr(service_manager.llm_manager, 'current_model_name', None)
    current_model = current_model_name if current_model_name else current_model_path
    
    default_load_options = service_manager.llm_manager.get_default_load_options()
    
    supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
    
    llm_endpoint_mode = await service_manager.memory_store.settings_store.get_setting("llm_endpoint_mode", "local")
    llm_remote_url = await service_manager.memory_store.settings_store.get_setting("llm_remote_url", None)
    llm_remote_api_key = await service_manager.memory_store.settings_store.get_setting("llm_remote_api_key", None)
    llm_remote_model = await service_manager.memory_store.settings_store.get_setting("llm_remote_model", None)
    streaming_mode = await service_manager.memory_store.settings_store.get_setting("streaming_mode", "non-streaming")
    
    response = AISettingsResponse(
        settings=AISettings(
            temperature=settings_dict.get("temperature", 0.7),
            top_p=settings_dict.get("top_p", 0.9),
            top_k=settings_dict.get("top_k", 40),
            repeat_penalty=settings_dict.get("repeat_penalty", 1.1),
            stop=settings_dict.get("stop", ["\n*{{user}}", "\n{{user}}", "{{user}}:", "User:"]),
            system_prompt=system_prompt,
            character_card=CharacterCard(**character_card) if character_card else None,
            user_profile=UserProfile(**user_profile) if user_profile else None,
            default_load_options=ModelLoadOptions(**default_load_options) if default_load_options else None,
            llm_endpoint_mode=llm_endpoint_mode,
            llm_remote_url=llm_remote_url,
            llm_remote_api_key=llm_remote_api_key,
            llm_remote_model=llm_remote_model,
            streaming_mode=streaming_mode
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
    """Update AI settings and broadcast via WebSocket."""
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
    if settings_update.stop is not None:
        settings_dict["stop"] = settings_update.stop
    
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
    if settings_update.streaming_mode is not None:
        await service_manager.memory_store.settings_store.set_setting("streaming_mode", settings_update.streaming_mode)
    
    # Broadcast settings update via WebSocket
    try:
        from ...services.websocket_manager import get_websocket_manager
        ws_manager = get_websocket_manager()
        settings_response = await get_settings()
        # Convert Pydantic model to dict for broadcasting
        if hasattr(settings_response, 'dict'):
            await ws_manager.broadcast_settings_update(settings_response.dict())
        elif hasattr(settings_response, 'model_dump'):
            await ws_manager.broadcast_settings_update(settings_response.model_dump())
        else:
            await ws_manager.broadcast_settings_update(dict(settings_response))
    except Exception as e:
        logger.debug(f"Failed to broadcast settings update: {e}")
    
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


# Character Card Management Endpoints
@router.get("/api/character-cards")
async def list_character_cards():
    """List all character cards."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        cards = await service_manager.memory_store.character_card_store.list_character_cards()
        return {"cards": cards}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list character cards: {str(e)}") from e


@router.get("/api/character-cards/{card_id}")
async def get_character_card(card_id: str):
    """Get a specific character card by ID."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        card = await service_manager.memory_store.character_card_store.get_character_card(card_id)
        if not card:
            raise HTTPException(status_code=404, detail="Character card not found")
        return card
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get character card: {str(e)}") from e


@router.post("/api/character-cards")
async def create_character_card(request: Request):
    """Create a new character card."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        body = await request.json()
        card_id = await service_manager.memory_store.character_card_store.create_character_card(body)
        card = await service_manager.memory_store.character_card_store.get_character_card(card_id)
        
        # Update LLM manager if this becomes the current card
        current_id = await service_manager.memory_store.character_card_store.get_current_character_card_id()
        if current_id == card_id and card:
            service_manager.llm_manager.update_character_card(card)
        
        return {"id": card_id, **card}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create character card: {str(e)}") from e


@router.put("/api/character-cards/{card_id}")
async def update_character_card(card_id: str, request: Request):
    """Update an existing character card."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        body = await request.json()
        success = await service_manager.memory_store.character_card_store.update_character_card(card_id, body)
        if not success:
            raise HTTPException(status_code=404, detail="Character card not found")
        
        # Update LLM manager if this is the current card
        current_id = await service_manager.memory_store.character_card_store.get_current_character_card_id()
        if current_id == card_id:
            card = await service_manager.memory_store.character_card_store.get_character_card(card_id)
            if card:
                service_manager.llm_manager.update_character_card(card)
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update character card: {str(e)}") from e


@router.delete("/api/character-cards/{card_id}")
async def delete_character_card(card_id: str):
    """Delete a character card."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        success = await service_manager.memory_store.character_card_store.delete_character_card(card_id)
        if not success:
            raise HTTPException(status_code=404, detail="Character card not found")
        
        # Clear LLM manager if this was the current card
        current_id = await service_manager.memory_store.character_card_store.get_current_character_card_id()
        if current_id == card_id:
            service_manager.llm_manager.update_character_card(None)
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete character card: {str(e)}") from e


@router.post("/api/character-cards/{card_id}/set-current")
async def set_current_character_card(card_id: str):
    """Set a character card as the current active card."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        success = await service_manager.memory_store.character_card_store.set_current_character_card(card_id)
        if not success:
            raise HTTPException(status_code=404, detail="Character card not found")
        
        # Update LLM manager with the new current card
        card = await service_manager.memory_store.character_card_store.get_character_card(card_id)
        if card:
            service_manager.llm_manager.update_character_card(card)
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set current character card: {str(e)}") from e


# User Profile Management Endpoints
@router.get("/api/user-profiles")
async def list_user_profiles():
    """List all user profiles."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        profiles = await service_manager.memory_store.user_profile_store.list_user_profiles()
        return {"profiles": profiles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list user profiles: {str(e)}") from e


@router.get("/api/user-profiles/{profile_id}")
async def get_user_profile(profile_id: str):
    """Get a specific user profile by ID."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        profile = await service_manager.memory_store.user_profile_store.get_user_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user profile: {str(e)}") from e


@router.post("/api/user-profiles")
async def create_user_profile(request: Request):
    """Create a new user profile."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        body = await request.json()
        profile_id = await service_manager.memory_store.user_profile_store.create_user_profile(body)
        profile = await service_manager.memory_store.user_profile_store.get_user_profile(profile_id)
        
        # Update LLM manager if this becomes the current profile
        current_id = await service_manager.memory_store.user_profile_store.get_current_user_profile_id()
        if current_id == profile_id and profile:
            service_manager.llm_manager.update_user_profile(profile)
        
        return {"id": profile_id, **profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user profile: {str(e)}") from e


@router.put("/api/user-profiles/{profile_id}")
async def update_user_profile(profile_id: str, request: Request):
    """Update an existing user profile."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        body = await request.json()
        success = await service_manager.memory_store.user_profile_store.update_user_profile(profile_id, body)
        if not success:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        # Update LLM manager if this is the current profile
        current_id = await service_manager.memory_store.user_profile_store.get_current_user_profile_id()
        if current_id == profile_id:
            profile = await service_manager.memory_store.user_profile_store.get_user_profile(profile_id)
            if profile:
                service_manager.llm_manager.update_user_profile(profile)
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user profile: {str(e)}") from e


@router.delete("/api/user-profiles/{profile_id}")
async def delete_user_profile(profile_id: str):
    """Delete a user profile."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        success = await service_manager.memory_store.user_profile_store.delete_user_profile(profile_id)
        if not success:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        # Clear LLM manager if this was the current profile
        current_id = await service_manager.memory_store.user_profile_store.get_current_user_profile_id()
        if current_id == profile_id:
            service_manager.llm_manager.update_user_profile(None)
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user profile: {str(e)}") from e


@router.post("/api/user-profiles/{profile_id}/set-current")
async def set_current_user_profile(profile_id: str):
    """Set a user profile as the current active profile."""
    if not service_manager.memory_store:
        raise HTTPException(status_code=503, detail="Memory service not available")
    
    try:
        success = await service_manager.memory_store.user_profile_store.set_current_user_profile(profile_id)
        if not success:
            raise HTTPException(status_code=404, detail="User profile not found")
        
        # Update LLM manager with the new current profile
        profile = await service_manager.memory_store.user_profile_store.get_user_profile(profile_id)
        if profile:
            service_manager.llm_manager.update_user_profile(profile)
        
        # Update vector store to use the new user's collection
        # The vector store will automatically use the new user_profile_id on next access
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set current user profile: {str(e)}") from e
