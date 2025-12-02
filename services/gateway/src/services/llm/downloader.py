"""Model downloader from HuggingFace."""
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from datetime import datetime
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
                model_id = model.id
                # Extract author from model ID (format: "author/model-name")
                author = model_id.split("/")[0] if "/" in model_id else "Unknown"
                name = model_id.split("/")[-1] if "/" in model_id else model_id
                
                results.append({
                    "model_id": model_id,
                    "name": name,
                    "author": author,
                    "downloads": getattr(model, "downloads", 0),
                    "tags": list(getattr(model, "tags", [])),
                    "likes": getattr(model, "likes", 0),
                    "last_modified": str(getattr(model, "lastModified", "")) if hasattr(model, "lastModified") else None,
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
    
    async def get_model_details(
        self,
        repo_id: str
    ) -> Dict[str, Any]:
        """Get detailed information about a HuggingFace model repository.
        
        Args:
            repo_id: HuggingFace repository ID
        
        Returns:
            Dictionary with model details including name, author, description, etc.
        
        Raises:
            ValueError: If repo_id is invalid or repository not found
            RuntimeError: If API call fails
        """
        if not repo_id or not repo_id.strip():
            raise ValueError("Repository ID cannot be empty")
        
        repo_id = repo_id.strip()
        if '/' not in repo_id:
            raise ValueError(f"Invalid repository ID format: {repo_id}. Expected format: 'username/model-name'")
        
        try:
            logger.info("Fetching model details for: %s", repo_id)
            loop = asyncio.get_event_loop()
            
            def _get_model_info():
                try:
                    api = HfApi()
                    model_info = api.model_info(repo_id)
                    return model_info
                except Exception as e:
                    logger.error("Error fetching model info: %s", str(e))
                    raise
            
            model_info = await loop.run_in_executor(None, _get_model_info)
            
            # Extract author (first part before '/')
            author = repo_id.split('/')[0] if '/' in repo_id else "Unknown"
            
            # Detect architecture from tags or model card
            architecture = self._detect_architecture(model_info)
            
            # Get model card/description safely
            description = ""
            try:
                if hasattr(model_info, 'cardData') and model_info.cardData:
                    description = getattr(model_info.cardData, 'text', '') or ''
                elif hasattr(model_info, 'card_data') and model_info.card_data:
                    if isinstance(model_info.card_data, dict):
                        description = model_info.card_data.get('description', '') or model_info.card_data.get('text', '')
                    else:
                        description = getattr(model_info.card_data, 'text', '') or ''
                
                if not description and hasattr(model_info, 'description'):
                    description = model_info.description or ''
            except Exception as e:
                logger.warning("Could not extract description for %s: %s", repo_id, str(e))
                description = ""
            
            # Get stats
            downloads = getattr(model_info, 'downloads', 0) or 0
            last_modified = None
            try:
                if hasattr(model_info, 'lastModified'):
                    last_modified = str(model_info.lastModified) if model_info.lastModified else None
                elif hasattr(model_info, 'last_modified'):
                    last_modified = str(model_info.last_modified) if model_info.last_modified else None
            except Exception as e:
                logger.warning("Could not extract last_modified for %s: %s", repo_id, str(e))
            
            tags = list(getattr(model_info, 'tags', []))
            
            result = {
                "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                "full_name": repo_id,
                "author": author,
                "description": description,
                "downloads": downloads,
                "last_modified": last_modified,
                "architecture": architecture,
                "tags": tags
            }
            
            logger.info("Successfully fetched details for %s", repo_id)
            return result
        except HfHubHTTPError as e:
            logger.error("HfHubHTTPError for %s: %s", repo_id, str(e))
            status_code = getattr(e, 'status_code', None)
            
            if status_code == 404:
                raise ValueError(f"Repository '{repo_id}' not found on HuggingFace.") from e
            elif status_code == 403:
                raise ValueError(f"Access denied to repository '{repo_id}'.") from e
            else:
                raise ValueError(f"Failed to access repository '{repo_id}': HTTP {status_code}") from e
        except ValueError:
            raise
        except Exception as e:
            logger.error("Unexpected error fetching model details for %s: %s", repo_id, str(e))
            raise RuntimeError(f"Failed to fetch model details for '{repo_id}': {str(e)}") from e
    
    def _detect_architecture(self, model_info) -> str:
        """Detect model architecture from model info.
        
        Args:
            model_info: HuggingFace model info object
        
        Returns:
            Architecture name (e.g., "Llama 3", "Mistral", "Qwen")
        """
        tags = list(getattr(model_info, 'tags', []))
        model_id = getattr(model_info, 'id', '').lower()
        
        # Check tags first
        for tag in tags:
            tag_lower = tag.lower()
            if 'llama-3' in tag_lower or 'llama3' in tag_lower:
                return "Llama 3"
            elif 'llama-2' in tag_lower or 'llama2' in tag_lower:
                return "Llama 2"
            elif 'llama' in tag_lower:
                return "Llama"
            elif 'mistral' in tag_lower:
                return "Mistral"
            elif 'mixtral' in tag_lower:
                return "Mixtral"
            elif 'qwen2.5' in tag_lower:
                return "Qwen 2.5"
            elif 'qwen2' in tag_lower:
                return "Qwen 2"
            elif 'qwen' in tag_lower:
                return "Qwen"
            elif 'phi-3' in tag_lower or 'phi3' in tag_lower:
                return "Phi-3"
            elif 'gemma' in tag_lower:
                return "Gemma"
            elif 'yi' in tag_lower:
                return "Yi"
        
        # Check model ID if tags don't match
        if 'llama-3' in model_id or 'llama3' in model_id:
            return "Llama 3"
        elif 'llama-2' in model_id or 'llama2' in model_id:
            return "Llama 2"
        elif 'llama' in model_id:
            return "Llama"
        elif 'mistral' in model_id:
            return "Mistral"
        elif 'mixtral' in model_id:
            return "Mixtral"
        elif 'qwen2.5' in model_id or 'qwen-2.5' in model_id:
            return "Qwen 2.5"
        elif 'qwen2' in model_id or 'qwen-2' in model_id:
            return "Qwen 2"
        elif 'qwen' in model_id:
            return "Qwen"
        elif 'phi-3' in model_id or 'phi3' in model_id:
            return "Phi-3"
        elif 'gemma' in model_id:
            return "Gemma"
        elif 'yi-' in model_id or 'yi_' in model_id:
            return "Yi"
        
        return "Unknown"

    
    def list_downloaded_models(self) -> List[Path]:
        """List all downloaded GGUF models.
        
        Scans both:
        1. New folder structure: models/{author}/{repo}/file.gguf
        2. Legacy flat structure: models/file.gguf
        
        Returns:
            List of paths to downloaded model files
        """
        gguf_files = []
        
        # Scan new folder structure: models/{author}/{repo}/*.gguf
        for author_dir in self.models_dir.iterdir():
            if author_dir.is_dir():
                for repo_dir in author_dir.iterdir():
                    if repo_dir.is_dir():
                        gguf_files.extend(repo_dir.glob("*.gguf"))
        
        # Also scan flat structure for legacy/manually added models
        gguf_files.extend(self.models_dir.glob("*.gguf"))
        
        return gguf_files
    
    def get_model_info(self, model_path: Path) -> Dict[str, Any]:
        """Get information about a downloaded model.
        
        Reads metadata from model_info.json if available.
        
        Args:
            model_path: Path to model file
        
        Returns:
            Dictionary with model information including metadata
        """
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        size_bytes = model_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        size_gb = size_bytes / (1024 * 1024 * 1024)
        
        # Basic info
        info = {
            "path": str(model_path),
            "name": model_path.name,
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 2),
            "size_gb": round(size_gb, 2),
            "exists": True,
            "has_metadata": False,
        }
        
        # Try to read metadata from model_info.json in the same directory
        metadata_file = model_path.parent / "model_info.json"
        if metadata_file.exists():
            try:
                import json
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                info["has_metadata"] = True
                info["repo_id"] = metadata.get("repo_id")
                info["author"] = metadata.get("author")
                info["repo_name"] = metadata.get("name")
                info["description"] = metadata.get("description", "")[:500]
                info["downloads"] = metadata.get("downloads", 0)
                info["likes"] = metadata.get("likes", 0)
                info["tags"] = metadata.get("tags", [])
                info["huggingface_url"] = metadata.get("huggingface_url")
                info["downloaded_at"] = metadata.get("downloaded_at")
                info["source"] = metadata.get("source", "unknown")
                
            except Exception as e:
                logger.warning(f"Failed to read metadata for {model_path}: {e}")
        
        return info
    
    def get_model_folder(self, model_path: Path) -> Optional[Path]:
        """Get the model's folder (for models in author/repo structure).
        
        Args:
            model_path: Path to model file
            
        Returns:
            Path to the model folder, or None if flat structure
        """
        # Check if model is in author/repo structure
        parent = model_path.parent
        if parent != self.models_dir:
            # Check if it's author/repo/file.gguf
            grandparent = parent.parent
            if grandparent != self.models_dir and grandparent.parent == self.models_dir:
                # This is in author/repo structure
                return parent
        return None
    
    def delete_model(self, model_id: str) -> bool:
        """Delete a downloaded model and its metadata.
        
        Args:
            model_id: Model filename, path, or identifier
        
        Returns:
            True if model was deleted, False if not found
        
        Raises:
            RuntimeError: If deletion fails
        """
        # Find model file
        downloaded_models = self.list_downloaded_models()
        model_path = None
        
        for path in downloaded_models:
            # Match by filename, relative path, or full path
            relative_path = path.relative_to(self.models_dir) if path.is_relative_to(self.models_dir) else path
            if (path.name == model_id or 
                str(path) == model_id or 
                str(relative_path) == model_id):
                model_path = path
                break
        
        if not model_path:
            # Try as direct path relative to models_dir
            potential_path = self.models_dir / model_id
            if potential_path.exists() and potential_path.suffix == ".gguf":
                model_path = potential_path
            else:
                return False
        
        try:
            if model_path.exists():
                model_folder = model_path.parent
                
                # Delete the model file
                model_path.unlink()
                logger.info("Deleted model file: %s", model_path)
                
                # Delete metadata file if exists
                metadata_file = model_folder / "model_info.json"
                if metadata_file.exists():
                    metadata_file.unlink()
                    logger.info("Deleted metadata file: %s", metadata_file)
                
                # Delete folder if empty and not the root models dir
                if model_folder != self.models_dir:
                    try:
                        # Check if folder is empty (no files, only maybe empty subdirs)
                        remaining_files = list(model_folder.glob("*"))
                        if not remaining_files:
                            model_folder.rmdir()
                            logger.info("Deleted empty folder: %s", model_folder)
                            
                            # Also try to delete parent (author folder) if empty
                            author_folder = model_folder.parent
                            if author_folder != self.models_dir:
                                remaining = list(author_folder.glob("*"))
                                if not remaining:
                                    author_folder.rmdir()
                                    logger.info("Deleted empty author folder: %s", author_folder)
                    except OSError:
                        pass  # Folder not empty or other issue, ignore
                
                return True
            return False
        except Exception as e:
            logger.error("Failed to delete model %s: %s", model_path, e)
            raise RuntimeError(f"Failed to delete model: {str(e)}") from e
    
    async def link_and_organize_model(
        self,
        model_id: str,
        repo_id: str,
        target_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Link a model to a HuggingFace repo and move it to the correct folder.
        
        This is used to "fix" manually downloaded models by:
        1. Finding the model file
        2. Creating the correct folder structure (author/repo/)
        3. Moving the model file
        4. Fetching and saving metadata from HuggingFace
        
        Args:
            model_id: Current model path/identifier
            repo_id: HuggingFace repository ID (e.g., "TheBloke/Mistral-7B-GGUF")
            target_filename: Optional new filename (if different from source repo)
            
        Returns:
            Dict with new path and metadata
        """
        from huggingface_hub import HfApi
        import shutil
        
        # Find the model file
        model_path = None
        for path in self.list_downloaded_models():
            relative_path = path.relative_to(self.models_dir) if path.is_relative_to(self.models_dir) else path
            if (path.name == model_id or 
                str(path) == model_id or 
                str(relative_path) == model_id):
                model_path = path
                break
        
        if not model_path:
            potential_path = self.models_dir / model_id
            if potential_path.exists():
                model_path = potential_path
            else:
                raise FileNotFoundError(f"Model not found: {model_id}")
        
        # Parse repo_id
        if '/' not in repo_id:
            raise ValueError(f"Invalid repo_id format: {repo_id}. Expected: author/model-name")
        
        author, repo_name = repo_id.split('/', 1)
        
        # Create target folder
        target_folder = self.models_dir / author / repo_name
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # Determine target filename
        new_filename = target_filename or model_path.name
        target_path = target_folder / new_filename
        
        # Move the file if not already in the right place
        if model_path != target_path:
            if target_path.exists():
                raise FileExistsError(f"Target file already exists: {target_path}")
            
            shutil.move(str(model_path), str(target_path))
            logger.info("Moved model: %s -> %s", model_path, target_path)
            
            # Clean up old folder if empty
            old_folder = model_path.parent
            if old_folder != self.models_dir:
                try:
                    if not list(old_folder.glob("*")):
                        old_folder.rmdir()
                        # Try parent too
                        if old_folder.parent != self.models_dir:
                            if not list(old_folder.parent.glob("*")):
                                old_folder.parent.rmdir()
                except OSError:
                    pass
        
        # Fetch metadata from HuggingFace
        loop = asyncio.get_event_loop()
        
        def fetch_metadata():
            api = HfApi()
            try:
                model_info = api.model_info(repo_id)
                
                description = ""
                try:
                    if hasattr(model_info, 'cardData') and model_info.cardData:
                        description = getattr(model_info.cardData, 'text', '') or ''
                except Exception:
                    pass
                
                return {
                    "repo_id": repo_id,
                    "author": author,
                    "name": repo_name,
                    "filename": new_filename,
                    "description": description[:2000] if description else "",
                    "downloads": getattr(model_info, 'downloads', 0) or 0,
                    "likes": getattr(model_info, 'likes', 0) or 0,
                    "tags": list(getattr(model_info, 'tags', [])),
                    "last_modified": str(getattr(model_info, 'lastModified', '')) if hasattr(model_info, 'lastModified') else None,
                    "source": "huggingface",
                    "organized_at": datetime.now().isoformat(),
                    "huggingface_url": f"https://huggingface.co/{repo_id}",
                }
            except Exception as e:
                logger.warning(f"Could not fetch full metadata for {repo_id}: {e}")
                return {
                    "repo_id": repo_id,
                    "author": author,
                    "name": repo_name,
                    "filename": new_filename,
                    "source": "huggingface",
                    "organized_at": datetime.now().isoformat(),
                    "huggingface_url": f"https://huggingface.co/{repo_id}",
                }
        
        metadata = await loop.run_in_executor(None, fetch_metadata)
        
        # Save metadata
        metadata_file = target_folder / "model_info.json"
        import json
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info("Saved metadata for organized model: %s", target_path)
        
        # Return info about the new location
        relative_path = target_path.relative_to(self.models_dir)
        return {
            "old_path": str(model_path),
            "new_path": str(target_path),
            "model_id": str(relative_path),
            "metadata": metadata
        }
