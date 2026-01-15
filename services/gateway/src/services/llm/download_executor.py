"""Download execution logic with progress monitoring."""

import asyncio
import logging
import os
import time
import threading
from pathlib import Path
from typing import Callable
from huggingface_hub import hf_hub_download, HfApi
from .download_models import Download, DownloadStatus

logger = logging.getLogger(__name__)


def execute_download(
    download: Download,
    model_folder: Path,
    on_progress: Callable[[Download], None]
) -> Path:
    """Execute the actual download with progress monitoring.
    
    Args:
        download: Download object to track
        model_folder: Folder to save the model
        on_progress: Callback for progress updates
        
    Returns:
        Path to downloaded file
    """
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
        logger.info(f"[DOWNLOAD PROGRESS] Initialized download {download.id}: total_bytes={expected_size}, filename={download.filename}")
    else:
        logger.warning(f"[DOWNLOAD PROGRESS] Could not determine file size for {download.filename}, will monitor file size directly")
    
    # Start download in a separate thread with file monitoring
    download_path = None
    download_error = None
    
    def monitor_progress():
        """Monitor file size during download."""
        target_file = None
        last_size = 0
        last_time = time.time()
        check_count = 0
        # Track speed over multiple samples for better accuracy
        speed_samples = []
        max_samples = 5
        
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
                        
                        # Calculate speed - use moving average for stability
                        if elapsed > 0.05 and current_size > last_size:  # Reduced threshold to 0.05s
                            bytes_diff = current_size - last_size
                            instant_speed = bytes_diff / elapsed
                            
                            # Add to samples for moving average
                            speed_samples.append(instant_speed)
                            if len(speed_samples) > max_samples:
                                speed_samples.pop(0)
                            
                            # Calculate average speed
                            avg_speed = sum(speed_samples) / len(speed_samples)
                            download.speed_bps = avg_speed
                            
                            last_time = now
                            last_size = current_size
                            
                            # Log progress update
                            speed_mbps = download.speed_bps / 1024 / 1024
                            logger.info(f"[DOWNLOAD PROGRESS] {download.id}: {current_size}/{expected_size} bytes ({download.progress:.1f}%), speed={speed_mbps:.2f} MB/s")
                            
                            # Notify progress
                            on_progress(download)
                        elif current_size != last_size:
                            # Size changed but not enough time elapsed - still update progress
                            # Keep existing speed if available, don't reset to 0
                            if download.speed_bps == 0 and len(speed_samples) > 0:
                                # Use last known speed if available
                                download.speed_bps = speed_samples[-1]
                            last_size = current_size
                            logger.debug(f"[DOWNLOAD PROGRESS] {download.id}: Size changed to {current_size} bytes but elapsed time too small ({elapsed:.2f}s), keeping speed={download.speed_bps/1024/1024:.2f} MB/s")
                            on_progress(download)
                        elif check_count % 20 == 0:
                            # Log periodic status even if no change - keep existing speed
                            logger.debug(f"[DOWNLOAD PROGRESS] {download.id}: Monitoring - {current_size}/{expected_size} bytes, speed={download.speed_bps/1024/1024:.2f} MB/s")
                            # Still notify to keep progress fresh
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
            logger.info(f"[DOWNLOAD PROGRESS] {download.id}: Download complete - {final_size} bytes, 100%")
            on_progress(download)
        
        return Path(path)
    except Exception as e:
        download_error = e
        raise
    finally:
        # Wait a bit for final progress update
        time.sleep(0.5)

