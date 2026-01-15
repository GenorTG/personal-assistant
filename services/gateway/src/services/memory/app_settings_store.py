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
    """File-based storage for multiple character cards.
    
    Structure:
    - character_cards/ - Directory containing character card files
      - {card_id}.json - Individual character card files
    - current_character_card_id.json - ID of currently active character card
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.cards_dir = self.base_dir / "character_cards"
        self.current_id_file = self.base_dir / "current_character_card_id.json"
        self.cards_dir.mkdir(parents=True, exist_ok=True)
    
    async def list_character_cards(self) -> List[Dict[str, Any]]:
        """List all character cards.
        
        Returns:
            List of character card dicts with 'id' and 'name' fields
        """
        cards = []
        if not self.cards_dir.exists():
            return cards
        
        try:
            for card_file in self.cards_dir.glob("*.json"):
                card_id = card_file.stem
                try:
                    async with aiofiles.open(card_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        card_data = json.loads(content)
                        cards.append({
                            "id": card_id,
                            "name": card_data.get("name", card_id),
                            **card_data
                        })
                except Exception as e:
                    logger.warning(f"Error loading character card {card_id}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error listing character cards: {e}")
        
        return cards
    
    async def get_character_card(self, card_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get character card by ID, or current active card if ID is None.
        
        Args:
            card_id: Character card ID, or None to get current active card
        
        Returns:
            Character card dict or None
        """
        # If no ID provided, get current active card ID
        if card_id is None:
            if self.current_id_file.exists():
                try:
                    async with aiofiles.open(self.current_id_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        card_id = json.loads(content).get("card_id")
                except Exception:
                    # Fallback: try to get first card or legacy single card
                    cards = await self.list_character_cards()
                    if cards:
                        card_id = cards[0]["id"]
                    else:
                        # Try legacy single card file
                        legacy_file = self.base_dir / "character_card.json"
                        if legacy_file.exists():
                            try:
                                async with aiofiles.open(legacy_file, 'r', encoding='utf-8') as f:
                                    content = await f.read()
                                    return json.loads(content)
                            except Exception:
                                pass
                        return None
        
        card_file = self.cards_dir / f"{card_id}.json"
        if not card_file.exists():
            return None
        
        try:
            async with aiofiles.open(card_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                card_data = json.loads(content)
                card_data["id"] = card_id
                return card_data
        except Exception as e:
            logger.error(f"Error loading character card {card_id}: {e}")
            return None
    
    async def create_character_card(self, card: Dict[str, Any]) -> str:
        """Create a new character card.
        
        Args:
            card: Character card dict (must include 'name')
        
        Returns:
            Character card ID
        """
        import uuid
        card_id = str(uuid.uuid4())
        card["id"] = card_id
        card["created_at"] = datetime.utcnow().isoformat()
        
        card_file = self.cards_dir / f"{card_id}.json"
        try:
            async with aiofiles.open(card_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(card, indent=2, default=str))
            
            # Set as current if it's the first card
            cards = await self.list_character_cards()
            if len(cards) == 1:
                await self.set_current_character_card(card_id)
            
            return card_id
        except Exception as e:
            logger.error(f"Error creating character card: {e}")
            raise
    
    async def update_character_card(self, card_id: str, card: Dict[str, Any]) -> bool:
        """Update an existing character card.
        
        Args:
            card_id: Character card ID
            card: Updated character card dict
        
        Returns:
            True if successful
        """
        card_file = self.cards_dir / f"{card_id}.json"
        if not card_file.exists():
            return False
        
        card["id"] = card_id
        card["updated_at"] = datetime.utcnow().isoformat()
        
        try:
            async with aiofiles.open(card_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(card, indent=2, default=str))
            return True
        except Exception as e:
            logger.error(f"Error updating character card {card_id}: {e}")
            return False
    
    async def delete_character_card(self, card_id: str) -> bool:
        """Delete a character card.
        
        Args:
            card_id: Character card ID
        
        Returns:
            True if successful
        """
        card_file = self.cards_dir / f"{card_id}.json"
        if not card_file.exists():
            return False
        
        try:
            card_file.unlink()
            
            # If this was the current card, clear current or set to another
            current_id = await self.get_current_character_card_id()
            if current_id == card_id:
                cards = await self.list_character_cards()
                if cards:
                    await self.set_current_character_card(cards[0]["id"])
                else:
                    if self.current_id_file.exists():
                        self.current_id_file.unlink()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting character card {card_id}: {e}")
            return False
    
    async def set_current_character_card(self, card_id: str) -> bool:
        """Set the current active character card.
        
        Args:
            card_id: Character card ID
        
        Returns:
            True if successful
        """
        # Verify card exists
        card_file = self.cards_dir / f"{card_id}.json"
        if not card_file.exists():
            return False
        
        try:
            async with aiofiles.open(self.current_id_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps({"card_id": card_id}, indent=2))
            return True
        except Exception as e:
            logger.error(f"Error setting current character card: {e}")
            return False
    
    async def get_current_character_card_id(self) -> Optional[str]:
        """Get the current active character card ID.
        
        Returns:
            Character card ID or None
        """
        if not self.current_id_file.exists():
            return None
        
        try:
            async with aiofiles.open(self.current_id_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content).get("card_id")
        except Exception:
            return None
    
    async def set_character_card(self, card: Optional[Dict[str, Any]]) -> bool:
        """Legacy method: Set character card (creates new or updates current).
        
        Args:
            card: Character card dict, or None to delete current
        
        Returns:
            True if successful
        """
        if card is None:
            current_id = await self.get_current_character_card_id()
            if current_id:
                return await self.delete_character_card(current_id)
            return True
        
        current_id = await self.get_current_character_card_id()
        if current_id:
            # Update existing
            return await self.update_character_card(current_id, card)
        else:
            # Create new
            card_id = await self.create_character_card(card)
            return await self.set_current_character_card(card_id)


class FileUserProfileStore:
    """File-based storage for multiple user profiles.
    
    Structure:
    - user_profiles/ - Directory containing user profile files
      - {profile_id}.json - Individual user profile files
    - current_user_profile_id.json - ID of currently active user profile
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.profiles_dir = self.base_dir / "user_profiles"
        self.current_id_file = self.base_dir / "current_user_profile_id.json"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
    
    async def list_user_profiles(self) -> List[Dict[str, Any]]:
        """List all user profiles.
        
        Returns:
            List of user profile dicts with 'id' and 'name' fields
        """
        profiles = []
        if not self.profiles_dir.exists():
            return profiles
        
        try:
            for profile_file in self.profiles_dir.glob("*.json"):
                profile_id = profile_file.stem
                try:
                    async with aiofiles.open(profile_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        profile_data = json.loads(content)
                        profiles.append({
                            "id": profile_id,
                            "name": profile_data.get("name", profile_id),
                            **profile_data
                        })
                except Exception as e:
                    logger.warning(f"Error loading user profile {profile_id}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error listing user profiles: {e}")
        
        return profiles
    
    async def get_user_profile(self, profile_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get user profile by ID, or current active profile if ID is None.
        
        Args:
            profile_id: User profile ID, or None to get current active profile
        
        Returns:
            User profile dict or None
        """
        # If no ID provided, get current active profile ID
        if profile_id is None:
            if self.current_id_file.exists():
                try:
                    async with aiofiles.open(self.current_id_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        profile_id = json.loads(content).get("profile_id")
                except Exception:
                    # Fallback: try to get first profile or legacy single profile
                    profiles = await self.list_user_profiles()
                    if profiles:
                        profile_id = profiles[0]["id"]
                    else:
                        # Try legacy single profile file
                        legacy_file = self.base_dir / "user_profile.json"
                        if legacy_file.exists():
                            try:
                                async with aiofiles.open(legacy_file, 'r', encoding='utf-8') as f:
                                    content = await f.read()
                                    return json.loads(content)
                            except Exception:
                                pass
                        return None
        
        profile_file = self.profiles_dir / f"{profile_id}.json"
        if not profile_file.exists():
            return None
        
        try:
            async with aiofiles.open(profile_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                profile_data = json.loads(content)
                profile_data["id"] = profile_id
                return profile_data
        except Exception as e:
            logger.error(f"Error loading user profile {profile_id}: {e}")
            return None
    
    async def create_user_profile(self, profile: Dict[str, Any]) -> str:
        """Create a new user profile.
        
        Args:
            profile: User profile dict (must include 'name')
        
        Returns:
            User profile ID
        """
        profile_id = str(uuid.uuid4())
        profile["id"] = profile_id
        profile["created_at"] = datetime.utcnow().isoformat()
        
        profile_file = self.profiles_dir / f"{profile_id}.json"
        try:
            async with aiofiles.open(profile_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(profile, indent=2, default=str))
            
            # Set as current if it's the first profile
            profiles = await self.list_user_profiles()
            if len(profiles) == 1:
                await self.set_current_user_profile(profile_id)
            
            return profile_id
        except Exception as e:
            logger.error(f"Error creating user profile: {e}")
            raise
    
    async def update_user_profile(self, profile_id: str, profile: Dict[str, Any]) -> bool:
        """Update an existing user profile.
        
        Args:
            profile_id: User profile ID
            profile: Updated user profile dict
        
        Returns:
            True if successful
        """
        profile_file = self.profiles_dir / f"{profile_id}.json"
        if not profile_file.exists():
            return False
        
        profile["id"] = profile_id
        profile["updated_at"] = datetime.utcnow().isoformat()
        
        try:
            async with aiofiles.open(profile_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(profile, indent=2, default=str))
            return True
        except Exception as e:
            logger.error(f"Error updating user profile {profile_id}: {e}")
            return False
    
    async def delete_user_profile(self, profile_id: str) -> bool:
        """Delete a user profile.
        
        Args:
            profile_id: User profile ID
        
        Returns:
            True if successful
        """
        profile_file = self.profiles_dir / f"{profile_id}.json"
        if not profile_file.exists():
            return False
        
        try:
            profile_file.unlink()
            
            # If this was the current profile, clear current or set to another
            current_id = await self.get_current_user_profile_id()
            if current_id == profile_id:
                profiles = await self.list_user_profiles()
                if profiles:
                    await self.set_current_user_profile(profiles[0]["id"])
                else:
                    if self.current_id_file.exists():
                        self.current_id_file.unlink()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting user profile {profile_id}: {e}")
            return False
    
    async def set_current_user_profile(self, profile_id: str) -> bool:
        """Set the current active user profile.
        
        Args:
            profile_id: User profile ID
        
        Returns:
            True if successful
        """
        # Verify profile exists
        profile_file = self.profiles_dir / f"{profile_id}.json"
        if not profile_file.exists():
            return False
        
        try:
            async with aiofiles.open(self.current_id_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps({"profile_id": profile_id}, indent=2))
            return True
        except Exception as e:
            logger.error(f"Error setting current user profile: {e}")
            return False
    
    async def get_current_user_profile_id(self) -> Optional[str]:
        """Get the current active user profile ID.
        
        Returns:
            User profile ID or None
        """
        if not self.current_id_file.exists():
            return None
        
        try:
            async with aiofiles.open(self.current_id_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content).get("profile_id")
        except Exception:
            return None
    
    async def set_user_profile(self, profile: Optional[Dict[str, Any]]) -> bool:
        """Legacy method: Set user profile (creates new or updates current).
        
        Args:
            profile: User profile dict, or None to delete current
        
        Returns:
            True if successful
        """
        if profile is None:
            current_id = await self.get_current_user_profile_id()
            if current_id:
                return await self.delete_user_profile(current_id)
            return True
        
        current_id = await self.get_current_user_profile_id()
        if current_id:
            # Update existing
            return await self.update_user_profile(current_id, profile)
        else:
            # Create new
            profile_id = await self.create_user_profile(profile)
            return await self.set_current_user_profile(profile_id)


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

