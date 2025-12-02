"""File-based storage for downloads and model metadata."""
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json
import aiofiles
import logging

logger = logging.getLogger(__name__)


class DownloadHistoryStore:
    """File-based storage for download history using JSON log files.
    
    Structure:
    - downloads/history.json - All download history
    - downloads/active.json - Currently active downloads
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.downloads_dir = self.base_dir / "downloads"
        self.history_file = self.downloads_dir / "history.json"
        self.active_file = self.downloads_dir / "active.json"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self._history_cache: Optional[List[Dict[str, Any]]] = None
        self._active_cache: Optional[Dict[str, Dict[str, Any]]] = None
    
    async def _load_history(self) -> List[Dict[str, Any]]:
        """Load download history from file."""
        if self._history_cache is not None:
            return self._history_cache
        
        if not self.history_file.exists():
            self._history_cache = []
            return self._history_cache
        
        try:
            async with aiofiles.open(self.history_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._history_cache = json.loads(content)
                return self._history_cache
        except Exception as e:
            logger.error(f"Error loading download history: {e}")
            self._history_cache = []
            return self._history_cache
    
    async def _save_history(self):
        """Save download history to file."""
        try:
            async with aiofiles.open(self.history_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._history_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving download history: {e}")
    
    async def _load_active(self) -> Dict[str, Dict[str, Any]]:
        """Load active downloads from file."""
        if self._active_cache is not None:
            return self._active_cache
        
        if not self.active_file.exists():
            self._active_cache = {}
            return self._active_cache
        
        try:
            async with aiofiles.open(self.active_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._active_cache = json.loads(content)
                return self._active_cache
        except Exception as e:
            logger.error(f"Error loading active downloads: {e}")
            self._active_cache = {}
            return self._active_cache
    
    async def _save_active(self):
        """Save active downloads to file."""
        try:
            async with aiofiles.open(self.active_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._active_cache, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving active downloads: {e}")
    
    async def save_download(self, download_data: Dict[str, Any]):
        """Save a download record (adds to history and updates active)."""
        # Update active downloads
        active = await self._load_active()
        download_id = download_data["id"]
        
        # If completed/failed/cancelled, remove from active
        if download_data.get("status") in ["completed", "failed", "cancelled"]:
            if download_id in active:
                del active[download_id]
        else:
            # Update or add to active
            active[download_id] = download_data
        
        self._active_cache = active
        await self._save_active()
        
        # Add to history (or update existing)
        history = await self._load_history()
        
        # Find existing entry
        existing_idx = None
        for i, entry in enumerate(history):
            if entry.get("id") == download_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            history[existing_idx] = download_data
        else:
            history.append(download_data)
        
        # Sort by created_at descending (most recent first)
        history.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        
        self._history_cache = history
        await self._save_history()
    
    async def get_download(self, download_id: str) -> Optional[Dict[str, Any]]:
        """Get a download by ID (checks active first, then history)."""
        # Check active downloads
        active = await self._load_active()
        if download_id in active:
            return active[download_id]
        
        # Check history
        history = await self._load_history()
        for entry in history:
            if entry.get("id") == download_id:
                return entry
        
        return None
    
    async def list_downloads(
        self,
        status: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List downloads, optionally filtered by status.
        
        Args:
            status: Filter by status (None = all)
            limit: Maximum number to return (None = all)
        """
        history = await self._load_history()
        
        if status:
            history = [d for d in history if d.get("status") == status]
        
        if limit:
            history = history[:limit]
        
        return history
    
    async def get_active_downloads(self) -> List[Dict[str, Any]]:
        """Get all active downloads (pending, downloading)."""
        active = await self._load_active()
        return list(active.values())


class ModelMetadataStore:
    """File-based storage for model metadata.
    
    Structure:
    - Each model has a {model_filename}.json metadata file next to it
    - Example: model.gguf -> model.gguf.json
    """
    
    def __init__(self, models_dir: Path):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_metadata_path(self, model_path: Path) -> Path:
        """Get the metadata file path for a model."""
        return model_path.with_suffix(model_path.suffix + ".json")
    
    async def get_metadata(self, model_path: Path) -> Optional[Dict[str, Any]]:
        """Get metadata for a model.
        
        Args:
            model_path: Path to the model file
            
        Returns:
            Metadata dictionary or None if not found
        """
        metadata_path = self._get_metadata_path(model_path)
        
        if not metadata_path.exists():
            return None
        
        try:
            async with aiofiles.open(metadata_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"Error reading metadata for {model_path}: {e}")
            return None
    
    async def save_metadata(self, model_path: Path, metadata: Dict[str, Any]):
        """Save metadata for a model.
        
        Args:
            model_path: Path to the model file
            metadata: Metadata dictionary to save
        """
        metadata_path = self._get_metadata_path(model_path)
        
        # Ensure model_path is relative to models_dir for storage
        if model_path.is_absolute():
            try:
                relative_path = model_path.relative_to(self.models_dir)
            except ValueError:
                # Model not in models_dir, store full path
                relative_path = model_path
        else:
            relative_path = model_path
        
        # Store relative path in metadata
        metadata["model_path"] = str(relative_path)
        metadata["filename"] = model_path.name
        metadata["last_updated"] = datetime.utcnow().isoformat()
        
        try:
            async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata, indent=2, default=str))
        except Exception as e:
            logger.error(f"Error saving metadata for {model_path}: {e}")
    
    async def delete_metadata(self, model_path: Path):
        """Delete metadata for a model.
        
        Args:
            model_path: Path to the model file
        """
        metadata_path = self._get_metadata_path(model_path)
        
        if metadata_path.exists():
            try:
                metadata_path.unlink()
            except Exception as e:
                logger.error(f"Error deleting metadata for {model_path}: {e}")
    
    async def list_all_metadata(self) -> List[Dict[str, Any]]:
        """List metadata for all models in the models directory.
        
        Returns:
            List of metadata dictionaries
        """
        metadata_files = list(self.models_dir.rglob("*.gguf.json"))
        results = []
        
        for metadata_path in metadata_files:
            try:
                async with aiofiles.open(metadata_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    metadata = json.loads(content)
                    # Resolve model path
                    model_path = metadata_path.with_suffix("")
                    if model_path.exists():
                        metadata["model_path"] = str(model_path)
                        results.append(metadata)
            except Exception as e:
                logger.error(f"Error reading metadata from {metadata_path}: {e}")
        
        return results
    
    async def find_metadata_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Find metadata by model filename.
        
        Args:
            filename: Model filename (e.g., "model.gguf")
            
        Returns:
            Metadata dictionary or None if not found
        """
        # Search in models directory
        for model_path in self.models_dir.rglob(filename):
            if model_path.is_file() and model_path.suffix == ".gguf":
                metadata = await self.get_metadata(model_path)
                if metadata:
                    return metadata
        
        return None

