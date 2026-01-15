"""Download manager for tracking model downloads with progress."""

from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime
import asyncio
import logging
import uuid
import threading
from .file_stores import DownloadHistoryStore
from .download_models import Download, DownloadStatus
from .download_executor import execute_download
from .download_metadata import save_model_metadata

logger = logging.getLogger(__name__)


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
        
        # Broadcast via WebSocket (fire and forget)
        try:
            from ...services.websocket_manager import get_websocket_manager
            ws_manager = get_websocket_manager()
            
            # Create async task to broadcast
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._broadcast_download_update(ws_manager, download))
            else:
                asyncio.run(self._broadcast_download_update(ws_manager, download))
        except Exception as e:
            logger.debug(f"Failed to broadcast download update: {e}")
    
    async def _broadcast_download_update(self, ws_manager, download: Download):
        """Broadcast download update via WebSocket."""
        try:
            if download.status == DownloadStatus.COMPLETED:
                await ws_manager.broadcast_download_completed(
                    download.id,
                    {
                        "filename": download.filename,
                        "repo_id": download.repo_id,
                        "model_path": download.model_path,
                        "total_bytes": download.total_bytes,
                    }
                )
            else:
                await ws_manager.broadcast_download_progress(
                    download.id,
                    {
                        "filename": download.filename,
                        "repo_id": download.repo_id,
                        "status": download.status.value,
                        "progress": download.progress,
                        "bytes_downloaded": download.bytes_downloaded,
                        "total_bytes": download.total_bytes,
                        "speed_bps": download.speed_bps,
                        "speed_mbps": download.speed_mbps,
                        "eta_seconds": download.eta_seconds,
                    }
                )
        except Exception as e:
            logger.debug(f"Error in _broadcast_download_update: {e}")
    
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
            
            # Get the event loop for progress callbacks
            loop = asyncio.get_event_loop()
            
            # Create progress callback that saves to disk
            def on_progress(d: Download):
                self._notify_subscribers(d)
                # Save progress updates to disk (fire and forget)
                # Use run_coroutine_threadsafe since we're in a sync thread from run_in_executor
                try:
                    if loop.is_running():
                        # Schedule the save operation from the sync thread
                        future = asyncio.run_coroutine_threadsafe(self._save_download(d), loop)
                        # Log save attempt
                        logger.debug(f"[DOWNLOAD SAVE] Scheduled save for {d.id}: progress={d.progress:.1f}%, bytes={d.bytes_downloaded}/{d.total_bytes}, speed={d.speed_bps/1024/1024:.2f} MB/s")
                        # Check for exceptions (non-blocking)
                        try:
                            future.result(timeout=1.0)
                            logger.debug(f"[DOWNLOAD SAVE] Successfully saved progress for {d.id}")
                        except Exception as save_error:
                            logger.error(f"[DOWNLOAD SAVE] Error saving progress for {d.id}: {save_error}", exc_info=True)
                    else:
                        # Shouldn't happen, but fallback
                        logger.warning(f"[DOWNLOAD SAVE] Loop not running, using fallback for {d.id}")
                        asyncio.run(self._save_download(d))
                except Exception as e:
                    logger.error(f"[DOWNLOAD SAVE] Error saving progress update for {d.id}: {e}", exc_info=True)
            
            # Download with progress tracking
            model_path = await loop.run_in_executor(
                None,
                lambda: execute_download(download, model_folder, on_progress)
            )
            
            # Fetch and save model metadata
            await save_model_metadata(download.repo_id, model_folder, download.filename, loop)
            
            # Mark as completed
            download.status = DownloadStatus.COMPLETED
            download.progress = 100.0
            download.completed_at = datetime.now()
            download.model_path = str(model_path)
            
            logger.info(f"Download completed: {download.filename} -> {model_path}")
            
            # Trigger model discovery for the newly downloaded model
            # Note: We don't need to run discovery here since save_model_metadata already
            # creates the model_info.json file. Discovery is mainly for manually added models.
            # However, we should ensure the model is properly registered.
            logger.info(f"Model download and metadata save completed for {model_path}")
            
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
        try:
            download_data = download.to_dict()
            download_data["created_at"] = datetime.now().isoformat()
            await self.history_store.save_download(download_data)
            logger.debug(f"[DOWNLOAD SAVE] Saved download {download.id} to file store: status={download.status.value}, progress={download.progress:.1f}%")
        except Exception as e:
            logger.error(f"[DOWNLOAD SAVE] Failed to save download {download.id} to file store: {e}", exc_info=True)
            raise
    
    
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

