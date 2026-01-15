"""File operations for downloaded models."""

import json
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from huggingface_hub import HfApi, hf_hub_download

logger = logging.getLogger(__name__)


def list_downloaded_models(models_dir: Path) -> List[Path]:
    """List all downloaded GGUF models.
    
    Scans recursively for GGUF files in any subdirectory structure:
    - services/data/models/ (primary location)
    - data/models/ (legacy/alternative location)
    - models/{author}/{repo}/file.gguf
    - models/{author}/{repo}/{subdir}/file.gguf (nested)
    - models/file.gguf (flat/legacy)
    
    Args:
        models_dir: Base directory for models
        
    Returns:
        List of paths to downloaded model files
    """
    gguf_files = []
    
    # Scan primary location: services/data/models/
    if models_dir.exists():
        gguf_files.extend(models_dir.glob("**/*.gguf"))
    
    # Scan legacy location: data/models/ (if different from primary)
    base_dir = models_dir.parent.parent.parent if models_dir.parent.parent.parent.exists() else None
    legacy_models_dir = base_dir / "data" / "models" if base_dir else None
    if legacy_models_dir and legacy_models_dir.exists() and legacy_models_dir != models_dir:
        gguf_files.extend(legacy_models_dir.glob("**/*.gguf"))
    
    # Remove duplicates
    gguf_files = list(set(gguf_files))
    
    # Filter out ARM-specific quantizations on non-ARM systems
    # Q4_0_4_4, Q4_0_4_8, Q4_0_8_8 are ARM NEON/i8mm/SVE optimizations
    import platform
    machine = platform.machine().lower()
    is_arm = machine in ('arm64', 'aarch64', 'armv8', 'armv7l')
    
    if not is_arm:
        arm_quant_patterns = ['q4_0_4_4', 'q4_0_4_8', 'q4_0_8_8']
        original_count = len(gguf_files)
        gguf_files = [
            f for f in gguf_files 
            if not any(pattern in f.name.lower() for pattern in arm_quant_patterns)
        ]
        filtered_count = original_count - len(gguf_files)
        if filtered_count > 0:
            logger.debug("Filtered out %d ARM-specific quantizations from downloaded models list", 
                       filtered_count)
    
    return gguf_files


def get_model_info(model_path: Path) -> Dict[str, Any]:
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
        "size_str": f"{size_gb:.2f} GB" if size_gb >= 1.0 else f"{size_mb:.2f} MB"
    }
    
    # Try to load metadata from model_info.json
    # First try model-specific file (same name as model but .json)
    model_specific_metadata = model_path.with_suffix('.json')
    metadata_file = None
    metadata = None
    
    if model_specific_metadata.exists():
        metadata_file = model_specific_metadata
    else:
        # Fall back to folder-level model_info.json
        model_folder = model_path.parent
        folder_metadata_file = model_folder / "model_info.json"
        if folder_metadata_file.exists():
            # Only use folder-level metadata if it matches this model's filename
            try:
                with open(folder_metadata_file, 'r', encoding='utf-8') as f:
                    folder_metadata = json.load(f)
                    # Check if this metadata file is for this specific model
                    if folder_metadata.get("filename") == model_path.name:
                        metadata_file = folder_metadata_file
                        metadata = folder_metadata
            except Exception:
                pass
    
    if metadata_file and metadata_file.exists():
        try:
            if metadata is None:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            
            # Only use metadata if it matches this model's filename
            if metadata.get("filename") == model_path.name or model_specific_metadata.exists():
                info["metadata"] = metadata
                info["repo_id"] = metadata.get("repo_id")
                info["author"] = metadata.get("author")
                info["description"] = metadata.get("description", "")
                # Use metadata name only if it matches this model
                if metadata.get("filename") == model_path.name:
                    info["name"] = metadata.get("name", model_path.stem)
        except Exception as e:
            logger.warning("Failed to load metadata from %s: %s", metadata_file, e)
    
    return info


def delete_model(model_path: Path, models_dir: Path) -> bool:
    """Delete a downloaded model and its metadata.
    
    Args:
        model_path: Path to model file to delete
        models_dir: Base models directory
        
    Returns:
        True if deleted successfully, False if not found
        
    Raises:
        RuntimeError: If deletion fails
    """
    try:
        if model_path.exists():
            model_path.unlink()
            logger.info("Deleted model file: %s", model_path)
            
            # Delete metadata file if it exists
            model_folder = model_path.parent
            metadata_file = model_folder / "model_info.json"
            if metadata_file.exists():
                metadata_file.unlink()
                logger.info("Deleted metadata file: %s", metadata_file)
            
            # Delete folder if empty and not the root models dir
            if model_folder != models_dir:
                try:
                    # Check if folder is empty (no files, only maybe empty subdirs)
                    remaining_files = list(model_folder.glob("*"))
                    if not remaining_files:
                        model_folder.rmdir()
                        logger.info("Deleted empty folder: %s", model_folder)
                        
                        # Also try to delete parent (author folder) if empty
                        author_folder = model_folder.parent
                        if author_folder != models_dir:
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
    model_id: str,
    repo_id: str,
    models_dir: Path,
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
        models_dir: Base models directory
        target_filename: Optional new filename (if different from source repo)
        
    Returns:
        Dict with new path and metadata
    """
    import asyncio
    
    # Find the model file
    model_path = None
    for path in list_downloaded_models(models_dir):
        relative_path = path.relative_to(models_dir) if path.is_relative_to(models_dir) else path
        if (path.name == model_id or 
            str(path) == model_id or 
            str(relative_path) == model_id):
            model_path = path
            break
    
    if not model_path:
        potential_path = models_dir / model_id
        if potential_path.exists():
            model_path = potential_path
        else:
            raise FileNotFoundError(f"Model not found: {model_id}")
    
    # Parse repo_id
    if '/' not in repo_id:
        raise ValueError(f"Invalid repo_id format: {repo_id}. Expected: author/model-name")
    
    author, repo_name = repo_id.split('/', 1)
    
    # Create target folder
    target_folder = models_dir / author / repo_name
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
        if old_folder != models_dir:
            try:
                if not list(old_folder.glob("*")):
                    old_folder.rmdir()
                    # Try parent too
                    if old_folder.parent != models_dir:
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
            
            # Try to fetch config.json from HuggingFace to get MoE info
            moe_info = None
            try:
                import tempfile
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    config_path = hf_hub_download(
                        repo_id=repo_id,
                        filename="config.json",
                        local_dir=tmpdir,
                        local_dir_use_symlinks=False
                    )
                    
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        
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
            
            metadata = {
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
            
            # Add MoE info if found
            if moe_info:
                metadata["moe"] = moe_info
            
            return metadata
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
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    logger.info("Saved metadata for organized model: %s", target_path)
    
    # Return info about the new location
    relative_path = target_path.relative_to(models_dir)
    return {
        "old_path": str(model_path),
        "new_path": str(target_path),
        "model_id": str(relative_path),
        "metadata": metadata
    }

