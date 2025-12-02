"""Model discovery service for manually added GGUF files.

Discovers GGUF models added manually to data/models/, extracts metadata,
and attempts to find the corresponding HuggingFace repository.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import re
import logging
import json
from datetime import datetime
from huggingface_hub import HfApi
from .model_info import ModelInfoExtractor

logger = logging.getLogger(__name__)


class ModelDiscovery:
    """Discovers and catalogs GGUF models in the models directory."""
    
    # Common model name patterns to search variations
    NAME_PATTERNS = [
        # Direct name match
        lambda name: name,
        # Remove quantization suffix
        lambda name: re.sub(r'[-_](Q\d+[_K]*[MSL]*|F16|F32|BF16|IQ\d+[_XSML]*).*$', '', name, flags=re.IGNORECASE),
        # Remove .gguf extension
        lambda name: name.replace('.gguf', ''),
        # Split by common delimiters and take first parts
        lambda name: '-'.join(name.split('-')[:4]),
        lambda name: '-'.join(name.split('-')[:3]),
        lambda name: '-'.join(name.split('-')[:2]),
    ]
    
    # Known repo mappings for common model patterns
    # IMPORTANT: More specific patterns should come FIRST (checked in order)
    # All repos should point to GGUF versions, not safetensors originals
    KNOWN_REPOS = [
        # Specific combined patterns first
        ('mistralrp-noromaid', 'TheBloke/MistralRP-Noromaid-7B-GGUF'),
        ('mistralrp_noromaid', 'TheBloke/MistralRP-Noromaid-7B-GGUF'),
        ('mistral-rp-noromaid', 'TheBloke/MistralRP-Noromaid-7B-GGUF'),
        ('mistralrp', 'TheBloke/MistralRP-Noromaid-7B-GGUF'),
        ('mistral-rp', 'TheBloke/MistralRP-Noromaid-7B-GGUF'),
        ('noromaid-7b', 'TheBloke/Noromaid-7B-v0.2-GGUF'),  # GGUF version
        ('noromaid', 'TheBloke/Noromaid-7B-v0.2-GGUF'),  # GGUF version, not safetensors
        # Llama variants
        ('llama-3.2', 'bartowski/Llama-3.2-3B-Instruct-GGUF'),
        ('llama-3.1', 'bartowski/Meta-Llama-3.1-8B-Instruct-GGUF'),
        ('llama-3', 'bartowski/Meta-Llama-3-8B-Instruct-GGUF'),
        ('llama3', 'bartowski/Meta-Llama-3-8B-Instruct-GGUF'),
        ('llama-2', 'TheBloke/Llama-2-7B-GGUF'),
        ('llama2', 'TheBloke/Llama-2-7B-GGUF'),
        # Other models
        ('mixtral', 'TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF'),
        ('mistral-7b', 'TheBloke/Mistral-7B-Instruct-v0.2-GGUF'),
        ('mistral', 'TheBloke/Mistral-7B-Instruct-v0.2-GGUF'),
        ('qwen2.5', 'bartowski/Qwen2.5-7B-Instruct-GGUF'),
        ('qwen2', 'bartowski/Qwen2-7B-Instruct-GGUF'),
        ('qwen', 'bartowski/Qwen2-7B-Instruct-GGUF'),
        ('phi-3', 'bartowski/Phi-3-medium-128k-instruct-GGUF'),
        ('phi3', 'bartowski/Phi-3-medium-128k-instruct-GGUF'),
        ('gemma-2', 'bartowski/gemma-2-9b-it-GGUF'),
        ('gemma', 'bartowski/gemma-7b-it-GGUF'),
        ('yi-', 'TheBloke/Yi-34B-Chat-GGUF'),
        ('deepseek', 'bartowski/DeepSeek-Coder-V2-Lite-Instruct-GGUF'),
        ('codellama', 'TheBloke/CodeLlama-7B-Instruct-GGUF'),
    ]
    
    def __init__(self, models_dir: Path, data_dir: Path):
        self.models_dir = Path(models_dir)
        self.data_dir = Path(data_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._api = HfApi()
        self.metadata_store = ModelMetadataStore(models_dir)
        self.info_extractor = ModelInfoExtractor(models_dir)
    
    def scan_models_directory(self) -> List[Path]:
        """Scan the models directory for GGUF files.
        
        Returns:
            List of paths to GGUF files found
        """
        gguf_files = list(self.models_dir.glob("*.gguf"))
        logger.info(f"Found {len(gguf_files)} GGUF files in {self.models_dir}")
        return gguf_files
    
    async def discover_all(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Discover all GGUF models and update metadata files.
        
        Args:
            force_refresh: If True, re-discover even already cataloged models
            
        Returns:
            List of discovered model metadata
        """
        gguf_files = self.scan_models_directory()
        results = []
        
        for model_path in gguf_files:
            try:
                # Check if already has metadata file
                existing = await self.metadata_store.get_metadata(model_path)
                
                if existing and not force_refresh:
                    logger.debug(f"Model {model_path.name} already cataloged, skipping")
                    results.append(existing)
                    continue
                
                # Discover model
                metadata = await self.discover_model(model_path)
                results.append(metadata)
                
            except Exception as e:
                logger.error(f"Error discovering model {model_path.name}: {e}")
                # Still add basic info even if discovery fails
                basic_info = {
                    "model_id": model_path.name,
                    "filename": model_path.name,
                    "file_size_bytes": model_path.stat().st_size if model_path.exists() else 0,
                    "source": "manual",
                    "discovered_at": datetime.now().isoformat(),
                    "error": str(e)
                }
                await self.metadata_store.save_metadata(model_path, basic_info)
                results.append(basic_info)
        
        return results
    
    async def discover_model(self, model_path: Path) -> Dict[str, Any]:
        """Discover a single GGUF model and find its HuggingFace repo.
        
        Args:
            model_path: Path to the GGUF file
            
        Returns:
            Model metadata dictionary
        """
        await self._initialize_db()
        
        filename = model_path.name
        logger.info(f"Discovering model: {filename}")
        
        # Step 1: Extract GGUF metadata
        local_info = self.info_extractor.extract_info(filename)
        
        # Step 2: Try to find HuggingFace repo
        repo_info = await self._find_huggingface_repo(filename, local_info)
        
        # Step 3: Build full metadata
        metadata = {
            "model_id": filename,
            "filename": filename,
            "repo_id": repo_info.get("repo_id") if repo_info else None,
            "repo_name": repo_info.get("name") if repo_info else None,
            "author": repo_info.get("author") if repo_info else None,
            "description": repo_info.get("description", "")[:500] if repo_info else None,
            "architecture": local_info.get("architecture", "Unknown"),
            "parameters": local_info.get("parameters"),
            "quantization": local_info.get("quantization"),
            "file_size_bytes": model_path.stat().st_size if model_path.exists() else 0,
            "context_length": local_info.get("context", {}).get("max_length", 2048),
            "is_moe": local_info.get("moe", {}).get("is_moe", False),
            "num_experts": local_info.get("moe", {}).get("num_experts"),
            "source": "manual",
            "discovered_at": datetime.now().isoformat(),
            "last_verified": datetime.now().isoformat(),
            "hf_downloads": repo_info.get("downloads", 0) if repo_info else 0,
            "tags": json.dumps(repo_info.get("tags", [])) if repo_info else "[]",
            "extra_metadata": json.dumps({
                "num_layers": local_info.get("num_layers"),
                "hidden_size": local_info.get("hidden_size"),
                "num_parameters": local_info.get("num_parameters"),
            })
        }
        
        # Step 4: Save to file next to model
        await self._save_model_metadata(metadata)
        
        logger.info(f"Discovered model {filename} -> repo: {metadata.get('repo_id', 'Unknown')}")
        
        return metadata
    
    async def _find_huggingface_repo(
        self, 
        filename: str, 
        local_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Try to find the HuggingFace repository for a GGUF file.
        
        Uses multiple strategies:
        1. Check known repo mappings
        2. Search by filename patterns
        3. Search by architecture + parameter count
        
        Args:
            filename: GGUF filename
            local_info: Extracted local GGUF metadata
            
        Returns:
            Repository info dictionary or None if not found
        """
        loop = asyncio.get_event_loop()
        
        # Clean up filename for searching
        base_name = filename.replace('.gguf', '')
        
        # Strategy 1: Check known repo mappings (list of tuples, checked in order)
        base_name_lower = base_name.lower()
        for pattern, repo_id in self.KNOWN_REPOS:
            if pattern.lower() in base_name_lower:
                logger.info(f"Found known repo mapping: {pattern} -> {repo_id}")
                try:
                    return await self._get_repo_details(repo_id)
                except Exception as e:
                    logger.warning(f"Known repo {repo_id} not accessible: {e}")
                    # Continue to try other patterns if this one fails
        
        # Strategy 2: Search by various filename patterns
        search_terms = set()
        for pattern_fn in self.NAME_PATTERNS:
            try:
                term = pattern_fn(base_name)
                if term and len(term) >= 3:
                    search_terms.add(term.lower())
            except Exception:
                continue
        
        logger.info(f"Searching HuggingFace with terms: {search_terms}")
        
        for search_term in list(search_terms)[:5]:  # Limit to 5 searches
            try:
                # Add "gguf" to search to find GGUF repos
                results = await self._search_huggingface(f"{search_term} gguf", limit=5)
                
                if results:
                    # Find best match by comparing filename similarity
                    best_match = self._find_best_match(filename, results)
                    if best_match:
                        logger.info(f"Found matching repo: {best_match['model_id']}")
                        return await self._get_repo_details(best_match['model_id'])
                        
            except Exception as e:
                logger.warning(f"Search failed for '{search_term}': {e}")
                continue
        
        # Strategy 3: Search by architecture + parameters
        arch = local_info.get("architecture", "").lower()
        params = local_info.get("parameters", "")
        
        if arch and arch != "unknown":
            try:
                search_query = f"{arch} {params} gguf" if params else f"{arch} gguf"
                results = await self._search_huggingface(search_query, limit=10)
                
                if results:
                    best_match = self._find_best_match(filename, results)
                    if best_match:
                        return await self._get_repo_details(best_match['model_id'])
                        
            except Exception as e:
                logger.warning(f"Architecture search failed: {e}")
        
        logger.warning(f"Could not find HuggingFace repo for {filename}")
        return None
    
    def _find_best_match(
        self, 
        filename: str, 
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching repository from search results.
        
        Prioritizes GGUF repos over safetensors repos.
        
        Args:
            filename: Original GGUF filename
            candidates: List of search result dictionaries
            
        Returns:
            Best matching candidate or None
        """
        filename_lower = filename.lower().replace('.gguf', '')
        filename_parts = set(re.split(r'[-_]', filename_lower))
        
        best_score = 0
        best_match = None
        
        for candidate in candidates:
            model_id = candidate.get("model_id", "").lower()
            repo_name = candidate.get("name", "").lower()
            repo_parts = set(re.split(r'[-_/]', repo_name))
            tags = [t.lower() for t in candidate.get("tags", [])]
            
            # Calculate similarity score
            common_parts = filename_parts & repo_parts
            score = len(common_parts)
            
            # STRONG bonus for GGUF repos (this is critical!)
            if "gguf" in model_id or "gguf" in repo_name or "gguf" in tags:
                score += 20  # Very high bonus for GGUF repos
            
            # Penalty for non-GGUF repos (safetensors, pytorch, etc.)
            if any(term in model_id for term in ["safetensors", "pytorch", "transformers"]):
                if "gguf" not in model_id:
                    score -= 10  # Penalty for non-GGUF
            
            # Bonus for known GGUF providers
            if "thebloke" in model_id:
                score += 10  # TheBloke is THE GGUF provider
            if "bartowski" in model_id:
                score += 8
            if "mradermacher" in model_id:
                score += 6
            if "unsloth" in model_id:
                score += 5
            
            # Bonus for key name matches
            key_terms = ["noromaid", "mistral", "llama", "qwen", "phi", "gemma", "yi"]
            for key in key_terms:
                if key in repo_name and key in filename_lower:
                    score += 5
            
            if score > best_score:
                best_score = score
                best_match = candidate
                logger.debug(f"New best match: {model_id} with score {score}")
        
        # Only return if we have a reasonable match with GGUF bonus
        if best_score >= 15:  # Require GGUF bonus (20) minus some leeway
            return best_match
        
        return None
    
    async def _search_huggingface(
        self, 
        query: str, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search HuggingFace for models.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of model info dictionaries
        """
        loop = asyncio.get_event_loop()
        
        try:
            models = await loop.run_in_executor(
                None,
                lambda: list(self._api.list_models(
                    search=query,
                    filter="gguf",
                    sort="downloads",
                    direction=-1,
                    limit=limit
                ))
            )
            
            results = []
            for model in models:
                results.append({
                    "model_id": model.id,
                    "name": model.id.split("/")[-1] if "/" in model.id else model.id,
                    "downloads": getattr(model, "downloads", 0),
                    "tags": list(getattr(model, "tags", []))
                })
            
            return results
            
        except Exception as e:
            logger.error(f"HuggingFace search failed: {e}")
            return []
    
    async def _get_repo_details(self, repo_id: str) -> Dict[str, Any]:
        """Get detailed information about a HuggingFace repository.
        
        Args:
            repo_id: Full repository ID (e.g., "TheBloke/Model-GGUF")
            
        Returns:
            Repository details dictionary
        """
        loop = asyncio.get_event_loop()
        
        try:
            model_info = await loop.run_in_executor(
                None,
                lambda: self._api.model_info(repo_id)
            )
            
            author = repo_id.split('/')[0] if '/' in repo_id else "Unknown"
            
            # Try to get description
            description = ""
            try:
                if hasattr(model_info, 'cardData') and model_info.cardData:
                    description = getattr(model_info.cardData, 'text', '') or ''
            except Exception:
                pass
            
            return {
                "repo_id": repo_id,
                "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                "author": author,
                "description": description,
                "downloads": getattr(model_info, 'downloads', 0) or 0,
                "tags": list(getattr(model_info, 'tags', []))
            }
            
        except Exception as e:
            logger.error(f"Failed to get repo details for {repo_id}: {e}")
            return {
                "repo_id": repo_id,
                "name": repo_id.split('/')[-1] if '/' in repo_id else repo_id,
                "author": repo_id.split('/')[0] if '/' in repo_id else "Unknown",
            }
    
    async def _save_model_metadata(self, metadata: Dict[str, Any]):
        """Save model metadata to file next to model.
        
        Args:
            metadata: Model metadata dictionary
        """
        filename = metadata.get("filename")
        if not filename:
            logger.error("Cannot save metadata: missing filename")
            return
        
        # Find model file
        model_path = self.models_dir / filename
        if not model_path.exists():
            # Try searching in subdirectories
            found = list(self.models_dir.rglob(filename))
            if found:
                model_path = found[0]
            else:
                logger.error(f"Model file not found: {filename}")
                return
        
        await self.metadata_store.save_metadata(model_path, metadata)
    
    async def get_model_metadata(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get stored metadata for a model.
        
        Args:
            model_id: Model filename/ID
            
        Returns:
            Metadata dictionary or None if not found
        """
        return await self.metadata_store.find_metadata_by_filename(model_id)
    
    async def get_all_metadata(self) -> List[Dict[str, Any]]:
        """Get metadata for all discovered models.
        
        Returns:
            List of model metadata dictionaries
        """
        return await self.metadata_store.list_all_metadata()
    
    async def update_model_repo(
        self, 
        model_id: str, 
        repo_id: str
    ) -> Dict[str, Any]:
        """Manually set/update the HuggingFace repo for a model.
        
        Args:
            model_id: Model filename/ID
            repo_id: HuggingFace repository ID
            
        Returns:
            Updated metadata dictionary
        """
        # Get repo details
        repo_info = await self._get_repo_details(repo_id)
        
        # Get existing metadata
        existing = await self.get_model_metadata(model_id)
        if not existing:
            # Find model file
            found = list(self.models_dir.rglob(model_id))
            if not found:
                raise ValueError(f"Model not found: {model_id}")
            model_path = found[0]
            existing = {"model_id": model_id, "filename": model_id}
        else:
            model_path = self.models_dir / existing.get("filename", model_id)
        
        # Update metadata
        existing.update({
            "repo_id": repo_info.get("repo_id"),
            "repo_name": repo_info.get("name"),
            "author": repo_info.get("author"),
            "description": repo_info.get("description", "")[:500],
            "hf_downloads": repo_info.get("downloads", 0),
            "tags": repo_info.get("tags", []),
            "last_verified": datetime.now().isoformat(),
            "source": "manual_linked"
        })
        
        await self.metadata_store.save_metadata(model_path, existing)
        return existing
    
    async def delete_model_metadata(self, model_id: str) -> bool:
        """Delete metadata for a model (when file is deleted).
        
        Args:
            model_id: Model filename/ID
            
        Returns:
            True if deleted, False if not found
        """
        # Find model file
        found = list(self.models_dir.rglob(model_id))
        if not found:
            return False
        
        model_path = found[0]
        await self.metadata_store.delete_metadata(model_path)
        return True

