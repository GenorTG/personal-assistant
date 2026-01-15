"""Model metadata saving for downloads."""

import json
import logging
from pathlib import Path
from datetime import datetime
from huggingface_hub import HfApi, hf_hub_download
import tempfile

logger = logging.getLogger(__name__)


async def save_model_metadata(
    repo_id: str,
    model_folder: Path,
    filename: str,
    loop
) -> None:
    """Fetch and save model metadata to a JSON file alongside the model.
    
    Creates a model_info.json file with full HuggingFace repo metadata.
    
    Args:
        repo_id: HuggingFace repository ID
        model_folder: Folder where model is saved
        filename: Model filename
        loop: Event loop for async execution
    """
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

