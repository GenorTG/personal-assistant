"""Model download and discovery routes."""
import json
import logging
from typing import Optional
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Query, Request

from ...services.service_manager import service_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["downloads"])


@router.get("/api/models/search")
async def search_models(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results")
):
    """Search for models on HuggingFace (independent of LLM service)."""
    try:
        from ...services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        results = await downloader.search_models(
            query=query,
            limit=limit
        )
        return results
    except RuntimeError as e:
        # Network errors are already wrapped in RuntimeError with user-friendly messages
        error_msg = str(e)
        if "Network error" in error_msg or "Unable to connect" in error_msg:
            raise HTTPException(
                status_code=503,
                detail=error_msg
            ) from e
        raise HTTPException(status_code=500, detail=f"Search failed: {error_msg}") from e
    except Exception as e:
        error_msg = str(e)
        # Check for network-related errors
        if "Network is unreachable" in error_msg or "Connection" in error_msg or "MaxRetryError" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Network error: Unable to connect to HuggingFace. Please check your internet connection and try again."
            ) from e
        raise HTTPException(status_code=500, detail=f"Search failed: {error_msg}") from e


@router.get("/api/models/files")
async def get_model_files_by_query(repo_id: str = Query(..., description="HuggingFace repository ID")):
    """Get list of files in a HuggingFace model repository (independent of LLM service)."""
    # Removed verbose logging - this endpoint is called frequently
    try:
        from ...services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        
        decoded_repo_id = unquote(repo_id)
        
        if not decoded_repo_id or not decoded_repo_id.strip():
            raise HTTPException(
                status_code=400,
                detail="Repository ID cannot be empty"
            )
        
        if '/' not in decoded_repo_id:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repository ID format: '{decoded_repo_id}'. Expected format: 'username/model-name'"
            )
        
        files = await downloader.get_model_files(repo_id=decoded_repo_id)
        return files
    except HTTPException:
        raise
    except ValueError as e:
        error_msg = str(e)
        logger.warning("Invalid repository ID or not found: %s - %s", repo_id, error_msg)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg) from e
        else:
            raise HTTPException(status_code=400, detail=error_msg) from e
    except Exception as e:
        import traceback
        error_detail = f"Failed to list files for repository '{repo_id}': {str(e)}"
        logger.error("Error listing files: %s\n%s", error_detail, traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_detail) from e


@router.get("/api/models/{model_id:path}/files")
async def get_model_files_by_path(model_id: str):
    """Get list of GGUF files for a specific model repository (independent of LLM service)."""
    # Removed verbose logging - this endpoint is called frequently
    try:
        from ...services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        files = await downloader.get_model_files(model_id)
        return {"files": files}
    except ValueError as e:
        logger.error(f"ValueError getting model files for {model_id}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Exception getting model files for {model_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch model files: {str(e)}"
        ) from e


@router.get("/api/models/{model_id:path}/details")
async def get_model_details(model_id: str):
    """Get detailed information for a specific model repository (independent of LLM service)."""
    try:
        from ...services.llm.downloader import ModelDownloader
        downloader = ModelDownloader()
        details = await downloader.get_model_details(model_id)
        return details
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch model details: {str(e)}"
        ) from e


@router.post("/api/models/download")
async def download_model(
    repo_id: str = Query(..., description="HuggingFace repository ID"),
    filename: Optional[str] = Query(None, description="Specific GGUF filename to download")
):
    """Start a model download with progress tracking."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = await manager.start_download(repo_id, filename)
        
        return {
            "status": "started",
            "message": f"Download started for {filename}",
            "download_id": download.id,
            "download": download.to_dict()
        }
    except Exception as e:
        logger.error(f"Failed to start download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start download: {str(e)}") from e


@router.get("/api/downloads")
async def list_downloads():
    """Get all active downloads and recent history."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        
        # Get active downloads from memory
        active_downloads = manager.get_active_downloads()
        logger.debug(f"[API DOWNLOADS] Found {len(active_downloads)} active downloads in memory")
        for d in active_downloads:
            logger.debug(f"[API DOWNLOADS] In-memory: {d.id} - {d.filename}, progress={d.progress:.1f}%, bytes={d.bytes_downloaded}/{d.total_bytes}, speed={d.speed_bps/1024/1024:.2f} MB/s")
        
        # Also check file store for any active downloads that might have been persisted
        file_active = await manager.history_store.get_active_downloads()
        logger.debug(f"[API DOWNLOADS] Found {len(file_active)} active downloads in file store")
        
        # Merge in-memory and file-based active downloads
        # In-memory downloads take precedence as they have the latest progress
        active_dict = {d.id: d for d in active_downloads}
        logger.debug(f"[API DOWNLOADS] In-memory downloads take precedence: {len(active_dict)} downloads")
        
        for file_download in file_active:
            download_id = file_download.get("id")
            if download_id and download_id not in active_dict:
                # Only reconstruct from file if not in memory (might be from previous session)
                from ...services.llm.download_models import Download, DownloadStatus
                try:
                    # Check if this is actually still active (not completed/failed/cancelled)
                    file_status = file_download.get("status", "pending")
                    if file_status not in ["pending", "downloading"]:
                        logger.debug(f"[API DOWNLOADS] Skipping file download {download_id} - status is {file_status}")
                        continue
                    
                    download = Download(
                        id=file_download.get("id", ""),
                        repo_id=file_download.get("repo_id", ""),
                        filename=file_download.get("filename", ""),
                        status=DownloadStatus(file_status),
                        progress=file_download.get("progress", 0.0),
                        bytes_downloaded=file_download.get("bytes_downloaded", 0),
                        total_bytes=file_download.get("total_bytes", 0),
                        speed_bps=file_download.get("speed_bps", 0.0),
                        error=file_download.get("error"),
                        model_path=file_download.get("model_path"),
                    )
                    if file_download.get("started_at"):
                        download.started_at = datetime.fromisoformat(file_download["started_at"])
                    if file_download.get("completed_at"):
                        download.completed_at = datetime.fromisoformat(file_download["completed_at"])
                    active_dict[download_id] = download
                    logger.debug(f"[API DOWNLOADS] Reconstructed from file: {download_id} - {download.filename}, progress={download.progress:.1f}%")
                except Exception as e:
                    logger.debug(f"Error reconstructing download from file: {e}")
        
        active = [d.to_dict() for d in active_dict.values()]
        logger.info(f"[API DOWNLOADS] Returning {len(active)} active downloads")
        for d_dict in active:
            logger.debug(f"[API DOWNLOADS] Returning: {d_dict.get('id')} - progress={d_dict.get('progress', 0):.1f}%, bytes={d_dict.get('bytes_downloaded', 0)}/{d_dict.get('total_bytes', 0)}, speed_mbps={d_dict.get('speed_mbps', 0):.2f}, eta={d_dict.get('eta_seconds')}")
        
        history = await manager.get_download_history(limit=20)
        
        return {
            "active": active,
            "history": history,
            "active_count": len(active)
        }
    except Exception as e:
        logger.error(f"Failed to list downloads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/downloads/{download_id}")
async def get_download_status(download_id: str):
    """Get status of a specific download."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = manager.get_download(download_id)
        
        if download:
            return download.to_dict()
        
        history = await manager.get_download_history(limit=100)
        for record in history:
            if record['id'] == download_id:
                return record
        
        raise HTTPException(status_code=404, detail=f"Download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get download status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/api/downloads/{download_id}")
async def cancel_download(download_id: str):
    """Cancel an active download."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        cancelled = await manager.cancel_download(download_id)
        
        if cancelled:
            return {"status": "cancelled", "download_id": download_id}
        else:
            raise HTTPException(status_code=404, detail=f"Active download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/downloads/{download_id}/retry")
async def retry_download(download_id: str):
    """Retry a failed download."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        download = await manager.retry_download(download_id)
        
        if download:
            return {
                "status": "started",
                "message": "Download retry started",
                "download_id": download.id,
                "download": download.to_dict()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Failed download {download_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry download: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/api/downloads/history")
async def clear_download_history(keep_days: int = Query(7, description="Keep records from last N days")):
    """Clear old download history."""
    from ...services.llm.download_manager import get_download_manager
    from ...config.settings import settings
    
    try:
        manager = get_download_manager(settings.models_dir, settings.data_dir)
        deleted = await manager.clear_history(keep_days)
        
        return {
            "status": "success",
            "deleted_count": deleted,
            "kept_days": keep_days
        }
    except Exception as e:
        logger.error(f"Failed to clear history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# Model discovery endpoints
@router.post("/api/models/discover")
async def discover_models(force_refresh: bool = Query(False, description="Re-discover already cataloged models")):
    """Discover manually added GGUF models and find their HuggingFace repositories."""
    from ...services.llm.discovery import ModelDiscovery
    from ...config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        results = await discovery.discover_all(force_refresh=force_refresh)
        
        return {
            "status": "success",
            "message": f"Discovered {len(results)} models",
            "models": results
        }
    except Exception as e:
        logger.error(f"Model discovery failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}") from e


@router.post("/api/models/{model_id:path}/discover")
async def discover_single_model(model_id: str):
    """Discover/rediscover a specific model and find its HuggingFace repository."""
    from ...services.llm.discovery import ModelDiscovery
    from ...config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        metadata = await discovery.discover_model(model_path)
        
        return {
            "status": "success",
            "message": f"Discovered model: {model_id}",
            "metadata": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model discovery failed for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}") from e


@router.get("/api/models/{model_id:path}/metadata")
async def get_model_metadata(model_id: str):
    """Get discovered metadata for a model."""
    from ...services.llm.discovery import ModelDiscovery
    from ...config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        metadata = await discovery.get_model_metadata(model_id)
        
        if not metadata:
            raise HTTPException(status_code=404, detail=f"No metadata found for model: {model_id}")
        
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metadata for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}") from e


@router.put("/api/models/{model_id:path}/metadata")
async def set_model_metadata(model_id: str, request: Request):
    """Manually set or update metadata for a model."""
    from ...config.settings import settings
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            flat_path = settings.models_dir / Path(model_id).name
            if flat_path.exists():
                model_path = flat_path
            else:
                raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        model_folder = model_path.parent
        metadata_file = model_folder / "model_info.json"
        
        existing_metadata = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    existing_metadata = json.load(f)
            except Exception:
                pass
        
        new_metadata = {
            **existing_metadata,
            "filename": model_path.name,
            "name": body.get("name") or existing_metadata.get("name") or model_path.stem,
            "author": body.get("author") or existing_metadata.get("author") or "Unknown",
            "description": body.get("description") or existing_metadata.get("description") or "",
            "repo_id": body.get("repo_id") or existing_metadata.get("repo_id"),
            "huggingface_url": body.get("huggingface_url") or existing_metadata.get("huggingface_url"),
            "tags": body.get("tags") or existing_metadata.get("tags") or [],
            "source": body.get("source") or existing_metadata.get("source") or "manual",
            "updated_at": datetime.now().isoformat(),
        }
        
        if "downloaded_at" not in new_metadata:
            new_metadata["downloaded_at"] = datetime.now().isoformat()
        
        if new_metadata.get("repo_id") and not new_metadata.get("huggingface_url"):
            new_metadata["huggingface_url"] = f"https://huggingface.co/{new_metadata['repo_id']}"
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(new_metadata, f, indent=2, ensure_ascii=False)
        
        # Removed verbose logging - only log errors
        return {
            "status": "success",
            "message": f"Metadata updated for {model_id}",
            "metadata": new_metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set metadata for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set metadata: {str(e)}") from e


@router.post("/api/models/{model_id:path}/link")
async def link_and_organize_model(
    model_id: str,
    repo_id: str = Query(..., description="HuggingFace repository ID"),
    filename: Optional[str] = Query(None, description="New filename (optional)")
):
    """Link a model to a HuggingFace repo and move it to the correct folder."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    try:
        result = await service_manager.llm_manager.downloader.link_and_organize_model(
            model_id=model_id,
            repo_id=repo_id,
            target_filename=filename
        )
        
        return {
            "status": "success",
            "message": f"Model linked and organized to {result['new_path']}",
            **result
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to link model {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to link model: {str(e)}") from e


@router.put("/api/models/{model_id:path}/repo")
async def set_model_repo(model_id: str, repo_id: str = Query(..., description="HuggingFace repository ID")):
    """Manually set the HuggingFace repository for a model and fetch its metadata."""
    from ...services.llm.discovery import ModelDiscovery
    from ...config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        model_path = settings.models_dir / model_id
        
        if not model_path.exists():
            raise HTTPException(status_code=404, detail=f"Model file not found: {model_id}")
        
        existing = await discovery.get_model_metadata(model_id)
        if not existing:
            await discovery.discover_model(model_path)
        
        metadata = await discovery.update_model_repo(model_id, repo_id)
        
        return {
            "status": "success",
            "message": f"Updated repository for {model_id} to {repo_id}",
            "metadata": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set repo for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set repository: {str(e)}") from e


@router.get("/api/models/all-metadata")
async def get_all_model_metadata():
    """Get discovered metadata for all models."""
    from ...services.llm.discovery import ModelDiscovery
    from ...config.settings import settings
    
    try:
        discovery = ModelDiscovery(settings.models_dir, settings.data_dir)
        all_metadata = await discovery.get_all_metadata()
        
        return {
            "status": "success",
            "count": len(all_metadata),
            "models": all_metadata
        }
    except Exception as e:
        logger.error(f"Failed to get all metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}") from e
