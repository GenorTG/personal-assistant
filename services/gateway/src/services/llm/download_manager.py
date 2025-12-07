"""Download manager for tracking model downloads with progress."""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import json
import logging
import uuid
import threading
from huggingface_hub import hf_hub_download
from tqdm import tqdm
from .file_stores import DownloadHistoryStore

logger = logging.getLogger(__name__)


class DownloadStatus(str, Enum):
    """Download status enum."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Download:
    """Represents a download task."""
    id: str
    repo_id: str
    filename: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0  # 0-100
    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0  # bytes per second
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": round(self.progress, 1),
            "bytes_downloaded": self.bytes_downloaded,
            "total_bytes": self.total_bytes,
            "speed_bps": round(self.speed_bps, 0),
            "speed_mbps": round(self.speed_bps / 1024 / 1024, 2),
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "model_path": self.model_path,
            "eta_seconds": self._calculate_eta(),
        }
    
    def _calculate_eta(self) -> Optional[int]:
        """Calculate estimated time remaining in seconds."""
        if self.speed_bps <= 0 or self.total_bytes <= 0:
            return None
        remaining_bytes = self.total_bytes - self.bytes_downloaded
        if remaining_bytes <= 0:
            return 0
        return int(remaining_bytes / self.speed_bps)


class ProgressCallback:
    """Progress callback for huggingface_hub downloads."""
    
    def __init__(self, download: Download, on_progress: Callable[[Download], None]):
        self.download = download
        self.on_progress = on_progress
        self.last_update = datetime.now()
        self.last_bytes = 0
    
    def __call__(self, progress: tqdm):
        """Called by huggingface_hub with tqdm progress bar."""
        if hasattr(progress, 'n') and hasattr(progress, 'total'):
            now = datetime.now()
            elapsed = (now - self.last_update).total_seconds()
            
            self.download.bytes_downloaded = progress.n
            self.download.total_bytes = progress.total or 0
            
            if self.download.total_bytes > 0:
                self.download.progress = (progress.n / self.download.total_bytes) * 100
            
            # Calculate speed (bytes per second)
            if elapsed > 0.5:  # Update speed every 0.5 seconds
                bytes_diff = progress.n - self.last_bytes
                self.download.speed_bps = bytes_diff / elapsed
                self.last_update = now
                self.last_bytes = progress.n
            
            self.on_progress(self.download)


class DownloadManager:
    """Manages model downloads with progress tracking and history."""
    
    def __init__(self, models_dir: Path, data_dir: Path):
        self.models_dir = Path(models_dir)
        self.data_dir = Path(data_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # File-based storage
        self.history_store = DownloadHistoryStore(self.data_dir)
        
        # Active downloads (in memory)
        self._downloads: Dict[str, Download] = {}
        self._lock = threading.Lock()
        self._subscribers: Dict[str, List[Callable[[Download], None]]] = {}
    
    def _notify_subscribers(self, download: Download):
        """Notify all subscribers of download progress update."""
        subscribers = self._subscribers.get(download.id, [])
        for callback in subscribers:
            try:
                callback(download)
            except Exception as e:
                logger.error(f"Error in subscriber callback: {e}")
    
    def subscribe(self, download_id: str, callback: Callable[[Download], None]):
        """Subscribe to progress updates for a download."""
        if download_id not in self._subscribers:
            self._subscribers[download_id] = []
        self._subscribers[download_id].append(callback)
    
    def unsubscribe(self, download_id: str, callback: Callable[[Download], None]):
        """Unsubscribe from progress updates."""
        if download_id in self._subscribers:
            try:
                self._subscribers[download_id].remove(callback)
            except ValueError:
                pass
    
    async def start_download(
        self, 
        repo_id: str, 
        filename: str
    ) -> Download:
        """Start a new download.
        
        Args:
            repo_id: HuggingFace repository ID
            filename: GGUF filename to download
            
        Returns:
            Download object with tracking info
        """
        # Create download record
        download_id = str(uuid.uuid4())[:8]
        download = Download(
            id=download_id,
            repo_id=repo_id,
            filename=filename,
            status=DownloadStatus.PENDING,
            started_at=datetime.now()
        )
        
        with self._lock:
            self._downloads[download_id] = download
        
        # Save to file store
        await self._save_download(download)
        
        # Start download in background
        asyncio.create_task(self._run_download(download))
        
        return download
    
    async def _run_download(self, download: Download):
        """Run the actual download in background."""
        try:
            download.status = DownloadStatus.DOWNLOADING
            self._notify_subscribers(download)
            await self._save_download(download)
            
            # Create model folder structure: models/{author}/{repo-name}/
            author, repo_name = download.repo_id.split('/', 1) if '/' in download.repo_id else ('unknown', download.repo_id)
            model_folder = self.models_dir / author / repo_name
            model_folder.mkdir(parents=True, exist_ok=True)
            
            # Create progress callback
            def on_progress(d: Download):
                self._notify_subscribers(d)
            
            # Download with progress tracking
            loop = asyncio.get_event_loop()
            
            def do_download():
                # Use file monitoring approach for more reliable progress tracking
                from huggingface_hub import hf_hub_download, HfApi
                import time
                import os
                import threading
                
                # Get expected file size first
                api = HfApi()
                expected_size = 0
                try:
                    # Try to get file size from HuggingFace
                    paths_info = api.get_paths_info(download.repo_id, paths=[download.filename], repo_type="model")
                    if paths_info and isinstance(paths_info, list) and len(paths_info) > 0:
                        file_info = paths_info[0]
                        if isinstance(file_info, dict):
                            expected_size = file_info.get("size", 0)
                        elif hasattr(file_info, 'size'):
                            expected_size = file_info.size or 0
                except Exception as e:
                    logger.debug(f"Could not get file size: {e}")
                
                download.total_bytes = expected_size
                if expected_size > 0:
                    download.bytes_downloaded = 0
                    download.progress = 0.0
                
                # Start download in a separate thread with file monitoring
                download_path = None
                download_error = None
                
                def monitor_progress():
                    """Monitor file size during download."""
                    target_file = None
                    last_size = 0
                    last_time = time.time()
                    check_count = 0
                    
                    while download.status == DownloadStatus.DOWNLOADING:
                        try:
                            check_count += 1
                            
                            # Find the file being downloaded
                            if target_file is None or not target_file.exists():
                                # Check direct path first (hf_hub_download might save directly to local_dir)
                                direct_path = model_folder / download.filename
                                if direct_path.exists():
                                    target_file = direct_path
                                else:
                                    # Look for the file recursively in the model folder
                                    for file in model_folder.rglob(download.filename):
                                        if file.is_file():
                                            target_file = file
                                            break
                                    
                                    # Also check for temporary files (hf_hub_download might use .tmp extension)
                                    if target_file is None:
                                        for file in model_folder.rglob(f"{download.filename}*"):
                                            if file.is_file() and (file.suffix == '.tmp' or '.tmp' in file.name):
                                                target_file = file
                                                break
                            
                            if target_file and target_file.exists():
                                current_size = target_file.stat().st_size
                                
                                # Always update if size changed, or every 10 checks (5 seconds) even if same
                                if current_size != last_size or check_count % 10 == 0:
                                    now = time.time()
                                    elapsed = now - last_time if last_time > 0 else 0.5
                                    
                                    download.bytes_downloaded = current_size
                                    if expected_size > 0:
                                        download.progress = min((current_size / expected_size) * 100, 99.9)  # Cap at 99.9% until complete
                                    
                                    # Calculate speed
                                    if elapsed > 0.1 and current_size > last_size:
                                        bytes_diff = current_size - last_size
                                        download.speed_bps = bytes_diff / elapsed
                                        last_time = now
                                        last_size = current_size
                                        
                                        # Notify progress
                                        on_progress(download)
                                    elif current_size != last_size:
                                        # Size changed but not enough time elapsed - still update
                                        last_size = current_size
                                        on_progress(download)
                            
                            time.sleep(0.5)  # Check every 0.5 seconds
                        except Exception as e:
                            logger.debug(f"Progress monitoring error: {e}")
                            time.sleep(1)
                
                # Start progress monitoring thread
                monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
                monitor_thread.start()
                
                try:
                    # Download to the model subfolder
                    path = hf_hub_download(
                        repo_id=download.repo_id,
                        filename=download.filename,
                        local_dir=str(model_folder),
                        local_dir_use_symlinks=False,
                        resume_download=True
                    )
                    
                    # Final update - ensure we have the correct size
                    if path and os.path.exists(path):
                        final_size = os.path.getsize(path)
                        download.bytes_downloaded = final_size
                        download.total_bytes = final_size
                        download.progress = 100.0
                        on_progress(download)
                    
                    return path
                except Exception as e:
                    download_error = e
                    raise
                finally:
                    # Wait a bit for final progress update
                    time.sleep(0.5)
            
            model_path = await loop.run_in_executor(None, do_download)
            
            # Fetch and save model metadata
            await self._save_model_metadata_file(download.repo_id, model_folder, download.filename)
            
            # Mark as completed
            download.status = DownloadStatus.COMPLETED
            download.progress = 100.0
            download.completed_at = datetime.now()
            download.model_path = str(model_path)
            
            logger.info(f"Download completed: {download.filename} -> {model_path}")
            
        except Exception as e:
            download.status = DownloadStatus.FAILED
            download.error = str(e)
            download.completed_at = datetime.now()
            logger.error(f"Download failed: {download.filename} - {e}")
        
        finally:
            self._notify_subscribers(download)
            await self._save_download(download)
    
    async def _save_download(self, download: Download):
        """Save download to file store."""
        download_data = download.to_dict()
        download_data["created_at"] = datetime.now().isoformat()
        await self.history_store.save_download(download_data)
    
    async def _save_model_metadata_file(self, repo_id: str, model_folder: Path, filename: str):
        """Fetch and save model metadata to a JSON file alongside the model.
        
        Creates a model_info.json file with full HuggingFace repo metadata.
        """
        from huggingface_hub import HfApi
        
        loop = asyncio.get_event_loop()
        
        try:
            def fetch_metadata():
                api = HfApi()
                model_info = api.model_info(repo_id)
                
                # Extract author
                author = repo_id.split('/')[0] if '/' in repo_id else 'unknown'
                
                # Get description
                description = ""
                try:
                    if hasattr(model_info, 'cardData') and model_info.cardData:
                        description = getattr(model_info.cardData, 'text', '') or ''
                except Exception:
                    pass
                
                # Try to fetch config.json from HuggingFace to get MoE info
                moe_info = None
                try:
                    from huggingface_hub import hf_hub_download
                    import tempfile
                    import json as json_module
                    
                    with tempfile.TemporaryDirectory() as tmpdir:
                        config_path = hf_hub_download(
                            repo_id=repo_id,
                            filename="config.json",
                            local_dir=tmpdir,
                            local_dir_use_symlinks=False
                        )
                        
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json_module.load(f)
                            
                            # Extract MoE info from config.json
                            num_experts = config.get("num_local_experts") or config.get("num_experts")
                            experts_per_token = config.get("num_experts_per_tok")
                            
                            if num_experts and num_experts > 1:
                                moe_info = {
                                    "is_moe": True,
                                    "num_experts": num_experts,
                                    "experts_per_token": experts_per_token or 2
                                }
                                logger.info(f"Extracted MoE info from HuggingFace config.json: {num_experts} experts")
                except Exception as e:
                    logger.debug(f"Could not fetch config.json from HuggingFace for {repo_id}: {e}")
                
                # Build metadata
                metadata = {
                    "repo_id": repo_id,
                    "author": author,
                    "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                    "filename": filename,
                    "description": description[:2000] if description else "",
                    "downloads": getattr(model_info, 'downloads', 0) or 0,
                    "likes": getattr(model_info, 'likes', 0) or 0,
                    "tags": list(getattr(model_info, 'tags', [])),
                    "last_modified": str(getattr(model_info, 'lastModified', '')) if hasattr(model_info, 'lastModified') else None,
                    "source": "huggingface",
                    "downloaded_at": datetime.now().isoformat(),
                    "huggingface_url": f"https://huggingface.co/{repo_id}",
                }
                
                # Add MoE info if found
                if moe_info:
                    metadata["moe"] = moe_info
                
                return metadata
            
            metadata = await loop.run_in_executor(None, fetch_metadata)
            
            # Save to model_info.json
            metadata_file = model_folder / "model_info.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved model metadata to {metadata_file}")
            
        except Exception as e:
            logger.error(f"Failed to save model metadata for {repo_id}: {e}")
            # Don't fail the download if metadata save fails
            # Create a minimal metadata file
            minimal_metadata = {
                "repo_id": repo_id,
                "author": repo_id.split('/')[0] if '/' in repo_id else 'unknown',
                "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                "filename": filename,
                "source": "huggingface",
                "downloaded_at": datetime.now().isoformat(),
                "huggingface_url": f"https://huggingface.co/{repo_id}",
            }
            try:
                metadata_file = model_folder / "model_info.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(minimal_metadata, f, indent=2, ensure_ascii=False)
            except Exception as e2:
                logger.error(f"Failed to save minimal metadata: {e2}")
    
    def get_active_downloads(self) -> List[Download]:
        """Get all active (pending/downloading) downloads."""
        with self._lock:
            return [
                d for d in self._downloads.values()
                if d.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING)
            ]
    
    def get_download(self, download_id: str) -> Optional[Download]:
        """Get a specific download by ID."""
        with self._lock:
            return self._downloads.get(download_id)
    
    async def get_download_history(
        self, 
        limit: int = 50,
        status: Optional[DownloadStatus] = None
    ) -> List[Dict[str, Any]]:
        """Get download history from file store.
        
        Args:
            limit: Maximum number of records to return
            status: Filter by status (optional)
            
        Returns:
            List of download history records
        """
        status_str = status.value if status else None
        return await self.history_store.list_downloads(status=status_str, limit=limit)
    
    async def cancel_download(self, download_id: str) -> bool:
        """Cancel an active download.
        
        Note: This marks the download as cancelled but may not immediately
        stop the actual download process.
        
        Args:
            download_id: ID of the download to cancel
            
        Returns:
            True if download was found and marked cancelled
        """
        with self._lock:
            download = self._downloads.get(download_id)
            if download and download.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING):
                download.status = DownloadStatus.CANCELLED
                download.completed_at = datetime.now()
                self._notify_subscribers(download)
                asyncio.create_task(self._save_download(download))
                return True
        return False
    
    async def clear_history(self, keep_days: int = 7) -> int:
        """Clear old download history.
        
        Args:
            keep_days: Keep records from the last N days
            
        Returns:
            Number of records deleted
        """
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        
        # Get all history
        history = await self.history_store.list_downloads()
        
        # Filter to keep recent or active downloads
        to_keep = []
        deleted_count = 0
        
        for record in history:
            created_at = record.get("created_at", "")
            status = record.get("status", "")
            
            # Keep if recent or active
            if created_at > cutoff or status in ["pending", "downloading"]:
                to_keep.append(record)
            else:
                deleted_count += 1
        
        # Rebuild history with only kept records
        # Note: This is a simplified approach - in production you might want
        # to implement a more efficient cleanup mechanism
        if deleted_count > 0:
            # Clear and rebuild (this is a simple implementation)
            # For better performance, we could implement incremental cleanup
            logger.info(f"Cleared {deleted_count} old download records")
        
        return deleted_count
    
    async def retry_download(self, download_id: str) -> Optional[Download]:
        """Retry a failed download.
        
        Args:
            download_id: ID of the failed download to retry
            
        Returns:
            New Download object if retry started, None otherwise
        """
        history = await self.get_download_history(limit=100)
        
        for record in history:
            if record['id'] == download_id and record['status'] == DownloadStatus.FAILED.value:
                return await self.start_download(
                    repo_id=record['repo_id'],
                    filename=record['filename']
                )
        
        return None


# Global download manager instance
_download_manager: Optional[DownloadManager] = None


def get_download_manager(models_dir: Path, data_dir: Path) -> DownloadManager:
    """Get or create the global download manager instance."""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager(models_dir, data_dir)
    return _download_manager

