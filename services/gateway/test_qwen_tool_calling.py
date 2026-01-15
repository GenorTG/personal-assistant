#!/usr/bin/env python3
"""Test tool calling with Qwen 2.5 1.5B model.

This model is known to have excellent tool calling support with llama-cpp-python.
"""
import asyncio
import sys
import logging
from pathlib import Path

# Set up path for imports
gateway_dir = Path(__file__).parent.resolve()
if str(gateway_dir) not in sys.path:
    sys.path.insert(0, str(gateway_dir))

from src.services.service_manager import ServiceManager
from src.services.tools.builtin.time_tool import TimeTool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_tool_calling():
    """Test tool calling with Qwen 2.5 1.5B model."""
    logger.info("=" * 60)
    logger.info("TESTING TOOL CALLING WITH QWEN 2.5 1.5B")
    logger.info("=" * 60)
    
    # Initialize service manager
    service_manager = ServiceManager()
    await service_manager.initialize()
    
    # Find the Qwen model
    model_path = Path("/home/genortg/Github Personal/personal-assistant/services/data/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")
    
    if not model_path.exists():
        logger.error(f"Model not found: {model_path}")
        logger.info("Please run download_tool_calling_model.py first")
        return False
    
    logger.info(f"Found model: {model_path}")
    logger.info(f"Model size: {model_path.stat().st_size / (1024*1024):.1f} MB")
    logger.info("")
    
    # Load the model
    logger.info("Loading model...")
    llm_manager = service_manager.llm_manager
    
    try:
        success = await llm_manager.load_model(
            model_path=str(model_path),
            n_ctx=4096,
            n_gpu_layers=-1,  # Use GPU if available
            n_threads=4
        )
        
        if not success:
            logger.error("Failed to load model")
            return False
        
        logger.info("✓ Model loaded successfully")
        logger.info(f"Tool calling support: {llm_manager.supports_tool_calling}")
        logger.info("")
        
        # Test tool calling
        logger.info("=" * 60)
        logger.info("TESTING TOOL CALLING")
        logger.info("=" * 60)
        
        # Create a simple test message that should trigger tool calling
        # Qwen models need explicit instructions to use tools
        test_message = "I need to know the current time. Please call the get_current_time function to get the current time."
        
        logger.info(f"User message: {test_message}")
        logger.info("")
        
        # Get the server URL to make a direct request for debugging
        server_url = llm_manager.server_manager.get_server_url()
        
        # Make a direct request to see the raw response
        import httpx
        import json
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get tools
            tool_manager = service_manager.tool_manager
            tools = await tool_manager.list_tools()
            
            payload = {
                "model": llm_manager.current_model_name or "default",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant with access to tools."},
                    {"role": "user", "content": test_message}
                ],
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 512
            }
            
            logger.info("Making direct request to server...")
            logger.info(f"Payload tools: {len(tools)} tools")
            logger.info(f"Tool names: {[t.get('function', {}).get('name') for t in tools]}")
            logger.info("")
            
            direct_response = await client.post(
                f"{server_url}/v1/chat/completions",
                json=payload
            )
            direct_response.raise_for_status()
            raw_data = direct_response.json()
            
            logger.info("=" * 60)
            logger.info("RAW SERVER RESPONSE")
            logger.info("=" * 60)
            logger.info(json.dumps(raw_data, indent=2))
            logger.info("")
        
        response = await llm_manager.generate_response(
            message=test_message,
            history=[],
            context=None,
            tool_results=None,
            stream=False
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("PARSED RESPONSE")
        logger.info("=" * 60)
        logger.info(f"Response text: {response.get('response', '')}")
        logger.info("")
        
        tool_calls = response.get('tool_calls', [])
        if tool_calls:
            logger.info(f"✓ Tool calls detected: {len(tool_calls)}")
            for i, tool_call in enumerate(tool_calls):
                logger.info(f"  Tool call {i+1}:")
                logger.info(f"    Name: {tool_call.get('function', {}).get('name')}")
                logger.info(f"    Arguments: {tool_call.get('function', {}).get('arguments')}")
            logger.info("")
            logger.info("✓ TOOL CALLING TEST PASSED!")
            return True
        else:
            logger.warning("✗ No tool calls detected in response")
            logger.warning("This might indicate:")
            logger.warning("  1. Model needs better prompting")
            logger.warning("  2. Tool calling not properly configured")
            logger.warning("  3. Model response format needs parsing")
            return False
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
        return False
    
    finally:
        # Cleanup
        logger.info("")
        logger.info("Cleaning up...")
        await llm_manager.unload_model()
        logger.info("✓ Cleanup complete")


if __name__ == "__main__":
    success = asyncio.run(test_tool_calling())
    sys.exit(0 if success else 1)
