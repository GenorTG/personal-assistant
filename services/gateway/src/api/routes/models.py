"""Model management routes."""
import json
import logging
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import ModelInfo, ModelLoadOptions, ModelMetadata, MemoryEstimate
from ...services.service_manager import service_manager
from ...services.llm.tool_calling_detector import detect_tool_calling_from_metadata
from ...utils.request_logger import get_request_log_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["models"])


@router.get("/api/models", response_model=List[ModelInfo])
async def list_models():
    """List available/downloaded models with metadata from model_info.json files."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_infos = []
    
    for model_path in downloaded_models:
        try:
            info = service_manager.llm_manager.downloader.get_model_info(model_path)
            
            if info.get("has_metadata") and info.get("repo_name"):
                display_name = info["repo_name"]
            else:
                display_name = info["name"]
            
            model_folder = service_manager.llm_manager.downloader.get_model_folder(model_path)
            if model_folder:
                relative_path = model_path.relative_to(service_manager.llm_manager.downloader.models_dir)
                model_id = str(relative_path)
            else:
                model_id = model_path.name
            
            moe_info = info.get("moe")
            metadata = info.get("metadata", {})
            tags = metadata.get("tags") or info.get("tags") or []
            architecture = metadata.get("architecture") or info.get("architecture")
            repo_id = metadata.get("repo_id") or info.get("repo_id")
            
            # Check for cached tool calling info first (from model_info.json or extracted)
            tool_calling_info = info.get("tool_calling") or metadata.get("tool_calling")
            if tool_calling_info and isinstance(tool_calling_info, dict):
                supports_tool_calling = tool_calling_info.get("supports_tool_calling", False)
                logger.debug(f"Using cached tool calling info for {model_id}: {supports_tool_calling}")
            else:
                # Allow manual override from saved model config
                config_override = service_manager.llm_manager.get_model_config(model_id).get("supports_tool_calling_override")
                if isinstance(config_override, bool):
                    supports_tool_calling = config_override
                else:
                    # Extract chat template from model info if available
                    chat_template = info.get("chat_template")
                    supports_tool_calling, _ = detect_tool_calling_from_metadata(
                        model_id=model_id,
                        model_name=display_name,
                        architecture=architecture,
                        tags=tags,
                        repo_id=repo_id,
                        remote_fetch=True if repo_id else False,
                        chat_template=chat_template
                    )
            
            model_infos.append(ModelInfo(
                model_id=model_id,
                name=display_name,
                size=f"{info['size_gb']} GB" if info['size_gb'] >= 1 else f"{info['size_mb']} MB",
                format="gguf",
                downloaded=True,
                repo_id=info.get("repo_id"),
                author=info.get("author"),
                description=info.get("description"),
                huggingface_url=info.get("huggingface_url"),
                downloaded_at=info.get("downloaded_at"),
                has_metadata=info.get("has_metadata", False),
                moe=moe_info,
                supports_tool_calling=supports_tool_calling
            ))
        except Exception as e:
            logger.warning(f"Error getting model info for {model_path.name}: {e}")
            continue
    
    return model_infos


@router.post("/api/models/{model_id:path}/load")
async def load_model_by_id(
    model_id: str,
    options: Optional[ModelLoadOptions] = None
):
    """Load a model for inference with optional configuration."""
    from ...config.settings import settings
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    # Normalize model_id (handle both forward and backslash, URL decoding)
    from urllib.parse import unquote
    # FastAPI should already decode, but handle both cases
    try:
        normalized_model_id = unquote(model_id).replace('\\', '/')
    except Exception:
        normalized_model_id = model_id.replace('\\', '/')
    
    # Log detailed information for debugging
    logger.info(f"=== LOAD MODEL REQUEST ===")
    logger.info(f"Raw model_id from path param: {model_id!r}")
    logger.info(f"Normalized model_id: {normalized_model_id!r}")
    logger.info(f"Models directory: {settings.models_dir}")
    logger.info(f"Found {len(downloaded_models)} downloaded models")
    
    # Log first few model paths for comparison
    for i, path in enumerate(downloaded_models[:5]):
        try:
            rel = path.relative_to(settings.models_dir) if path.is_relative_to(settings.models_dir) else path
            logger.info(f"  Model {i+1}: {str(rel)} (full: {path})")
        except Exception as e:
            logger.info(f"  Model {i+1}: {path} (error getting relative: {e})")
    
    # First, try exact match with relative paths from downloaded models
    for path in downloaded_models:
        try:
            relative_path = path.relative_to(settings.models_dir) if path.is_relative_to(settings.models_dir) else path
        except (ValueError, AttributeError):
            relative_path = path
        
        # Try multiple matching strategies
        path_str = str(path).replace('\\', '/')
        relative_str = str(relative_path).replace('\\', '/')
        relative_str_normalized = relative_str.replace('\\', '/')
        
        # Exact matches (most important - this is what list_models returns)
        if (str(relative_path) == normalized_model_id or
            relative_str == normalized_model_id or
            relative_str_normalized == normalized_model_id):
            model_path = path
            logger.info(f"✓ Matched model by exact relative path: {relative_str} == {normalized_model_id}")
            break
        
        # Path ending matches (for nested paths)
        if (path_str.endswith('/' + normalized_model_id) or
            relative_str.endswith('/' + normalized_model_id) or
            path_str.endswith(normalized_model_id) or
            relative_str.endswith(normalized_model_id)):
            model_path = path
            logger.info(f"✓ Matched model by path ending: {relative_str} ends with {normalized_model_id}")
            break
        
        # Filename-only match (fallback)
        if path.name == Path(normalized_model_id).name:
            model_path = path
            logger.info(f"✓ Matched model by filename: {path.name} == {Path(normalized_model_id).name}")
            break
    
    if not model_path:
        logger.info("No match found in downloaded_models list, trying direct path resolution...")
        # Try direct path resolution relative to models_dir
        potential_path = settings.models_dir / normalized_model_id
        logger.info(f"Checking direct path: {potential_path} (exists: {potential_path.exists()})")
        if potential_path.exists():
            if potential_path.is_file() and potential_path.suffix == ".gguf":
                model_path = potential_path
                logger.info(f"✓ Found model as file: {potential_path}")
            elif potential_path.is_dir():
                # Look for .gguf files in this directory
                gguf_files = list(potential_path.glob("*.gguf"))
                logger.info(f"Directory contains {len(gguf_files)} .gguf files")
                if gguf_files:
                    model_path = gguf_files[0]  # Use first .gguf file found
                    logger.info(f"✓ Using first .gguf file: {model_path}")
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Model {model_id} not found. Directory exists but no .gguf files found."
                    )
        
        # Try as absolute path
        if not model_path:
            potential_path = Path(normalized_model_id)
            logger.info(f"Checking absolute path: {potential_path} (exists: {potential_path.exists()})")
            if potential_path.exists() and potential_path.suffix == ".gguf":
                model_path = potential_path
                logger.info(f"✓ Found model as absolute path: {potential_path}")
        
        if not model_path:
            # Last resort: search for filename in all downloaded models
            filename = Path(normalized_model_id).name
            for path in downloaded_models:
                if path.name == filename:
                    model_path = path
                    break
            
            if not model_path:
                # Log available models for debugging
                available_ids = []
                for p in downloaded_models[:10]:
                    try:
                        rel = p.relative_to(settings.models_dir)
                        available_ids.append(str(rel))
                    except (ValueError, AttributeError):
                        available_ids.append(p.name)
                
                logger.error(f"=== MODEL NOT FOUND ===")
                logger.error(f"Requested model_id: {model_id!r}")
                logger.error(f"Normalized model_id: {normalized_model_id!r}")
                logger.error(f"Available models (first 10):")
                for aid in available_ids:
                    logger.error(f"  - {aid}")
                logger.error(f"Total available models: {len(downloaded_models)}")
                
                # Also try to see if the path exists directly
                direct_path = settings.models_dir / normalized_model_id
                logger.error(f"Direct path check: {direct_path} exists={direct_path.exists()}")
                
                raise HTTPException(
                    status_code=404,
                    detail=f"Model {model_id} not found. Available models: {available_ids[:5]}"
                )
    
    try:
        if service_manager.llm_manager.is_model_loaded():
            await service_manager.llm_manager.unload_model()
        
        load_options: Dict[str, Any] = {}
        # Detect GPU layers (loader was removed, use detection logic)
        try:
            from llama_cpp import llama_cpp
            has_cuda = hasattr(llama_cpp, 'llama_supports_gpu_offload') or hasattr(llama_cpp, 'llama_gpu_offload')
            auto_gpu_layers = -1 if has_cuda else 0
        except ImportError:
            auto_gpu_layers = 0
        
        if options:
            if options.n_ctx is not None:
                load_options['n_ctx'] = options.n_ctx
            # Treat 0 as "use model defaults" (don't pass the parameter)
            if options.n_batch is not None and options.n_batch > 0:
                load_options['n_batch'] = options.n_batch
            if options.n_threads is not None and options.n_threads > 0:
                load_options['n_threads'] = options.n_threads
            if options.n_threads_batch is not None:
                load_options['n_threads_batch'] = options.n_threads_batch
                
            if options.n_gpu_layers is not None:
                load_options['n_gpu_layers'] = options.n_gpu_layers
                logger.info("GPU layers explicitly set to: %d", options.n_gpu_layers)
            else:
                # Use auto-detected GPU layers (should be -1 for all layers if GPU available, 0 for CPU)
                load_options['n_gpu_layers'] = auto_gpu_layers
                logger.info("GPU layers not specified, using auto-detected: %d", auto_gpu_layers)
                if auto_gpu_layers == 0:
                    logger.warning("Auto-detection found 0 GPU layers (CPU mode). If you have a GPU, ensure llama-cpp-python[cuda] is installed.")
            if options.main_gpu is not None:
                load_options['main_gpu'] = options.main_gpu
            if options.tensor_split is not None:
                load_options['tensor_split'] = options.tensor_split
                
            if options.use_mmap is not None:
                load_options['use_mmap'] = options.use_mmap
            if options.use_mlock is not None:
                load_options['use_mlock'] = options.use_mlock
                
            if options.flash_attn is not None:
                load_options['flash_attn'] = options.flash_attn
            elif options.use_flash_attention is not None:
                load_options['flash_attn'] = options.use_flash_attention
                logger.warning("use_flash_attention is deprecated, use flash_attn")
                
            if options.rope_freq_base is not None:
                load_options['rope_freq_base'] = options.rope_freq_base
            if options.rope_freq_scale is not None:
                load_options['rope_freq_scale'] = options.rope_freq_scale
            if options.rope_scaling_type is not None:
                load_options['rope_scaling_type'] = options.rope_scaling_type
                
            if options.yarn_ext_factor is not None:
                load_options['yarn_ext_factor'] = options.yarn_ext_factor
            if options.yarn_attn_factor is not None:
                load_options['yarn_attn_factor'] = options.yarn_attn_factor
            if options.yarn_beta_fast is not None:
                load_options['yarn_beta_fast'] = options.yarn_beta_fast
            if options.yarn_beta_slow is not None:
                load_options['yarn_beta_slow'] = options.yarn_beta_slow
            if options.yarn_orig_ctx is not None:
                load_options['yarn_orig_ctx'] = options.yarn_orig_ctx
                
            if options.cache_type_k is not None:
                load_options['cache_type_k'] = options.cache_type_k
            if options.cache_type_v is not None:
                load_options['cache_type_v'] = options.cache_type_v
                
            if options.offload_kqv is not None:
                logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
        else:
            load_options['n_gpu_layers'] = auto_gpu_layers
            logger.info("No load options provided, using auto-detected GPU layers: %d", auto_gpu_layers)
        
        logger.info("[API] ========== STARTING MODEL LOAD ==========")
        logger.info(f"[API] Model: {model_id}")
        logger.info(f"[API] Path: {model_path}")
        logger.info(f"[API] Options: {load_options}")
        logger.info("[API] ==========================================")
        
        absolute_model_path = Path(model_path).resolve()
        load_start_time = time.time()
        
        try:
            success = await service_manager.llm_manager.load_model(
                str(absolute_model_path),
                **load_options
            )
            load_duration = time.time() - load_start_time
            
            if success:
                logger.info(f"[API] ✓ Model {model_id} loaded successfully in {load_duration:.2f}s")
                supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
                
                # Get logs if available
                log_store = get_request_log_store()
                logs = log_store.get_logs() if log_store else None
                
                # Invalidate settings cache so frontend sees the new model status immediately
                try:
                    from .settings import invalidate_settings_cache
                    invalidate_settings_cache()
                except Exception as e:
                    logger.warning("Failed to invalidate settings cache: %s", e)
                
                response = {
                    "status": "success",
                    "message": f"Model {model_id} loaded successfully",
                    "model_path": str(model_path),
                    "options_used": load_options,
                    "supports_tool_calling": supports_tool_calling
                }
                if logs:
                    response["logs"] = logs
                return response
            else:
                error_msg = f"Failed to load model {model_id} (took {load_duration:.2f}s)"
                logger.error(f"[API] ❌ {error_msg}")
                # Get last error from server manager if available
                last_error = getattr(service_manager.llm_manager.server_manager, '_last_error', None)
                if last_error:
                    logger.error(f"[API] Server error: {last_error}")
                    error_msg += f"\n{last_error}"
                raise HTTPException(
                    status_code=500,
                    detail=error_msg
                )
        except Exception as e:
            load_duration = time.time() - load_start_time if 'load_start_time' in locals() else 0
            logger.error(f"[API] ❌ Load failed after {load_duration:.2f}s: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Load failed: {str(e)}") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] ❌ Load failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Load failed: {str(e)}") from e


@router.post("/api/models/load")
async def load_model_direct(request: Dict[str, Any]):
    """Load a model by path (simplified endpoint)."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
        
    model_path = request.get("model_path")
    if not model_path:
        raise HTTPException(status_code=400, detail="model_path is required")
        
    clean_options: Dict[str, Any] = {}
    
    valid_params = [
        'n_ctx', 'n_batch', 'n_threads', 'n_threads_batch',
        'n_gpu_layers', 'main_gpu', 'tensor_split',
        'use_mmap', 'use_mlock', 'flash_attn',
        'rope_freq_base', 'rope_freq_scale', 'rope_scaling_type',
        'yarn_ext_factor', 'yarn_attn_factor', 'yarn_beta_fast', 'yarn_beta_slow', 'yarn_orig_ctx',
        'cache_type_k', 'cache_type_v'
    ]
    
    for param in valid_params:
        if param in request and request[param] is not None:
            clean_options[param] = request[param]
    
    if 'use_flash_attention' in request and 'flash_attn' not in clean_options:
        clean_options['flash_attn'] = request['use_flash_attention']
        logger.warning("use_flash_attention is deprecated, use flash_attn")
    
    if 'offload_kqv' in request:
        logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
    
    try:
        success = await service_manager.llm_manager.load_model(model_path, **clean_options)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to load model")
            
        return {"status": "success", "message": f"Loaded {model_path}", "options_used": clean_options}
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}") from e


@router.post("/api/models/unload")
async def unload_model():
    """Unload the currently loaded model."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    if not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model is currently loaded"
        )
    
    try:
        success = await service_manager.llm_manager.unload_model()
        if success:
            # Invalidate settings cache so frontend sees the model is unloaded
            try:
                from .settings import invalidate_settings_cache
                invalidate_settings_cache()
            except Exception as e:
                logger.warning("Failed to invalidate settings cache: %s", e)
            
            return {
                "status": "success",
                "message": "Model unloaded successfully"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to unload model"
            )
    except Exception as e:
        logger.error("Unload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to unload model: {str(e)}") from e


@router.post("/api/models/{model_id:path}/test")
async def test_model_generation(model_id: str):
    """Test model generation with a simple prompt to verify it works."""
    from ...config.settings import settings
    
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    # Check if this model is loaded
    if not service_manager.llm_manager.is_model_loaded():
        raise HTTPException(
            status_code=400,
            detail="No model loaded. Please load a model first."
        )
    
    # Verify it's the right model
    if service_manager.llm_manager.current_model_name != model_id:
        raise HTTPException(
            status_code=400,
            detail=f"Model {model_id} is not currently loaded. Loaded model: {service_manager.llm_manager.current_model_name}"
        )
    
    try:
        # Simple test prompt
        test_prompt = "Hello"
        test_settings = service_manager.llm_manager.sampler_settings
        
        # Generate a very short response (just 10 tokens)
        from ...services.llm.sampler import SamplerSettings
        test_sampler = SamplerSettings(
            temperature=test_settings.temperature,
            top_p=test_settings.top_p,
            top_k=test_settings.top_k,
            repeat_penalty=test_settings.repeat_penalty,
            max_tokens=10  # Very short for testing
        )
        
        # Check if model is loaded
        if not service_manager.llm_manager.is_model_loaded():
            raise HTTPException(
                status_code=500,
                detail="Model not loaded"
            )
        
        # Test generation via OpenAI-compatible server
        # Build OpenAI-compatible request
        import httpx
        server_url = service_manager.llm_manager.server_manager.get_server_url()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{server_url}/v1/chat/completions",
                json={
                    "model": service_manager.llm_manager.current_model_name or "default",
                    "messages": [{"role": "user", "content": test_prompt}],
                    "temperature": test_sampler.temperature,
                    "top_p": test_sampler.top_p,
                    "max_tokens": test_sampler.max_tokens,
                }
            )
            response.raise_for_status()
            resp_data = response.json()
            if "choices" in resp_data and len(resp_data["choices"]) > 0:
                response_text = resp_data["choices"][0].get("message", {}).get("content", "")
            else:
                response_text = "No response generated"
        
        return {
            "status": "success",
            "test_prompt": test_prompt,
            "response": response_text,
            "message": "Model generation test passed"
        }
    except Exception as e:
        logger.error("Model test failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Model test failed: {str(e)}"
        ) from e


@router.get("/api/models/{model_id:path}/info", response_model=ModelMetadata)
async def get_model_info(model_id: str):
    """Get detailed model metadata including architecture, parameters, context length, MoE info."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from ...services.llm.model_info import ModelInfoExtractor
    
    normalized_model_id = model_id.replace('\\', '/')
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        path_str = str(path).replace('\\', '/')
        path_name = path.name
        
        if (path_name == model_id or 
            path_name == normalized_model_id or
            path_str == model_id or 
            path_str == normalized_model_id or
            path_str.endswith(normalized_model_id) or
            path_str.endswith(model_id)):
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(normalized_model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            models_dir = service_manager.llm_manager.downloader.models_dir
            potential_path = models_dir / normalized_model_id
            if potential_path.exists():
                model_path = potential_path
            else:
                raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        
        try:
            relative_path = model_path.relative_to(models_dir)
            model_name_for_extraction = str(relative_path)
        except ValueError:
            if model_path.is_relative_to(models_dir.parent):
                model_name_for_extraction = str(model_path.relative_to(models_dir.parent))
            else:
                model_name_for_extraction = model_path.name
        
        metadata_file = model_path.parent / "model_info.json" if model_path.is_file() else model_path / "model_info.json"
        cached_moe_info = None
        cached_tool_calling_info = None
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    cached_moe_info = metadata.get("moe")
                    cached_tool_calling_info = metadata.get("tool_calling")
                    # Use cached data if available
                    if (cached_moe_info and cached_moe_info.get("is_moe") and cached_moe_info.get("num_experts")) or cached_tool_calling_info:
                        logger.debug(f"Using cached metadata from model_info.json")
                        info = extractor.extract_info(model_name_for_extraction, use_cache=True)
                        if cached_moe_info:
                            info["moe"] = cached_moe_info
                        if cached_tool_calling_info:
                            info["tool_calling"] = cached_tool_calling_info
                        return ModelMetadata(**info)
            except Exception as e:
                logger.debug(f"Could not read cached MoE info from model_info.json: {e}")
        
        info = extractor.extract_info(model_name_for_extraction, use_cache=True)
        
        # Save extracted metadata to model_info.json for caching
        should_save = False
        try:
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = {}
            
            # Save MoE info if extracted
            if info.get("moe") and info["moe"].get("is_moe") and info["moe"].get("num_experts"):
                metadata["moe"] = info["moe"]
                should_save = True
                logger.debug(f"Updating MoE info in model_info.json: {info['moe']}")
            
            # Save tool calling info if extracted
            if info.get("tool_calling"):
                metadata["tool_calling"] = info["tool_calling"]
                should_save = True
                logger.debug(f"Updating tool calling info in model_info.json: {info['tool_calling']}")
            
            if should_save:
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                logger.debug(f"Saved updated metadata to {metadata_file}")
        except Exception as e:
            logger.debug(f"Could not save metadata to model_info.json: {e}")
        
        return ModelMetadata(**info)
    except Exception as e:
        logger.error(f"Error extracting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract model info: {str(e)}")


@router.get("/api/models/{model_id:path}/memory-estimate", response_model=MemoryEstimate)
async def get_memory_estimate(
    model_id: str,
    context_length: int = Query(2048, ge=512, le=32768),
    batch_size: int = Query(1, ge=1, le=32)
):
    """Get memory requirement estimate for a model with given context length."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from ...services.llm.model_info import ModelInfoExtractor
    from ...services.llm.memory_calculator import memory_calculator
    
    downloaded_models = service_manager.llm_manager.downloader.list_downloaded_models()
    model_path = None
    
    for path in downloaded_models:
        if path.name == model_id or str(path) == model_id:
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists():
            model_path = potential_path
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    
    try:
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        model_params = {
            "num_parameters": info.get("num_parameters"),
            "num_layers": info.get("num_layers", 32),
            "hidden_size": info.get("hidden_size", 4096),
            "quantization": info.get("quantization"),
            "model_name": info.get("name")
        }
        
        estimate = memory_calculator.estimate_total_memory(
            model_params,
            context_length=context_length,
            batch_size=batch_size
        )
        
        recommended_vram = memory_calculator.get_recommended_vram(estimate["total_gb"])
        estimate["recommended_vram_gb"] = recommended_vram
        
        try:
            import torch
            if torch.cuda.is_available():
                available_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                estimate["will_fit"] = estimate["total_gb"] <= available_vram
            else:
                estimate["will_fit"] = None
        except:
            estimate["will_fit"] = None
        
        return MemoryEstimate(**estimate)
    except Exception as e:
        logger.error(f"Error calculating memory estimate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate memory estimate: {str(e)}")


@router.get("/api/models/{model_id:path}/config")
async def get_model_config(model_id: str):
    """Get configuration for a specific model."""
    if not service_manager.llm_manager:
        # Return empty config instead of 503 to prevent frontend errors
        return {}
    
    try:
        # Decode URL-encoded model_id (handles slashes and special characters)
        import urllib.parse
        decoded_model_id = urllib.parse.unquote(model_id)
        
        config = service_manager.llm_manager.get_model_config(decoded_model_id)
        
        # Return empty config if not found (don't 404, just return defaults)
        if not config:
            return {}
        
        return config
    except Exception as e:
        logger.warning(f"Error getting model config for {model_id}: {e}")
        # Return empty config instead of error to prevent frontend issues
        return {}


@router.put("/api/models/{model_id:path}/config")
async def save_model_config(model_id: str, config: ModelLoadOptions):
    """Save configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    try:
        # Decode URL-encoded model_id
        import urllib.parse
        decoded_model_id = urllib.parse.unquote(model_id)
        service_manager.llm_manager.save_model_config(decoded_model_id, config.model_dump(exclude_unset=True))
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving model config for {model_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save model config: {str(e)}")


@router.delete("/api/models/{model_id:path}")
async def delete_model(model_id: str):
    """Delete a downloaded model."""
    if not service_manager.llm_manager:
        raise HTTPException(
            status_code=503,
            detail="LLM service not initialized"
        )
    
    current_model_path = service_manager.llm_manager.get_current_model_path()
    if current_model_path:
        current_model_name = Path(current_model_path).name
        if current_model_name == model_id or str(current_model_path) == model_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete model '{model_id}' - it is currently loaded. Please unload it first."
            )
    
    try:
        success = service_manager.llm_manager.downloader.delete_model(model_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Model {model_id} deleted successfully"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_id} not found"
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        logger.error("Delete failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}") from e


@router.post("/api/models/install-llama-cuda")
async def install_llama_cuda():
    """Install llama-cpp-python with CUDA support."""
    from ...services.llm.cuda_installer import install_llama_cuda, check_cuda_available, check_llama_cuda_support
    
    if not check_cuda_available():
        raise HTTPException(
            status_code=400,
            detail="No CUDA GPU detected. Cannot install CUDA-enabled llama-cpp-python."
        )
    
    has_cuda, error = check_llama_cuda_support()
    if has_cuda:
        return {
            "status": "success",
            "message": "llama-cpp-python already has CUDA support",
            "cuda_available": True
        }
    
    try:
        import sys
        python_exe = sys.executable
        
        success, message = install_llama_cuda(python_exe)
        
        if success:
            return {
                "status": "success",
                "message": message,
                "cuda_available": True
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Installation failed: {message}"
            )
    except Exception as e:
        logger.error("Failed to install llama-cpp-python with CUDA: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Installation error: {str(e)}"
        ) from e
