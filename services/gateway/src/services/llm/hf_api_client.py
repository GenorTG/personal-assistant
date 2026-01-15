"""HuggingFace API client for model operations."""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from huggingface_hub import HfApi
from huggingface_hub.utils import HfHubHTTPError

logger = logging.getLogger(__name__)


class HuggingFaceAPIClient:
    """Client for interacting with HuggingFace API."""
    
    def __init__(self):
        self._api = HfApi()
    
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
                
                # Format last_modified date properly
                last_modified = None
                if hasattr(model, "lastModified") and model.lastModified:
                    try:
                        from datetime import datetime
                        # If it's a datetime object, convert to ISO string
                        if isinstance(model.lastModified, datetime):
                            last_modified = model.lastModified.isoformat()
                        # If it's already a string, use it
                        elif isinstance(model.lastModified, str):
                            last_modified = model.lastModified
                        # Otherwise try to convert to string
                        else:
                            last_modified = str(model.lastModified)
                    except Exception as e:
                        logger.debug(f"Could not format lastModified for {model_id}: {e}")
                        last_modified = None
                
                # Detect tool calling support
                from .tool_calling_detector import detect_tool_calling_from_metadata
                tags_list = list(getattr(model, "tags", []))
                # Function returns tuple (bool, Optional[str]) - extract just the boolean
                supports_tool_calling, _ = detect_tool_calling_from_metadata(
                    model_id=model_id,
                    model_name=name,
                    architecture=None,  # Not available from list_models
                    tags=tags_list,
                    repo_id=model_id,
                    remote_fetch=True
                )
                
                results.append({
                    "model_id": model_id,
                    "name": name,
                    "author": author,
                    "downloads": getattr(model, "downloads", 0),
                    "tags": tags_list,
                    "likes": getattr(model, "likes", 0),
                    "last_modified": last_modified,
                    "supports_tool_calling": supports_tool_calling,  # Now correctly a boolean
                })
            
            return results
        except (ConnectionError, OSError) as e:
            # Handle network errors gracefully
            error_msg = str(e)
            logger.error("Network error searching HuggingFace: %s", error_msg)
            if "Network is unreachable" in error_msg or "Connection" in type(e).__name__:
                raise RuntimeError(
                    "Network error: Unable to connect to HuggingFace. "
                    "Please check your internet connection and try again."
                ) from e
            raise RuntimeError(f"Network error searching models: {error_msg}") from e
        except Exception as e:
            # Check if it's a MaxRetryError or urllib3 connection error
            error_str = str(e)
            error_type = type(e).__name__
            
            if "MaxRetryError" in error_type or "NewConnectionError" in error_str or "Network is unreachable" in error_str:
                logger.error("Connection error searching HuggingFace: %s", error_str)
                raise RuntimeError(
                    "Network error: Unable to connect to HuggingFace. "
                    "Please check your internet connection and try again."
                ) from e
            
            logger.error("Unexpected error searching models: %s", error_str)
            raise RuntimeError(f"Failed to search models: {error_str}") from e
    
    async def get_repo_files(
        self,
        repo_id: str
    ) -> tuple[List[str], Dict[str, int]]:
        """Get list of GGUF files in a HuggingFace model repository with sizes.
        
        Args:
            repo_id: HuggingFace repository ID
            
        Returns:
            Tuple of (list of filenames, dict of filename -> size_bytes)
            
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
            loop = asyncio.get_event_loop()
            
            def _list_files():
                try:
                    logger.debug("Calling HfApi methods for: %s", repo_id)
                    api = HfApi()  # Create fresh instance to avoid any state issues
                    # First, get list of files
                    file_list = api.list_repo_files(repo_id, repo_type="model")
                    logger.info("Successfully retrieved %d files from %s", len(file_list) if file_list else 0, repo_id)
                    
                    # Filter to GGUF files
                    gguf_file_list = [f for f in file_list if f.endswith(".gguf")]
                    
                    # Filter out ARM-specific quantizations on non-ARM systems
                    import platform
                    machine = platform.machine().lower()
                    is_arm = machine in ('arm64', 'aarch64', 'armv8', 'armv7l')
                    
                    if not is_arm:
                        # ARM-specific quantization patterns to filter out
                        arm_quant_patterns = ['q4_0_4_4', 'q4_0_4_8', 'q4_0_8_8']
                        original_count = len(gguf_file_list)
                        gguf_file_list = [
                            f for f in gguf_file_list 
                            if not any(pattern in f.lower() for pattern in arm_quant_patterns)
                        ]
                        filtered_count = original_count - len(gguf_file_list)
                        if filtered_count > 0:
                            logger.info("Filtered out %d ARM-specific quantizations (Q4_0_4_4/Q4_0_4_8/Q4_0_8_8) from %s", 
                                       filtered_count, repo_id)
                    
                    # Get file sizes using get_paths_info
                    file_sizes = {}
                    if gguf_file_list:
                        try:
                            # Get file info including sizes
                            paths_info = api.get_paths_info(repo_id, paths=gguf_file_list, repo_type="model")
                            if paths_info:
                                logger.debug("Got paths_info for %d files", len(paths_info))
                                for path_info in paths_info:
                                    try:
                                        # Handle both dict and object responses
                                        if isinstance(path_info, dict):
                                            file_path = path_info.get("path", "") or path_info.get("name", "") or path_info.get("rfilename", "")
                                            size_bytes = path_info.get("size") or path_info.get("size_bytes") or 0
                                        else:
                                            # Try object attributes
                                            file_path = getattr(path_info, "path", None) or getattr(path_info, "name", None) or getattr(path_info, "rfilename", None) or ""
                                            size_bytes = getattr(path_info, "size", None) or getattr(path_info, "size_bytes", None) or 0
                                        
                                        if file_path:
                                            # Convert size_bytes to int if it's not already
                                            if isinstance(size_bytes, (int, float)) and size_bytes > 0:
                                                file_sizes[file_path] = int(size_bytes)
                                                logger.debug("Found size for %s: %d bytes", file_path, int(size_bytes))
                                            else:
                                                logger.debug("No size found for %s (size_bytes=%s)", file_path, size_bytes)
                                    except Exception as parse_err:
                                        logger.debug("Error parsing path_info: %s", str(parse_err))
                                        continue
                        except Exception as size_err:
                            logger.warning("Could not fetch file sizes via get_paths_info for %s: %s", repo_id, str(size_err))
                            import traceback
                            logger.debug("Size fetch traceback: %s", traceback.format_exc())
                            
                            # Note: File sizes may not be available for all repositories
                            # This is a limitation of the HuggingFace API in some cases
                            logger.debug("File sizes will not be available for this repository")
                            # Continue without sizes for remaining files
                    
                    return gguf_file_list, file_sizes
                except HfHubHTTPError as http_err:
                    logger.error("HfHubHTTPError in executor: %s", str(http_err))
                    # Re-raise with full context
                    raise
                except Exception as inner_e:
                    logger.error("Error in _list_files for %s: %s (type: %s)", repo_id, str(inner_e), type(inner_e).__name__)
                    import traceback
                    logger.error("Inner traceback: %s", traceback.format_exc())
                    raise
            
            file_list, file_sizes = await loop.run_in_executor(None, _list_files)
            
            if not file_list:
                raise ValueError(f"Repository '{repo_id}' not found or contains no GGUF files. Please check the repository ID.")
            
            return file_list, file_sizes
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
            logger.error("Unexpected error fetching files for %s: %s", repo_id, str(e))
            raise RuntimeError(f"Failed to fetch files for '{repo_id}': {str(e)}") from e
    
    async def get_model_details(self, repo_id: str) -> Dict[str, Any]:
        """Get detailed information about a HuggingFace model.
        
        Args:
            repo_id: HuggingFace repository ID
            
        Returns:
            Dictionary with model details
            
        Raises:
            ValueError: If repo_id is invalid or repository not found
            RuntimeError: If API call fails
        """
        from .model_metadata import detect_architecture
        
        loop = asyncio.get_event_loop()
        
        try:
            model_info = await loop.run_in_executor(
                None,
                lambda: self._api.model_info(repo_id)
            )
            
            # Extract author
            author = repo_id.split('/')[0] if '/' in repo_id else "Unknown"
            
            # Detect architecture
            architecture = detect_architecture(model_info)
            
            # Get description
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
                from datetime import datetime
                if hasattr(model_info, 'lastModified') and model_info.lastModified:
                    # If it's a datetime object, convert to ISO string
                    if isinstance(model_info.lastModified, datetime):
                        last_modified = model_info.lastModified.isoformat()
                    # If it's already a string, use it
                    elif isinstance(model_info.lastModified, str):
                        last_modified = model_info.lastModified
                    # Otherwise try to convert to string
                    else:
                        last_modified = str(model_info.lastModified)
                elif hasattr(model_info, 'last_modified') and model_info.last_modified:
                    # If it's a datetime object, convert to ISO string
                    if isinstance(model_info.last_modified, datetime):
                        last_modified = model_info.last_modified.isoformat()
                    # If it's already a string, use it
                    elif isinstance(model_info.last_modified, str):
                        last_modified = model_info.last_modified
                    # Otherwise try to convert to string
                    else:
                        last_modified = str(model_info.last_modified)
            except Exception as e:
                logger.warning("Could not extract last_modified for %s: %s", repo_id, str(e))
            
            tags = list(getattr(model_info, 'tags', []))
            
            # Detect tool calling support
            from .tool_calling_detector import detect_tool_calling_from_metadata
            # Function returns tuple (bool, Optional[str]) - extract just the boolean
            supports_tool_calling, _ = detect_tool_calling_from_metadata(
                model_id=repo_id,
                model_name=repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                architecture=architecture,
                tags=tags
            )
            
            result = {
                "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                "full_name": repo_id,
                "author": author,
                "description": description,
                "downloads": downloads,
                "last_modified": last_modified,
                "architecture": architecture,
                "tags": tags,
                "supports_tool_calling": supports_tool_calling
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

