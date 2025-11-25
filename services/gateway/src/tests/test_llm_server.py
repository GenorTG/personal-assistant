import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from backend.src.services.llm.manager import LLMManager
from backend.src.config.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_llm_server():
    manager = LLMManager()
    
    # Path to model
    model_name = "MistralRP-Noromaid-NSFW-7B-Q4_0.gguf"
    model_path = settings.models_dir / model_name
    
    if not model_path.exists():
        logger.error(f"Model not found at {model_path}")
        return
        
    logger.info(f"Testing with model: {model_path}")
    
    # Load model
    logger.info("Loading model...")
    success = await manager.load_model(
        str(model_path),
        n_ctx=2048,
        n_gpu_layers=-1 # Try GPU
    )
    
    if not success:
        logger.error("Failed to load model")
        return
        
    logger.info("Model loaded successfully!")
    
    # Generate response
    logger.info("Generating response...")
    try:
        response = await manager.generate_response(
            message="Hello, who are you?",
            history=[],
            stream=False
        )
        logger.info(f"Response: {response['response']}")
        
        # Test streaming
        logger.info("Testing streaming...")
        stream_response = await manager.generate_response(
            message="Tell me a short joke.",
            history=[],
            stream=True
        )
        
        print("Stream output: ", end="", flush=True)
        async for chunk in stream_response["stream"]:
            print(chunk, end="", flush=True)
        print("\n")
        
    except Exception as e:
        logger.error(f"Generation failed: {e}")
    finally:
        # Unload
        logger.info("Unloading model...")
        await manager.unload_model()
        logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(test_llm_server())
