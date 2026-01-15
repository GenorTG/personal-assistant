#!/usr/bin/env python3
"""Download a baseline tool calling model for testing.

Downloads Llama 3.1 8B Instruct, which is known to have excellent
tool calling support with llama-cpp-python.
"""
import asyncio
import sys
import logging
from pathlib import Path

# Set up path for imports
gateway_dir = Path(__file__).parent.resolve()
if str(gateway_dir) not in sys.path:
    sys.path.insert(0, str(gateway_dir))

from src.services.llm.downloader import ModelDownloader
from src.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Download Llama 3.1 8B Instruct model."""
    logger.info("=" * 60)
    logger.info("DOWNLOADING TOOL CALLING MODEL")
    logger.info("=" * 60)
    
    # Qwen 2.5 1.5B Instruct - excellent tool calling support, single file
    # Using Qwen's official GGUF quantized version (Q4_K_M is a good balance)
    repo_id = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
    filename = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
    
    logger.info(f"Repository: {repo_id}")
    logger.info(f"Filename: {filename}")
    logger.info(f"Destination: {settings.models_dir}")
    logger.info("")
    
    downloader = ModelDownloader()
    
    try:
        logger.info("Starting download...")
        model_path = await downloader.download_model(
            repo_id=repo_id,
            filename=filename
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✓ DOWNLOAD COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Model saved to: {model_path}")
        logger.info("")
        logger.info("This model is known to work well with tool calling!")
        logger.info("You can now test tool calling with this model.")
        
        return model_path
        
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
