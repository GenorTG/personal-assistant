"""Vector memory settings management."""

import aiofiles
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


async def should_save_vector_memory(
    conversation_id: str,
    conversations_dir: Path,
    get_setting_func
) -> bool:
    """Check if vector memory saving is enabled for a conversation.
    
    Checks per-conversation settings first (from file store), then falls back to global settings.
    
    Args:
        conversation_id: Conversation ID to check
        conversations_dir: Directory containing conversation files
        get_setting_func: Async function to get settings
        
    Returns:
        True if saving is enabled, False otherwise
    """
    # Check per-conversation settings from file store
    conv_file = conversations_dir / f"{conversation_id}.json"
    if conv_file.exists():
        try:
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                vector_memory = data.get("vector_memory", {})
                if vector_memory.get("custom", False):
                    save_enabled = vector_memory.get("save_enabled")
                    if save_enabled is not None:
                        return save_enabled
        except Exception:
            pass  # Fall through to global settings
    
    # Fall back to global settings
    global_enabled = await get_setting_func("vector_memory_enabled", "true")
    if global_enabled != "true":
        return False
    
    global_save = await get_setting_func("vector_memory_save_enabled", "true")
    return global_save == "true"


async def should_read_vector_memory(
    conversation_id: Optional[str],
    conversations_dir: Path,
    get_setting_func
) -> bool:
    """Check if vector memory reading is enabled for a conversation.
    
    Checks per-conversation settings first (from file store), then falls back to global settings.
    
    Args:
        conversation_id: Conversation ID to check (None for global check)
        conversations_dir: Directory containing conversation files
        get_setting_func: Async function to get settings
        
    Returns:
        True if reading is enabled, False otherwise
    """
    if conversation_id:
        # Check per-conversation settings from file store
        conv_file = conversations_dir / f"{conversation_id}.json"
        if conv_file.exists():
            try:
                async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    vector_memory = data.get("vector_memory", {})
                    if vector_memory.get("custom", False):
                        read_enabled = vector_memory.get("read_enabled")
                        if read_enabled is not None:
                            return read_enabled
            except Exception:
                pass  # Fall through to global settings
    
    # Fall back to global settings
    global_enabled = await get_setting_func("vector_memory_enabled", "true")
    if global_enabled != "true":
        return False
    
    global_read = await get_setting_func("vector_memory_read_enabled", "true")
    return global_read == "true"


async def get_vector_memory_settings(get_setting_func) -> Dict[str, Any]:
    """Get global vector memory settings.
    
    Args:
        get_setting_func: Async function to get settings
        
    Returns:
        Dictionary with vector memory settings
    """
    return {
        "vector_memory_enabled": await get_setting_func("vector_memory_enabled", "true") == "true",
        "vector_memory_save_enabled": await get_setting_func("vector_memory_save_enabled", "true") == "true",
        "vector_memory_read_enabled": await get_setting_func("vector_memory_read_enabled", "true") == "true",
        "vector_memory_apply_to_all": await get_setting_func("vector_memory_apply_to_all", "false") == "true"
    }


async def set_vector_memory_settings(
    settings: Dict[str, Any],
    set_setting_func,
    file_store,
    apply_to_all_func
) -> None:
    """Set global vector memory settings.
    
    Args:
        settings: Dictionary with settings to apply
        set_setting_func: Async function to set settings
        file_store: File store instance for listing conversations
        apply_to_all_func: Async function to apply settings to all conversations
    """
    for key, value in settings.items():
        await set_setting_func(key, "true" if value else "false")
    
    # If apply_to_all is True, update all conversations
    if settings.get("vector_memory_apply_to_all", False):
        await apply_to_all_func(settings)


async def apply_global_settings_to_all_conversations(
    settings: Dict[str, Any],
    conversations_dir: Path,
    list_conversations_func
) -> int:
    """Apply global vector memory settings to all conversations (update file store).
    
    Args:
        settings: Dictionary with settings to apply
        conversations_dir: Directory containing conversation files
        list_conversations_func: Async function to list conversations
        
    Returns:
        Number of conversations updated
    """
    conversations = await list_conversations_func()
    updated_count = 0
    
    for conv_data in conversations:
        conv_id = conv_data["conversation_id"]
        conv_file = conversations_dir / f"{conv_id}.json"
        
        if not conv_file.exists():
            continue
        
        try:
            # Read conversation file
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            # Update vector memory settings
            if "vector_memory" not in data:
                data["vector_memory"] = {}
            
            data["vector_memory"]["custom"] = False  # Reset to use global
            data["vector_memory"]["save_enabled"] = None
            data["vector_memory"]["read_enabled"] = None
            data["updated_at"] = datetime.utcnow().isoformat()
            
            # Write back
            async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, default=str))
            
            updated_count += 1
        except Exception as e:
            logger.error(f"Error updating conversation {conv_id}: {e}")
    
    logger.info(f"Applied global vector memory settings to {updated_count} conversations")
    return updated_count


async def get_conversation_vector_memory_settings(
    conversation_id: str,
    conversations_dir: Path
) -> Dict[str, Any]:
    """Get per-conversation vector memory settings from file store.
    
    Args:
        conversation_id: Conversation ID
        conversations_dir: Directory containing conversation files
        
    Returns:
        Dictionary with vector memory settings
    """
    conv_file = conversations_dir / f"{conversation_id}.json"
    
    if not conv_file.exists():
        return {
            "custom": False,
            "save_enabled": None,
            "read_enabled": None
        }
    
    try:
        async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            vector_memory = data.get("vector_memory", {})
            return {
                "custom": vector_memory.get("custom", False),
                "save_enabled": vector_memory.get("save_enabled"),
                "read_enabled": vector_memory.get("read_enabled")
            }
    except Exception:
        return {
            "custom": False,
            "save_enabled": None,
            "read_enabled": None
        }


async def set_conversation_vector_memory_settings(
    conversation_id: str,
    settings: Dict[str, Any],
    conversations_dir: Path
) -> None:
    """Set per-conversation vector memory settings in file store.
    
    Args:
        conversation_id: Conversation ID
        settings: Dictionary with settings to apply
        conversations_dir: Directory containing conversation files
        
    Raises:
        ValueError: If conversation not found
    """
    conv_file = conversations_dir / f"{conversation_id}.json"
    
    if not conv_file.exists():
        raise ValueError(f"Conversation {conversation_id} not found")
    
    custom = settings.get("custom", False)
    save_enabled = settings.get("save_enabled", True) if custom else None
    read_enabled = settings.get("read_enabled", True) if custom else None
    
    try:
        # Read conversation file
        async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
        
        # Update vector memory settings
        if "vector_memory" not in data:
            data["vector_memory"] = {}
        
        data["vector_memory"]["custom"] = custom
        data["vector_memory"]["save_enabled"] = save_enabled
        data["vector_memory"]["read_enabled"] = read_enabled
        data["updated_at"] = datetime.utcnow().isoformat()
        
        # Write back
        async with aiofiles.open(conv_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, default=str))
    except Exception as e:
        logger.error(f"Error setting vector memory settings for {conversation_id}: {e}")
        raise

