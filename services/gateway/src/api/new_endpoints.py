# New API endpoints to add after line 1020 in routes.py

# Model Info and Memory Estimation Endpoints
@router.get("/api/models/{model_id}/info", response_model=ModelMetadata)
async def get_model_info(model_id: str):
    """Get detailed model metadata including architecture, parameters, context length, MoE info."""
    if not service_manager.llm_manager:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    
    # Find model file
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
    
    from pathlib import Path
    from ..services.llm.model_info import ModelInfoExtractor
    from ..services.llm.memory_calculator import memory_calculator
    
    # Find model file
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
        # Extract model info
        models_dir = service_manager.llm_manager.downloader.models_dir
        extractor = ModelInfoExtractor(models_dir)
        info = extractor.extract_info(model_path.name)
        
        # Calculate memory estimate
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
        
        # Get recommended VRAM
        recommended_vram = memory_calculator.get_recommended_vram(estimate["total_gb"])
        estimate["recommended_vram_gb"] = recommended_vram
        
        # Check if it will fit
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


# Conversation Management Endpoints
@router.post("/api/conversations/{conversation_id}/rename")
async def rename_conversation(request: ConversationRenameRequest):
    """Rename a conversation."""
    if not service_manager.chat_manager:
        raise HTTPException(status_code=503, detail="Chat service not initialized")
    
    try:
        # Update conversation name
        success = await service_manager.chat_manager.set_conversation_name(
            request.conversation_id,
            request.new_name
        )
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Conversation {request.conversation_id} not found")
        
        return {
            "status": "success",
            "conversation_id": request.conversation_id,
            "new_name": request.new_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename conversation: {str(e)}")
