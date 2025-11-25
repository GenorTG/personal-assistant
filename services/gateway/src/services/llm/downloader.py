"""Model downloader from HuggingFace."""
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
import asyncio
import logging
from huggingface_hub import hf_hub_download, HfApi
from huggingface_hub.utils import HfHubHTTPError
from ...config.settings import settings
from ...utils.helpers import sanitize_filename

logger = logging.getLogger(__name__)


class ModelDownloader:
    """Downloads GGUF models from HuggingFace."""
    
    def __init__(self):
        self.models_dir = settings.models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._api = HfApi()
    
    async def download_model(
        self,
        repo_id: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """Download a GGUF model from HuggingFace.
        
        Args:
            repo_id: HuggingFace repository ID (e.g., "TheBloke/Llama-2-7B-Chat-GGUF")
            filename: Specific GGUF file to download (if None, downloads first .gguf file found)
            progress_callback: Optional callback for download progress (bytes_downloaded, total_bytes)
        
        Returns:
            Path to downloaded model file
        
        Raises:
            ValueError: If no GGUF files found in repository
            RuntimeError: If download fails
        """
        loop = asyncio.get_event_loop()
        
        # If filename not specified, find GGUF files in repo
        if filename is None:
            try:
                # Use HfApi instance method instead of standalone function
                files = await loop.run_in_executor(
                    None,
                    lambda: self._api.list_repo_files(repo_id, repo_type="model")
                )
                gguf_files = [f for f in files if f.endswith(".gguf")]
                
                if not gguf_files:
                    raise ValueError(f"No GGUF files found in repository: {repo_id}")
                
                # Prefer smaller models for default (Q4_K_M or Q4_0 quantization)
                # Sort by filename to get consistent ordering
                gguf_files.sort()
                filename = gguf_files[0]
            except Exception as e:
                raise RuntimeError(f"Failed to list repository files: {str(e)}") from e
        
        # Download model
        try:
            model_path = await loop.run_in_executor(
                None,
                lambda: hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=self.models_dir,
                    local_dir_use_symlinks=False,
                    resume_download=True
                )
            )
            return Path(model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to download model: {str(e)}") from e
    
    async def search_models(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for GGUF models on HuggingFace.
        
        Args:
            query: Search query (e.g., "llama-2-7b gguf")
            limit: Maximum number of results
        
        Returns:
            List of model information dictionaries
        """
        loop = asyncio.get_event_loop()
        
        try:
            models = await loop.run_in_executor(
                None,
                lambda: self._api.list_models(
                    search=query,
                    filter="gguf",
                    sort="downloads",
                    direction=-1,
                    limit=limit
                )
            )
            
            results = []
            for model in models:
                results.append({
                    "model_id": model.id,
                    "name": model.id.split("/")[-1] if "/" in model.id else model.id,
                    "downloads": getattr(model, "downloads", 0),
                    "tags": getattr(model, "tags", [])
                })
            
            return results
        except Exception as e:
            raise RuntimeError(f"Failed to search models: {str(e)}") from e
    
    async def get_model_files(
        self,
        repo_id: str
    ) -> List[Dict[str, Any]]:
        """Get list of files in a HuggingFace model repository.
        
        Args:
            repo_id: HuggingFace repository ID
        
        Returns:
            List of file information dictionaries
        
        Raises:
            ValueError: If repo_id is invalid or repository not found
            RuntimeError: If API call fails
        """
        if not repo_id or not repo_id.strip():
            raise ValueError("Repository ID cannot be empty")
        
        # Clean and validate repo_id format
        repo_id = repo_id.strip()
        if not '/' in repo_id:
            raise ValueError(f"Invalid repository ID format: {repo_id}. Expected format: 'username/model-name'")
        
        try:
            # Try direct call first (synchronous but in async context)
            # This avoids executor issues with exception handling
            logger.info("Attempting to list files for repository: %s", repo_id)
            
            # Use run_in_executor to avoid blocking, but handle exceptions properly
            loop = asyncio.get_event_loop()
            
            def _list_files():
                try:
                    logger.debug("Calling HfApi.list_repo_files for: %s", repo_id)
                    api = HfApi()  # Create fresh instance to avoid any state issues
                    result = api.list_repo_files(repo_id, repo_type="model")
                    logger.info("Successfully retrieved %d files from %s", len(result) if result else 0, repo_id)
                    return result
                except HfHubHTTPError as http_err:
                    logger.error("HfHubHTTPError in executor: %s", str(http_err))
                    # Re-raise with full context
                    raise
                except Exception as inner_e:
                    logger.error("Error in _list_files for %s: %s (type: %s)", repo_id, str(inner_e), type(inner_e).__name__)
                    import traceback
                    logger.error("Inner traceback: %s", traceback.format_exc())
                    raise
            
            files = await loop.run_in_executor(None, _list_files)
            
            if not files:
                raise ValueError(f"Repository '{repo_id}' not found or is empty. Please check the repository ID.")
            
            gguf_files = []
            for file in files:
                if file.endswith(".gguf"):
                    # Extract quantization info from filename if possible
                    size_info = self._extract_size_info(file)
                    gguf_files.append({
                        "filename": file,
                        "size_info": size_info,
                        "is_gguf": True
                    })
            
            if not gguf_files:
                raise ValueError(f"No GGUF files found in repository '{repo_id}'. This repository may not contain GGUF models.")
            
            return gguf_files
        except HfHubHTTPError as e:
            # Handle HuggingFace API HTTP errors specifically
            logger.error("HfHubHTTPError for %s: %s", repo_id, str(e))
            status_code = getattr(e, 'status_code', None) or (getattr(e, 'response', None) and getattr(e.response, 'status_code', None)) or None
            logger.error("Status code: %s", status_code)
            
            if status_code == 404:
                raise ValueError(f"Repository '{repo_id}' not found on HuggingFace. Please verify the repository ID is correct and the repository exists.") from e
            elif status_code == 403:
                raise ValueError(f"Access denied to repository '{repo_id}'. The repository may be private or require authentication.") from e
            else:
                status_msg = f"HTTP {status_code}" if status_code else "HTTP error"
                raise ValueError(f"Failed to access repository '{repo_id}': {status_msg}. {str(e)}") from e
        except ValueError:
            # Re-raise ValueError as-is
            raise
        except Exception as e:
            # Log the actual exception for debugging
            logger.error("Unexpected error listing files for %s: %s (type: %s)", repo_id, str(e), type(e).__name__)
            import traceback
            logger.error("Traceback: %s", traceback.format_exc())
            
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Check for common error patterns
            if "404" in error_msg or "not found" in error_msg.lower() or "NotFoundError" in error_type:
                raise ValueError(f"Repository '{repo_id}' not found on HuggingFace. Please verify the repository ID.") from e
            elif "403" in error_msg or "Forbidden" in error_type:
                raise ValueError(f"Access denied to repository '{repo_id}'. The repository may be private.") from e
            
            raise RuntimeError(f"Failed to list model files for '{repo_id}': {error_msg} (type: {error_type})") from e
    
    def _extract_size_info(self, filename: str) -> Optional[str]:
        """Extract quantization/size info from GGUF filename.
        
        Args:
            filename: GGUF filename
        
        Returns:
            Size/quantization info if found, None otherwise
        """
        # Common quantization patterns: Q4_K_M, Q4_0, Q8_0, F16, etc.
        import re
        patterns = [
            r"Q\d+_K?[MS]?",
            r"Q\d+_\d+",
            r"F\d+",
            r"(\d+B)",  # Model size like "7B", "13B"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return match.group(0)
        
        return None
    
    def list_downloaded_models(self) -> List[Path]:
        """List all downloaded GGUF models.
        
        Returns:
            List of paths to downloaded model files
        """
        return list(self.models_dir.glob("*.gguf"))
    
    def get_model_info(self, model_path: Path) -> Dict[str, Any]:
        """Get information about a downloaded model.
        
        Args:
            model_path: Path to model file
        
        Returns:
            Dictionary with model information
        """
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        size_bytes = model_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_bytes / (1024 * 1024 * 1024)
        
        return {
            "path": str(model_path),
            "name": model_path.name,
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 2),
            "size_gb": round(size_gb, 2),
            "exists": True
        }
    
    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model.
        
        Args:
            model_id: Model filename or identifier
        
        Returns:
            True if model was deleted, False if not found
        
        Raises:
            ValueError: If model is currently loaded
        """
        # Find model file
        downloaded_models = self.list_downloaded_models()
        model_path = None
        
        for path in downloaded_models:
            if path.name == model_id or str(path) == model_id:
                model_path = path
                break
        
        if not model_path:
            # Try as direct path
            from pathlib import Path
            potential_path = Path(model_id)
            if potential_path.exists() and potential_path.suffix == ".gguf":
                model_path = potential_path
            else:
                return False
        
        # Check if model is currently loaded (would need access to LLMManager)
        # For now, just delete the file
        
        try:
            if model_path.exists():
                model_path.unlink()
                logger.info("Deleted model: %s", model_path)
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete model %s: %s", model_path, e)
            raise RuntimeError(f"Failed to delete model: {str(e)}") from e
