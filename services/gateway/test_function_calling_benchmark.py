#!/usr/bin/env python3
"""Test function calling with benchmark models.

This script tests function calling functionality with benchmark models
by sending simple, clear requests that should trigger function calls.
"""

import sys
import asyncio
from pathlib import Path
import logging
import httpx
import json

# Add gateway src to path
gateway_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(gateway_dir / "src"))
sys.path.insert(0, str(gateway_dir))

try:
    from src.services.service_manager import ServiceManager
except ImportError:
    # Try alternative import path
    import os
    os.chdir(str(gateway_dir))
    sys.path.insert(0, str(gateway_dir / "src"))
    from src.services.service_manager import ServiceManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_function_calling(model_path: str = None) -> bool:
    """Test function calling with a model.
    
    Args:
        model_path: Optional path to model file. If None, uses current loaded model.
        
    Returns:
        True if test passes, False otherwise
    """
    service_manager = ServiceManager()
    await service_manager.initialize()
    
    llm_manager = service_manager.llm_manager
    tool_manager = service_manager.tool_manager
    
    # Load model if path provided
    if model_path:
        logger.info(f"Loading model: {model_path}")
        success = await llm_manager.load_model(model_path)
        if not success:
            logger.error(f"Failed to load model: {model_path}")
            return False
        logger.info("Model loaded successfully")
    else:
        if not llm_manager.current_model_name:
            logger.error("No model loaded and no model path provided")
            return False
        logger.info(f"Using currently loaded model: {llm_manager.current_model_name}")
    
    # Check if tool calling is supported
    if not llm_manager.supports_tool_calling:
        logger.warning("Model does not support tool calling according to detection")
        logger.info("Proceeding with test anyway...")
    
    # Initialize tool manager
    await tool_manager.initialize()
    
    # Get tool definitions
    tools = await tool_manager.list_tools()
    logger.info(f"Available tools: {[t['function']['name'] for t in tools]}")
    
    # Check if benchmark tool is available
    benchmark_tool = None
    for tool in tools:
        if tool['function']['name'] == 'add_numbers':
            benchmark_tool = tool
            break
    
    if not benchmark_tool:
        logger.error("Benchmark tool 'add_numbers' not found in tool registry")
        return False
    
    logger.info("✓ Benchmark tool 'add_numbers' is available")
    
    # Use the exact system message format from official docs for chatml-function-calling
    system_message = "A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. The assistant calls functions with appropriate input when necessary"
    
    # Test messages - simple and clear requests matching official docs format
    test_cases = [
        {
            "name": "Simple addition request",
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": "Add 3 and 5 using add_numbers"
                }
            ]
        },
        {
            "name": "Direct instruction",
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": "What is 7 plus 9? Use the add_numbers function."
                }
            ]
        },
        {
            "name": "Natural language",
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": "I need to add 12 and 8 together using add_numbers"
                }
            ]
        }
    ]
    
    server_url = llm_manager.server_manager.get_server_url()
    logger.info(f"Server URL: {server_url}")
    
    passed_tests = 0
    total_tests = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Test {i}/{total_tests}: {test_case['name']}")
        logger.info(f"{'='*60}")
        # Find user message (not system message)
        user_msg = next((msg['content'] for msg in test_case['messages'] if msg['role'] == 'user'), 'N/A')
        logger.info(f"User message: {user_msg}")
        
        try:
            # Make request to server
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Format tools according to official docs - use 'title' and proper structure
                # Only include add_numbers tool (as per docs example)
                formatted_tools = [{
                    "type": "function",
                    "function": {
                        "name": "add_numbers",
                        "parameters": {
                            "type": "object",
                            "title": "add_numbers",
                            "properties": {
                                "a": {
                                    "title": "A",
                                    "type": "integer"
                                },
                                "b": {
                                    "title": "B",
                                    "type": "integer"
                                }
                            },
                            "required": ["a", "b"]
                        }
                    }
                }]
                
                # Use "test" as model name - this works in manual tests
                # The server accepts any model name when only one model is loaded
                model_name = "test"
                logger.debug(f"Using model name: {model_name}")
                
                payload = {
                    "model": model_name,
                    "messages": test_case['messages'],
                    "tools": formatted_tools,
                    # Use tool_choice to force tool calling (required for chatml-function-calling format)
                    "tool_choice": {
                        "type": "function",
                        "function": {
                            "name": "add_numbers"
                        }
                    },
                    "temperature": 0.0,  # Use 0 for deterministic testing
                    "max_tokens": 512
                }
                
                logger.debug(f"Using model name: {model_name}")
                logger.debug(f"Payload tools: {json.dumps(formatted_tools, indent=2)}")
                
                logger.debug(f"Request payload (tools count: {len(tools)}): {json.dumps(payload, indent=2)}")
                
                response = await client.post(
                    f"{server_url}/v1/chat/completions",
                    json=payload
                )
                
                # Log error details if request failed
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Server returned {response.status_code}")
                    logger.error(f"Error text: {error_text[:500]}")
                    try:
                        error_json = response.json()
                        logger.error(f"Error JSON: {json.dumps(error_json, indent=2)}")
                    except Exception as e:
                        logger.error(f"Could not parse error as JSON: {e}")
                    # Log the payload that caused the error
                    logger.error(f"Payload that caused error: {json.dumps(payload, indent=2)[:1000]}")
                    # Continue to next test to see all errors
                    continue
                
                response.raise_for_status()
                result = response.json()
                
                # Check for tool calls
                choices = result.get("choices", [])
                if not choices:
                    logger.warning(f"✗ Test {i} FAILED: No choices in response")
                    continue
                
                message = choices[0].get("message", {})
                tool_calls = message.get("tool_calls", [])
                
                if tool_calls:
                    logger.info(f"✓ Test {i} PASSED: Model made {len(tool_calls)} tool call(s)")
                    for j, tool_call in enumerate(tool_calls, 1):
                        function_data = tool_call.get("function", {})
                        logger.info(f"  Tool call {j}:")
                        logger.info(f"    Name: {function_data.get('name')}")
                        logger.info(f"    Arguments: {function_data.get('arguments')}")
                    
                    # Execute the tool call
                    tool_results = await tool_manager.execute_tools(tool_calls)
                    if tool_results:
                        result_data = tool_results[0]
                        if result_data.get("success"):
                            logger.info(f"  Tool execution result: {result_data.get('result')}")
                            passed_tests += 1
                        else:
                            logger.warning(f"  Tool execution failed: {result_data.get('error')}")
                    else:
                        logger.warning(f"  Tool execution returned no results")
                else:
                    content = message.get("content", "")
                    logger.warning(f"✗ Test {i} FAILED: No tool calls detected")
                    logger.info(f"  Response content: {content[:200]}...")
                    
        except Exception as e:
            logger.error(f"✗ Test {i} ERROR: {e}", exc_info=True)
    
    logger.info(f"\n{'='*60}")
    logger.info("Test Summary:")
    logger.info(f"  Total tests: {total_tests}")
    logger.info(f"  Passed: {passed_tests}")
    logger.info(f"  Failed: {total_tests - passed_tests}")
    logger.info(f"{'='*60}\n")
    
    return passed_tests == total_tests


async def test_all_benchmark_models(models_dir: Path) -> dict:
    """Test function calling with all benchmark models.
    
    Args:
        models_dir: Directory containing benchmark models
        
    Returns:
        Dict with test results for each model
    """
    # Find all .gguf files
    model_files = list(models_dir.glob("**/*.gguf"))
    
    if not model_files:
        logger.warning(f"No .gguf files found in {models_dir}")
        return {}
    
    results = {}
    
    for model_file in model_files:
        logger.info(f"\n{'#'*60}")
        logger.info(f"Testing model: {model_file.name}")
        logger.info(f"{'#'*60}\n")
        
        try:
            success = await test_function_calling(str(model_file))
            results[model_file.name] = {
                "success": success,
                "path": str(model_file)
            }
        except Exception as e:
            logger.error(f"Error testing {model_file.name}: {e}", exc_info=True)
            results[model_file.name] = {
                "success": False,
                "error": str(e),
                "path": str(model_file)
            }
    
    return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test function calling with benchmark models"
    )
    parser.add_argument(
        '--model',
        type=str,
        help='Path to specific model file to test'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Test all benchmark models in models directory'
    )
    
    args = parser.parse_args()
    
    try:
        if args.all:
            from src.config.settings import settings
            results = asyncio.run(test_all_benchmark_models(settings.models_dir))
            
            logger.info(f"\n{'='*60}")
            logger.info("All Models Test Summary:")
            logger.info(f"{'='*60}")
            for model_name, result in results.items():
                status = "✓ PASSED" if result.get("success") else "✗ FAILED"
                logger.info(f"  {model_name}: {status}")
            logger.info(f"{'='*60}\n")
        else:
            success = asyncio.run(test_function_calling(args.model))
            sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nTest cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
