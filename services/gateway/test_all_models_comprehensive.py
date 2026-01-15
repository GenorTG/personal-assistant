#!/usr/bin/env python3
"""Comprehensive test for all downloaded benchmark models.

Tests each model for:
1. Basic chat response (does it respond at all)
2. Jinja template loading (no errors)
3. Function calling capability
"""

import sys
import asyncio
from pathlib import Path
import logging
import httpx
import json
import subprocess
import time
import signal

# Add gateway src to path
gateway_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(gateway_dir / "src"))
sys.path.insert(0, str(gateway_dir))

try:
    from src.services.service_manager import ServiceManager
    from src.services.llm.model_info import ModelInfoExtractor
except ImportError:
    import os
    os.chdir(str(gateway_dir))
    sys.path.insert(0, str(gateway_dir / "src"))
    from src.services.service_manager import ServiceManager
    from src.services.llm.model_info import ModelInfoExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_model_comprehensive(model_path: Path) -> dict:
    """Test a single model comprehensively.
    
    Returns:
        Dict with test results
    """
    model_name = model_path.name
    logger.info(f"\n{'='*80}")
    logger.info(f"TESTING MODEL: {model_name}")
    logger.info(f"{'='*80}")
    
    results = {
        "model": model_name,
        "path": str(model_path),
        "exists": model_path.exists(),
        "basic_chat": None,
        "jinja_template": None,
        "function_calling": None,
        "errors": []
    }
    
    if not model_path.exists():
        logger.error(f"✗ Model file does not exist: {model_path}")
        results["errors"].append("Model file not found")
        return results
    
    # Test 1: Check Jinja template loading
    logger.info(f"\n[1/3] Testing Jinja template loading...")
    try:
        info_extractor = ModelInfoExtractor(model_path.parent)
        template_file = info_extractor.extract_and_save_template(model_name, force=False)
        
        if template_file and template_file.exists():
            template_content = template_file.read_text(encoding='utf-8')
            logger.info(f"✓ Jinja template found: {template_file.name}")
            logger.info(f"  Template length: {len(template_content)} chars")
            results["jinja_template"] = {
                "status": "success",
                "file": str(template_file),
                "length": len(template_content)
            }
        else:
            logger.warning(f"⚠ No Jinja template file found (may be in GGUF metadata)")
            results["jinja_template"] = {
                "status": "not_found",
                "note": "Template may be in GGUF metadata"
            }
    except Exception as e:
        logger.error(f"✗ Error loading Jinja template: {e}")
        results["jinja_template"] = {
            "status": "error",
            "error": str(e)
        }
        results["errors"].append(f"Jinja template error: {e}")
    
    # Test 2: Basic chat response
    logger.info(f"\n[2/3] Testing basic chat response...")
    server_port = 8100
    server_process = None
    
    try:
        # Start server
        server_cmd = [
            sys.executable,
            "-m", "llama_cpp.server",
            "--model", str(model_path.resolve()),
            "--host", "127.0.0.1",
            "--port", str(server_port),
            "--n_ctx", "2048",  # Smaller context for faster testing
            "--n_gpu_layers", "-1",
            "--n_threads", "4"
        ]
        
        logger.info(f"Starting server on port {server_port}...")
        server_process = subprocess.Popen(
            server_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait for server to start (longer for large models)
        # With freed VRAM, models should load faster, but still need reasonable timeout
        model_size_gb = model_path.stat().st_size / (1024**3)
        if model_size_gb > 20:
            max_wait = 180  # 3 minutes for very large models
        elif model_size_gb > 10:
            max_wait = 120  # 2 minutes for large models
        elif model_size_gb > 5:
            max_wait = 90   # 1.5 minutes for medium models
        else:
            max_wait = 60   # 1 minute for smaller models
        
        waited = 0
        server_ready = False
        
        logger.info(f"Waiting up to {max_wait}s for server to start (model size: {model_size_gb:.1f} GB)...")
        logger.info(f"Checking server status every 2 seconds...")
        
        # Check server startup with exponential backoff for first few checks
        check_interval = 2
        while waited < max_wait:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://127.0.0.1:{server_port}/v1/models")
                    if response.status_code == 200:
                        # Verify we can actually get model info
                        models_data = response.json()
                        if models_data.get("data"):
                            server_ready = True
                            logger.info(f"✓ Server started successfully after {waited}s")
                            break
            except httpx.ConnectError:
                # Server not ready yet, continue waiting
                pass
            except Exception as e:
                logger.debug(f"Server check error (expected during startup): {e}")
            
            if waited % 10 == 0 and waited > 0:
                logger.info(f"  Still waiting... ({waited}/{max_wait}s)")
            
            await asyncio.sleep(check_interval)
            waited += check_interval
        
        if not server_ready:
            # Check if process is still running
            if server_process and server_process.poll() is None:
                logger.warning(f"Server process still running but not responding - may need more time")
            else:
                logger.error(f"Server process exited with code: {server_process.returncode if server_process else 'unknown'}")
                if server_process:
                    stdout, stderr = server_process.communicate(timeout=2)
                    if stderr:
                        logger.error(f"Server stderr: {stderr.decode()[:500]}")
            raise TimeoutError(f"Server did not start within {max_wait} seconds")
        
        logger.info(f"✓ Server started successfully")
        
        # Test basic chat with strict parameters
        payload = {
            "model": "test",
            "messages": [
                {"role": "user", "content": "Say 'Hello' if you can read this."}
            ],
            "max_tokens": 20,
            "temperature": 0.0,  # Strict for deterministic testing
            "top_p": 1.0,  # No top_p filtering
            "repeat_penalty": 1.0  # No repetition penalty
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"http://127.0.0.1:{server_port}/v1/chat/completions",
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                logger.info(f"✓ Basic chat response received")
                logger.info(f"  Response: {content[:100]}...")
                results["basic_chat"] = {
                    "status": "success",
                    "response": content[:200],
                    "tokens": result.get("usage", {}).get("total_tokens", 0)
                }
            else:
                error_text = response.text[:500]
                logger.error(f"✗ Chat request failed: {response.status_code}")
                logger.error(f"  Error: {error_text}")
                results["basic_chat"] = {
                    "status": "error",
                    "status_code": response.status_code,
                    "error": error_text
                }
                results["errors"].append(f"Chat error: {response.status_code}")
    
    except Exception as e:
        logger.error(f"✗ Error during basic chat test: {e}")
        results["basic_chat"] = {
            "status": "error",
            "error": str(e)
        }
        results["errors"].append(f"Basic chat error: {e}")
    
    finally:
        # Stop server
        if server_process:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
                logger.info("✓ Server stopped")
            except:
                try:
                    server_process.kill()
                except:
                    pass
    
    # Test 3: Function calling (if basic chat worked)
    logger.info(f"\n[3/3] Testing function calling...")
    if results["basic_chat"] and results["basic_chat"]["status"] == "success":
        try:
            # Start server again for function calling test
            server_process = subprocess.Popen(
                server_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for server
            waited = 0
            server_ready = False
            while waited < max_wait:
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        response = await client.get(f"http://127.0.0.1:{server_port}/v1/models")
                        if response.status_code == 200:
                            server_ready = True
                            break
                except:
                    pass
                await asyncio.sleep(1)
                waited += 1
            
            if server_ready:
                # Test with tools
                tools = [{
                    "type": "function",
                    "function": {
                        "name": "add_numbers",
                        "description": "Add two numbers together",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "integer", "description": "First number"},
                                "b": {"type": "integer", "description": "Second number"}
                            },
                            "required": ["a", "b"]
                        }
                    }
                }]
                
                payload = {
                    "model": "test",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant. When asked to use a tool, you MUST call it. You MUST respond with a tool call, not natural language."},
                        {"role": "user", "content": "Call the add_numbers tool with a=3 and b=5. You MUST use the tool."}
                    ],
                    "tools": tools,
                    "tool_choice": "required",  # Force tool use
                    "temperature": 0.0,  # Strict for tool calling
                    "top_p": 1.0,  # No top_p filtering
                    "repeat_penalty": 1.0,  # No repetition penalty
                    "max_tokens": 200  # More tokens for JSON response
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"http://127.0.0.1:{server_port}/v1/chat/completions",
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        message = result.get("choices", [{}])[0].get("message", {})
                        tool_calls = message.get("tool_calls", [])
                        
                        if tool_calls:
                            logger.info(f"✓ Function calling works! Found {len(tool_calls)} tool call(s)")
                            results["function_calling"] = {
                                "status": "success",
                                "tool_calls_count": len(tool_calls)
                            }
                        else:
                            logger.warning(f"⚠ Server accepted tools but model didn't make tool calls")
                            results["function_calling"] = {
                                "status": "no_tool_calls",
                                "note": "Model responded but didn't call tools"
                            }
                    else:
                        logger.warning(f"⚠ Function calling request failed: {response.status_code}")
                        results["function_calling"] = {
                            "status": "error",
                            "status_code": response.status_code
                        }
            
            # Stop server
            if server_process:
                try:
                    server_process.terminate()
                    server_process.wait(timeout=5)
                except:
                    try:
                        server_process.kill()
                    except:
                        pass
        
        except Exception as e:
            logger.warning(f"⚠ Function calling test error: {e}")
            results["function_calling"] = {
                "status": "error",
                "error": str(e)
            }
    else:
        logger.info("⏭ Skipping function calling test (basic chat failed)")
        results["function_calling"] = {
            "status": "skipped",
            "reason": "Basic chat test failed"
        }
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info(f"RESULTS FOR {model_name}:")
    logger.info(f"  Basic Chat: {results['basic_chat']['status'] if results['basic_chat'] else 'NOT TESTED'}")
    logger.info(f"  Jinja Template: {results['jinja_template']['status'] if results['jinja_template'] else 'NOT TESTED'}")
    logger.info(f"  Function Calling: {results['function_calling']['status'] if results['function_calling'] else 'NOT TESTED'}")
    if results['errors']:
        logger.warning(f"  Errors: {len(results['errors'])}")
    logger.info(f"{'='*80}\n")
    
    return results


async def test_all_models(max_model_size_gb: float = 10.0):
    """Test all downloaded models.
    
    Args:
        max_model_size_gb: Maximum model size in GB to test (default 10GB for 8GB VRAM)
    """
    # Find all GGUF files
    models_dir = Path("data/models")
    if not models_dir.exists():
        logger.error(f"Models directory not found: {models_dir}")
        return
    
    all_model_files = sorted(models_dir.glob("*.gguf"))
    
    # Filter by size (skip models too large for VRAM)
    model_files = []
    skipped_large = []
    
    for model_file in all_model_files:
        size_gb = model_file.stat().st_size / (1024**3)
        if size_gb <= max_model_size_gb:
            model_files.append(model_file)
        else:
            skipped_large.append((model_file.name, size_gb))
    
    if skipped_large:
        logger.info(f"\n⚠ Skipping {len(skipped_large)} model(s) larger than {max_model_size_gb}GB:")
        for name, size in skipped_large:
            logger.info(f"  - {name}: {size:.1f} GB")
    
    if not model_files:
        logger.error(f"No GGUF model files found under {max_model_size_gb}GB!")
        return
    
    logger.info(f"\n{'#'*80}")
    logger.info(f"COMPREHENSIVE MODEL TESTING")
    logger.info(f"Testing {len(model_files)} model(s) under {max_model_size_gb}GB")
    if skipped_large:
        logger.info(f"Skipped {len(skipped_large)} large model(s)")
    logger.info(f"{'#'*80}\n")
    
    logger.info(f"\n{'#'*80}")
    logger.info(f"COMPREHENSIVE MODEL TESTING")
    logger.info(f"Found {len(model_files)} model(s) to test")
    logger.info(f"{'#'*80}\n")
    
    all_results = []
    
    for i, model_file in enumerate(model_files, 1):
        logger.info(f"\n[{i}/{len(model_files)}]")
        try:
            results = await test_model_comprehensive(model_file)
            all_results.append(results)
        except Exception as e:
            logger.error(f"Error testing {model_file.name}: {e}", exc_info=True)
            all_results.append({
                "model": model_file.name,
                "status": "error",
                "error": str(e)
            })
    
    # Final summary
    logger.info(f"\n{'#'*80}")
    logger.info("FINAL TEST SUMMARY")
    logger.info(f"{'#'*80}\n")
    
    for results in all_results:
        model_name = results.get("model", "Unknown")
        basic_chat = results.get("basic_chat", {}).get("status", "N/A")
        jinja = results.get("jinja_template", {}).get("status", "N/A")
        func_calling = results.get("function_calling", {}).get("status", "N/A")
        
        status_icon = "✓" if basic_chat == "success" else "✗"
        logger.info(f"{status_icon} {model_name}")
        logger.info(f"    Chat: {basic_chat} | Template: {jinja} | Function Calling: {func_calling}")
    
    # Save results to file
    results_file = Path("data/models/test_results.json")
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    logger.info(f"\n✓ Detailed results saved to: {results_file}")
    
    return all_results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test all benchmark models")
    parser.add_argument(
        "--max-size",
        type=float,
        default=10.0,
        help="Maximum model size in GB to test (default: 10.0 for 8GB VRAM)"
    )
    args = parser.parse_args()
    
    try:
        results = asyncio.run(test_all_models(max_model_size_gb=args.max_size))
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("\nTest cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
