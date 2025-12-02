"""File-based storage for app-level settings: system prompts, character cards, user profiles, sampler settings."""
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import aiofiles
import logging
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class FileSystemPromptStore:
    """File-based storage for system prompts.
    
    Structure:
    - system_prompts/ - Directory for system prompt files
      - index.json - Index of all prompts with metadata
      - {prompt_id}.json - Individual prompt files
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.prompts_dir = self.base_dir / "system_prompts"
        self.index_file = self.prompts_dir / "index.json"
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self._index_cache: Optional[Dict[str, Any]] = None
    
    async def _load_index(self) -> Dict[str, Any]:
        """Load prompt index."""
        if self._index_cache is not None:
            return self._index_cache
        
        if not self.index_file.exists():
            self._index_cache = {"prompts": {}, "default_id": None}
            return self._index_cache
        
        try:
            async with aiofiles.open(self.index_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._index_cache = json.loads(content)
                return self._index_cache
        except Exception as e:
            logger.error(f"Error loading prompt index: {e}")
            self._index_cache = {"prompts": {}, "default_id": None}
            return self._index_cache
    
    async def _save_index(self):
        """Save prompt index."""
        try:
            async with aiofiles.open(self.index_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._index_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving prompt index: {e}")
    
    async def get_system_prompt(self, prompt_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a system prompt.
        
        Args:
            prompt_id: Prompt ID, or None for default prompt
        
        Returns:
            Prompt dict with id, name, content, is_default, created_at, updated_at
        """
        index = await self._load_index()
        
        if prompt_id:
            if prompt_id not in index["prompts"]:
                return None
            prompt_file = self.prompts_dir / f"{prompt_id}.json"
        else:
            # Get default prompt
            default_id = index.get("default_id")
            if not default_id:
                return None
            prompt_id = default_id
            prompt_file = self.prompts_dir / f"{prompt_id}.json"
        
        if not prompt_file.exists():
            # Stale index entry
            if prompt_id in index["prompts"]:
                del index["prompts"][prompt_id]
                if index.get("default_id") == prompt_id:
                    index["default_id"] = None
                await self._save_index()
            return None
        
        try:
            async with aiofiles.open(prompt_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                prompt_data = json.loads(content)
                return prompt_data
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_id}: {e}")
            return None
    
    async def set_system_prompt(
        self,
        content: str,
        name: Optional[str] = None,
        prompt_id: Optional[str] = None,
        is_default: bool = False
    ) -> str:
        """Create or update a system prompt.
        
        Args:
            content: Prompt content
            name: Prompt name
            prompt_id: Existing prompt ID (for updates), or None to create new
            is_default: Whether this is the default prompt
        
        Returns:
            Prompt ID
        """
        index = await self._load_index()
        now = datetime.now().isoformat()
        
        if prompt_id and prompt_id in index["prompts"]:
            # Update existing
            prompt_file = self.prompts_dir / f"{prompt_id}.json"
            existing_data = await self.get_system_prompt(prompt_id)
            if existing_data:
                created_at = existing_data.get("created_at", now)
            else:
                created_at = now
        else:
            # Create new
            prompt_id = str(uuid.uuid4())
            prompt_file = self.prompts_dir / f"{prompt_id}.json"
            created_at = now
        
        # If setting as default, unset other defaults
        if is_default:
            for pid in index["prompts"]:
                if pid != prompt_id:
                    other_file = self.prompts_dir / f"{pid}.json"
                    if other_file.exists():
                        try:
                            async with aiofiles.open(other_file, 'r', encoding='utf-8') as f:
                                other_data = json.loads(await f.read())
                                other_data["is_default"] = False
                            async with aiofiles.open(other_file, 'w', encoding='utf-8') as f:
                                await f.write(json.dumps(other_data, indent=2))
                        except Exception as e:
                            logger.error(f"Error updating prompt {pid}: {e}")
            index["default_id"] = prompt_id
        
        # Save prompt file
        prompt_data = {
            "id": prompt_id,
            "name": name or "Untitled Prompt",
            "content": content,
            "is_default": is_default,
            "created_at": created_at,
            "updated_at": now
        }
        
        try:
            async with aiofiles.open(prompt_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(prompt_data, indent=2))
        except Exception as e:
            logger.error(f"Error saving prompt {prompt_id}: {e}")
            raise
        
        # Update index
        index["prompts"][prompt_id] = {
            "name": prompt_data["name"],
            "is_default": is_default,
            "created_at": created_at,
            "updated_at": now
        }
        self._index_cache = index
        await self._save_index()
        
        return prompt_id
    
    async def list_system_prompts(self) -> List[Dict[str, Any]]:
        """List all system prompts.
        
        Returns:
            List of prompt dicts
        """
        index = await self._load_index()
        prompts = []
        
        for prompt_id in index.get("prompts", {}):
            prompt = await self.get_system_prompt(prompt_id)
            if prompt:
                prompts.append(prompt)
        
        # Sort: default first, then by updated_at desc
        prompts.sort(key=lambda p: (not p.get("is_default", False), p.get("updated_at", "")))
        return prompts
    
    async def delete_system_prompt(self, prompt_id: str) -> bool:
        """Delete a system prompt.
        
        Args:
            prompt_id: Prompt ID to delete
        
        Returns:
            True if deleted, False if not found
        """
        index = await self._load_index()
        
        if prompt_id not in index["prompts"]:
            return False
        
        # Delete file
        prompt_file = self.prompts_dir / f"{prompt_id}.json"
        if prompt_file.exists():
            try:
                prompt_file.unlink()
            except Exception as e:
                logger.error(f"Error deleting prompt file {prompt_id}: {e}")
        
        # Update index
        del index["prompts"][prompt_id]
        if index.get("default_id") == prompt_id:
            index["default_id"] = None
        self._index_cache = index
        await self._save_index()
        
        return True


class FileCharacterCardStore:
    """File-based storage for character cards.
    
    Structure:
    - character_card.json - Single character card file
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.card_file = self.base_dir / "character_card.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_character_card(self) -> Optional[Dict[str, Any]]:
        """Get character card.
        
        Returns:
            Character card dict or None
        """
        if not self.card_file.exists():
            return None
        
        try:
            async with aiofiles.open(self.card_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"Error loading character card: {e}")
            return None
    
    async def set_character_card(self, card: Optional[Dict[str, Any]]) -> bool:
        """Set character card.
        
        Args:
            card: Character card dict, or None to delete
        
        Returns:
            True if successful
        """
        try:
            if card is None:
                if self.card_file.exists():
                    self.card_file.unlink()
                return True
            
            async with aiofiles.open(self.card_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(card, indent=2, default=str))
            return True
        except Exception as e:
            logger.error(f"Error saving character card: {e}")
            return False


class FileUserProfileStore:
    """File-based storage for user profiles.
    
    Structure:
    - user_profile.json - Single user profile file
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.profile_file = self.base_dir / "user_profile.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Get user profile.
        
        Returns:
            User profile dict or None
        """
        if not self.profile_file.exists():
            return None
        
        try:
            async with aiofiles.open(self.profile_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"Error loading user profile: {e}")
            return None
    
    async def set_user_profile(self, profile: Optional[Dict[str, Any]]) -> bool:
        """Set user profile.
        
        Args:
            profile: User profile dict, or None to delete
        
        Returns:
            True if successful
        """
        try:
            if profile is None:
                if self.profile_file.exists():
                    self.profile_file.unlink()
                return True
            
            async with aiofiles.open(self.profile_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(profile, indent=2, default=str))
            return True
        except Exception as e:
            logger.error(f"Error saving user profile: {e}")
            return False


class FileSamplerSettingsStore:
    """File-based storage for sampler settings.
    
    Structure:
    - sampler_settings.json - Sampler settings file
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.settings_file = self.base_dir / "sampler_settings.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._settings_cache: Optional[Dict[str, Any]] = None
    
    async def _load_settings(self) -> Dict[str, Any]:
        """Load sampler settings."""
        if self._settings_cache is not None:
            return self._settings_cache
        
        if not self.settings_file.exists():
            self._settings_cache = {}
            return self._settings_cache
        
        try:
            async with aiofiles.open(self.settings_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._settings_cache = json.loads(content)
                return self._settings_cache
        except Exception as e:
            logger.error(f"Error loading sampler settings: {e}")
            self._settings_cache = {}
            return self._settings_cache
    
    async def _save_settings(self):
        """Save sampler settings."""
        try:
            async with aiofiles.open(self.settings_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._settings_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving sampler settings: {e}")
    
    async def get_sampler_settings(self) -> Dict[str, Any]:
        """Get sampler settings.
        
        Returns:
            Sampler settings dict
        """
        return await self._load_settings()
    
    async def set_sampler_settings(self, settings: Dict[str, Any]) -> bool:
        """Set sampler settings.
        
        Args:
            settings: Sampler settings dict
        
        Returns:
            True if successful
        """
        self._settings_cache = settings
        await self._save_settings()
        return True
    
    async def update_sampler_settings(self, updates: Dict[str, Any]) -> bool:
        """Update sampler settings (merge with existing).
        
        Args:
            updates: Partial settings dict to merge
        
        Returns:
            True if successful
        """
        settings = await self._load_settings()
        settings.update(updates)
        self._settings_cache = settings
        await self._save_settings()
        return True

