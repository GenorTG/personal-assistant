"""Fast file-based app settings storage using JSON."""
from typing import Any, Dict, Optional
from pathlib import Path
import json
import aiofiles
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class FileSettingsStore:
    """Fast file-based storage for app settings using JSON.
    
    Structure:
    - settings.json - All app settings in one JSON file
    - .encryption_key - Key for encrypting sensitive settings
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.settings_file = self.base_dir / "settings.json"
        self.key_file = self.base_dir / ".encryption_key"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._settings_cache: Optional[Dict[str, Any]] = None
        self._fernet: Optional[Fernet] = None
        self._init_encryption_key()
    
    def _init_encryption_key(self):
        """Initialize encryption key for sensitive settings."""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.key_file, 'wb') as f:
                f.write(key)
        
        self._fernet = Fernet(key)
    
    async def _load_settings(self) -> Dict[str, Any]:
        """Load settings from JSON file."""
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
            logger.error(f"Error loading settings: {e}")
            self._settings_cache = {}
            return self._settings_cache
    
    async def _save_settings(self):
        """Save settings to JSON file."""
        try:
            async with aiofiles.open(self.settings_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._settings_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value.
        
        Args:
            key: Setting key
            default: Default value if setting doesn't exist
        
        Returns:
            Setting value (decrypted if encrypted)
        """
        settings = await self._load_settings()
        
        if key not in settings:
            return default
        
        setting_data = settings[key]
        
        # Handle encrypted settings
        if isinstance(setting_data, dict) and setting_data.get("encrypted"):
            try:
                encrypted_value = setting_data["value"]
                decrypted = self._fernet.decrypt(encrypted_value.encode()).decode()
                return decrypted
            except Exception as e:
                logger.error(f"Error decrypting setting {key}: {e}")
                return default
        
        # Regular setting
        return setting_data.get("value") if isinstance(setting_data, dict) else setting_data
    
    async def set_setting(self, key: str, value: str, encrypted: bool = False):
        """Set a setting value.
        
        Args:
            key: Setting key
            value: Setting value
            encrypted: Whether to encrypt the value
        """
        settings = await self._load_settings()
        
        if encrypted:
            # Encrypt the value
            encrypted_value = self._fernet.encrypt(value.encode()).decode()
            settings[key] = {
                "value": encrypted_value,
                "encrypted": True
            }
        else:
            # Store as plain value
            settings[key] = {
                "value": value,
                "encrypted": False
            }
        
        self._settings_cache = settings
        await self._save_settings()
    
    async def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings (decrypted).
        
        Returns:
            Dictionary of all settings with decrypted values
        """
        settings = await self._load_settings()
        result = {}
        
        for key, setting_data in settings.items():
            if isinstance(setting_data, dict) and setting_data.get("encrypted"):
                try:
                    encrypted_value = setting_data["value"]
                    result[key] = self._fernet.decrypt(encrypted_value.encode()).decode()
                except Exception as e:
                    logger.error(f"Error decrypting setting {key}: {e}")
                    result[key] = None
            else:
                result[key] = setting_data.get("value") if isinstance(setting_data, dict) else setting_data
        
        return result
    
    async def delete_setting(self, key: str) -> bool:
        """Delete a setting.
        
        Args:
            key: Setting key to delete
        
        Returns:
            True if deleted, False if not found
        """
        settings = await self._load_settings()
        
        if key not in settings:
            return False
        
        del settings[key]
        self._settings_cache = settings
        await self._save_settings()
        return True
    
    async def clear_all(self) -> int:
        """Clear all settings (delete settings file and reset cache).
        
        Returns:
            Number of settings cleared
        """
        count = 0
        if self.settings_file.exists():
            try:
                # Count settings before clearing
                settings = await self._load_settings()
                count = len(settings)
                
                # Delete file
                self.settings_file.unlink()
                logger.info(f"Deleted settings.json with {count} settings")
            except Exception as e:
                logger.error(f"Error deleting settings.json: {e}")
        
        # Reset cache
        self._settings_cache = {}
        await self._save_settings()  # Re-create empty settings file
        return count

