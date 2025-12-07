"""Model management routes."""
import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import ModelInfo, ModelLoadOptions, ModelMetadata, MemoryEstimate
from ...services.service_manager import service_manager

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
                moe=moe_info
            ))
        except Exception as e:
            logger.warning(f"Error getting model info for {model_path.name}: {e}")
            continue
    
    return model_infos


@router.post("/api/models/{model_id}/load")
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
    
    for path in downloaded_models:
        try:
            relative_path = path.relative_to(settings.models_dir) if path.is_relative_to(settings.models_dir) else path
        except (ValueError, AttributeError):
            relative_path = path
        if (path.name == model_id or 
            str(path) == model_id or 
            str(relative_path) == model_id):
            model_path = path
            break
    
    if not model_path:
        potential_path = Path(model_id)
        if potential_path.exists() and potential_path.suffix == ".gguf":
            model_path = potential_path
        else:
            potential_path = settings.models_dir / model_id
            if potential_path.exists() and potential_path.suffix == ".gguf":
                model_path = potential_path
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model {model_id} not found. Please download it first."
                )
    
    try:
        if service_manager.llm_manager.is_model_loaded():
            await service_manager.llm_manager.unload_model()
        
        load_options: Dict[str, Any] = {}
        auto_gpu_layers = service_manager.llm_manager.loader._gpu_layers
        
        if options:
            if options.n_ctx is not None:
                load_options['n_ctx'] = options.n_ctx
            if options.n_batch is not None:
                load_options['n_batch'] = options.n_batch
            if options.n_threads is not None:
                load_options['n_threads'] = options.n_threads
            if options.n_threads_batch is not None:
                load_options['n_threads_batch'] = options.n_threads_batch
                
            if options.n_gpu_layers is not None:
                load_options['n_gpu_layers'] = options.n_gpu_layers
                logger.info("GPU layers explicitly set to: %d", options.n_gpu_layers)
            else:
                load_options['n_gpu_layers'] = auto_gpu_layers
                logger.info("GPU layers not specified, using auto-detected: %d", auto_gpu_layers)
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
                
            if options.n_experts_to_use is not None:
                load_options['n_experts_to_use'] = options.n_experts_to_use
                
            if options.offload_kqv is not None:
                logger.warning("offload_kqv is not supported by llama-cpp-python, ignoring")
        else:
            load_options['n_gpu_layers'] = auto_gpu_layers
            logger.info("No load options provided, using auto-detected GPU layers: %d", auto_gpu_layers)
        
        logger.info("=" * 60)
        logger.info("API: Loading model %s", model_id)
        logger.info("Options: %s", load_options)
        logger.info("=" * 60)
        
        absolute_model_path = Path(model_path).resolve()
        
        success = await service_manager.llm_manager.load_model(
            str(absolute_model_path),
            **load_options
        )
        
        if success:
            logger.info("API: Model %s loaded successfully", model_id)
            supports_tool_calling = service_manager.llm_manager.supports_tool_calling if service_manager.llm_manager else False
            return {
                "status": "success",
                "message": f"Model {model_id} loaded successfully",
                "model_path": str(model_path),
                "options_used": load_options,
                "supports_tool_calling": supports_tool_calling
            }
        else:
            error_msg = f"Failed to load model {model_id}"
            logger.error("API: %s", error_msg)
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Load failed: %s", e, exc_info=True)
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


@router.get("/api/models/{model_id}/info", response_model=ModelMetadata)
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
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    cached_moe_info = metadata.get("moe")
                    if cached_moe_info and cached_moe_info.get("is_moe") and cached_moe_info.get("num_experts"):
                        logger.debug(f"Using cached MoE info from model_info.json: {cached_moe_info}")
                        info = extractor.extract_info(model_name_for_extraction, use_cache=True)
                        info["moe"] = cached_moe_info
                        return ModelMetadata(**info)
            except Exception as e:
                logger.debug(f"Could not read cached MoE info from model_info.json: {e}")
        
        info = extractor.extract_info(model_name_for_extraction, use_cache=True)
        
        if info.get("moe") and info["moe"].get("is_moe") and info["moe"].get("num_experts"):
            try:
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                else:
                    metadata = {}
                
                metadata["moe"] = info["moe"]
                
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                logger.debug(f"Saved MoE info to model_info.json: {info['moe']}")
            except Exception as e:
                logger.debug(f"Could not save MoE info to model_info.json: {e}")
        
        return ModelMetadata(**info)
    except Exception as e:
        logger.error(f"Error extracting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract model info: {str(e)}")


@router.get("/api/models/{model_id}/memory-estimate", response_model=MemoryEstimate)
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


@router.get("/api/models/{model_id}/config")
async def get_model_config(model_id: str):
    """Get configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    return service_manager.llm_manager.get_model_config(model_id)


@router.put("/api/models/{model_id}/config")
async def save_model_config(model_id: str, config: ModelLoadOptions):
    """Save configuration for a specific model."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    service_manager.llm_manager.save_model_config(model_id, config.model_dump(exclude_unset=True))
    return {"status": "success"}


@router.delete("/api/models/{model_id}")
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
