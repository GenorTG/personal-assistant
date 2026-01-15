#!/usr/bin/env python3
"""Comprehensive test for LLM server functionality.

This test validates:
1. Server startup (OpenAI-compatible llama-cpp-python server)
2. Model loading
3. OpenAI API compatibility (health, models endpoints)
4. Chat completion
5. Tool calling

REQUIREMENTS:
- Gateway Python environment must be set up (venv with dependencies installed)
- At least one GGUF model file in the models directory

To run:
    cd services/gateway
    ../.core_venv/bin/python test_llm_server.py
"""
import asyncio
import sys
import logging
import subprocess
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
import json

# Set up path for imports - add gateway directory (parent of src) to path
gateway_dir = Path(__file__).parent.resolve()
src_dir = gateway_dir / "src"

# Add gateway directory to path so src is treated as a package
if str(gateway_dir) not in sys.path:
    sys.path.insert(0, str(gateway_dir))

# Import from src package
from src.config.settings import settings
from src.services.service_manager import ServiceManager
from src.services.tools.builtin.time_tool import TimeTool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LLMServerTest:
    """Comprehensive test for LLM server."""
    
    def __init__(self):
        self.service_manager: Optional[ServiceManager] = None
        self.model_path: Optional[str] = None
        self.server_url: str = settings.llm_service_url
        self.server_port: int = 8001
        self.test_results: Dict[str, bool] = {}
    
    def kill_process_on_port(self, port: int) -> bool:
        """Kill any process using the specified port.
        
        Returns:
            True if port was freed (or already free), False on error
        """
        try:
            # Check if port is in use
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result != 0:
                # Port is not in use
                return True
            
            # Port is in use, find and kill the process
            logger.warning(f"Port {port} is already in use, attempting to free it...")
            
            # Try to find process using the port (Linux/Mac)
            try:
                # Use lsof or fuser to find the process
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid:
                            try:
                                logger.info(f"Killing process {pid} on port {port}")
                                subprocess.run(['kill', '-9', pid], timeout=5, check=False)
                            except Exception as e:
                                logger.warning(f"Failed to kill process {pid}: {e}")
                    
                    # Wait a moment for port to be freed
                    import time
                    time.sleep(1)
                    
                    # Verify port is now free
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', port))
                    sock.close()
                    
                    if result != 0:
                        logger.info(f"✓ Port {port} is now free")
                        return True
                    else:
                        logger.warning(f"Port {port} is still in use after kill attempt")
                        return False
                else:
                    # Try alternative method with fuser (if lsof didn't work)
                    result = subprocess.run(
                        ['fuser', '-k', f'{port}/tcp'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        import time
                        time.sleep(1)
                        logger.info(f"✓ Port {port} freed using fuser")
                        return True
                    else:
                        logger.warning(f"Could not find process using port {port}")
                        return False
                        
            except FileNotFoundError:
                # lsof/fuser not available, try netstat (Windows/Linux)
                try:
                    result = subprocess.run(
                        ['netstat', '-ano'] if sys.platform == 'win32' else ['netstat', '-tlnp'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    # Parse netstat output to find PID (complex, skip for now)
                    logger.warning("Could not automatically free port (lsof/fuser not available)")
                    return False
                except FileNotFoundError:
                    logger.warning("Could not automatically free port (no tools available)")
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking/freeing port {port}: {e}")
            return False
    
    def log_test_step(self, step_name: str, status: str, message: str = ""):
        """Log a test step with clear status indicator."""
        status_symbol = "✓" if status == "pass" else "✗" if status == "fail" else "→"
        logger.info(f"{status_symbol} [{step_name}] {message}")
        self.test_results[step_name] = (status == "pass")
    
    async def initialize(self) -> bool:
        """Initialize service manager and find a model."""
        logger.info("=" * 70)
        logger.info("LLM SERVER COMPREHENSIVE TEST")
        logger.info("=" * 70)
        
        try:
            # Initialize service manager
            self.log_test_step("init", "running", "Initializing service manager...")
            self.service_manager = ServiceManager()
            await self.service_manager.initialize()
            self.log_test_step("init", "pass", "Service manager initialized")
            
            # Find available model
            self.log_test_step("find_model", "running", "Searching for GGUF models...")
            models_dir = Path(settings.models_dir)
            if not models_dir.exists():
                self.log_test_step("find_model", "fail", f"Models directory does not exist: {models_dir}")
                return False
            
            gguf_files = list(models_dir.rglob("*.gguf"))
            if not gguf_files:
                self.log_test_step("find_model", "fail", f"No GGUF models found in {models_dir}")
                return False
            
            # Use first model found
            model_file = gguf_files[0]
            self.model_path = str(model_file)
            relative_path = model_file.relative_to(models_dir)
            self.log_test_step("find_model", "pass", f"Found model: {relative_path}")
            
            return True
            
        except Exception as e:
            self.log_test_step("init", "fail", f"Error: {e}")
            logger.error("Initialization failed", exc_info=True)
            return False
    
    async def test_server_startup(self) -> bool:
        """Test 1: Server startup via model loading."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("TEST 1: SERVER STARTUP")
        logger.info("-" * 70)
        
        try:
            if not self.service_manager or not self.model_path:
                self.log_test_step("server_startup", "fail", "Service manager or model path not initialized")
                return False
            
            # Check and free port if needed
            self.log_test_step("port_check", "running", f"Checking port {self.server_port}...")
            if not self.kill_process_on_port(self.server_port):
                self.log_test_step("port_check", "fail", f"Could not free port {self.server_port}")
                logger.warning("Continuing anyway - server may fail to start if port is still in use")
            else:
                self.log_test_step("port_check", "pass", f"Port {self.server_port} is available")
            
            self.log_test_step("server_startup", "running", f"Loading model: {Path(self.model_path).name}")
            
            # Load model (this starts the server)
            success = await self.service_manager.llm_manager.load_model(self.model_path)
            
            if not success:
                error_msg = self.service_manager.llm_manager.server_manager.get_last_error()
                self.log_test_step("server_startup", "fail", f"Model loading failed: {error_msg}")
                return False
            
            # Verify server is running
            if not self.service_manager.llm_manager.is_model_loaded():
                self.log_test_step("server_startup", "fail", "Model loaded but server not detected as running")
                return False
            
            # Log tool calling support status
            supports_tc = self.service_manager.llm_manager.supports_tool_calling
            logger.info(f"Model tool calling support: {'ENABLED' if supports_tc else 'DISABLED'}")
            
            self.log_test_step("server_startup", "pass", "Server started successfully")
            return True
            
        except Exception as e:
            self.log_test_step("server_startup", "fail", f"Error: {e}")
            logger.error("Server startup test failed", exc_info=True)
            return False
    
    async def test_openai_compatibility(self) -> bool:
        """Test 2: OpenAI API compatibility (models endpoint)."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("TEST 2: OPENAI API COMPATIBILITY")
        logger.info("-" * 70)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test models endpoint (main OpenAI compatibility test)
                self.log_test_step("openai_models", "running", f"Testing /v1/models endpoint")
                try:
                    models_response = await client.get(f"{self.server_url}/v1/models")
                    if models_response.status_code == 200:
                        models_data = models_response.json()
                        if "data" in models_data and len(models_data["data"]) > 0:
                            model_id = models_data["data"][0].get("id", "unknown")
                            self.log_test_step("openai_models", "pass", f"Models endpoint returned model: {model_id}")
                        else:
                            self.log_test_step("openai_models", "fail", "Models endpoint returned empty data")
                            return False
                    else:
                        self.log_test_step("openai_models", "fail", f"Models endpoint returned {models_response.status_code}")
                        return False
                except Exception as e:
                    self.log_test_step("openai_models", "fail", f"Models endpoint error: {e}")
                    return False
            
            return True
            
        except Exception as e:
            self.log_test_step("openai_compatibility", "fail", f"Error: {e}")
            logger.error("OpenAI compatibility test failed", exc_info=True)
            return False
    
    async def test_template_verification(self) -> bool:
        """Test 3: Template verification via /props endpoint."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("TEST 3: TEMPLATE VERIFICATION")
        logger.info("-" * 70)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test /props endpoint
                self.log_test_step("template_props", "running", "Testing /props endpoint")
                try:
                    props_response = await client.get(f"{self.server_url}/props")
                    if props_response.status_code == 200:
                        props_data = props_response.json()
                        
                        # Check for template properties
                        has_chat_template = bool(props_data.get("chat_template"))
                        has_tool_use_template = bool(props_data.get("chat_template_tool_use"))
                        
                        if has_chat_template:
                            self.log_test_step("template_props", "pass", "chat_template found in /props")
                        else:
                            self.log_test_step("template_props", "warn", "chat_template not found in /props")
                        
                        if has_tool_use_template:
                            self.log_test_step("template_tool_use", "pass", "chat_template_tool_use found in /props")
                            logger.info("✓ Tool-use template is available - function calling should work")
                        else:
                            self.log_test_step("template_tool_use", "warn", "chat_template_tool_use not found in /props")
                            logger.warning("⚠ Tool-use template not found - function calling may not work")
                        
                        # Also check server manager's cached template info
                        template_info = self.service_manager.llm_manager.server_manager.get_template_info()
                        if template_info:
                            logger.info(f"Server manager template info: {template_info}")
                        
                        return True
                    else:
                        self.log_test_step("template_props", "fail", f"/props endpoint returned {props_response.status_code}")
                        logger.warning(f"/props endpoint not available (status {props_response.status_code})")
                        return False
                except httpx.HTTPStatusError as e:
                    self.log_test_step("template_props", "fail", f"/props endpoint error: {e.response.status_code}")
                    logger.warning(f"/props endpoint not available: {e}")
                    return False
                except Exception as e:
                    self.log_test_step("template_props", "fail", f"Error: {e}")
                    logger.warning(f"Could not test /props endpoint: {e}")
                    return False
            
        except Exception as e:
            self.log_test_step("template_verification", "fail", f"Error: {e}")
            logger.error("Template verification test failed", exc_info=True)
            return False
    
    async def test_chat_completion(self) -> bool:
        """Test 4: Chat completion."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("TEST 4: CHAT COMPLETION")
        logger.info("-" * 70)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                self.log_test_step("chat_completion", "running", "Sending chat completion request...")
                
                # Simple chat request
                payload = {
                    "model": "test-model",  # Model name doesn't matter for single-model server
                    "messages": [
                        {"role": "user", "content": "Say hello in exactly one word."}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 10
                }
                
                try:
                    response = await client.post(
                        f"{self.server_url}/v1/chat/completions",
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0].get("message", {}).get("content", "").strip()
                        if content:
                            self.log_test_step("chat_completion", "pass", f"Received response: '{content}'")
                            return True
                        else:
                            self.log_test_step("chat_completion", "fail", "Response has no content")
                            return False
                    else:
                        self.log_test_step("chat_completion", "fail", "Response has no choices")
                        return False
                        
                except httpx.HTTPStatusError as e:
                    self.log_test_step("chat_completion", "fail", f"HTTP error: {e.response.status_code} - {e.response.text[:200]}")
                    return False
                except Exception as e:
                    self.log_test_step("chat_completion", "fail", f"Error: {e}")
                    return False
            
        except Exception as e:
            self.log_test_step("chat_completion", "fail", f"Error: {e}")
            logger.error("Chat completion test failed", exc_info=True)
            return False
    
    async def test_tool_calling(self) -> bool:
        """Test 5: Tool calling with TimeTool."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("TEST 5: TOOL CALLING")
        logger.info("-" * 70)
        
        try:
            # Check if tool calling is supported
            if not self.service_manager.llm_manager.supports_tool_calling:
                self.log_test_step("tool_calling", "pass", "Model does not support tool calling (skipped)")
                logger.info("Model does not support tool calling - this is expected for some models")
                # Mark as pass since it's not a failure, just unsupported
                self.test_results["tool_calling"] = True
                return True  # Not a failure, just unsupported
            
            # Get tool schema
            time_tool = TimeTool()
            tool_schema = {
                "type": "function",
                "function": {
                    "name": time_tool.name,
                    "description": time_tool.description,
                    "parameters": time_tool.schema
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                self.log_test_step("tool_calling", "running", f"Requesting tool call for '{time_tool.name}'...")
                
                # Request tool call
                payload = {
                    "model": "test-model",
                    "messages": [
                        {"role": "user", "content": "What is the current time? Use the get_current_time tool."}
                    ],
                    "tools": [tool_schema],
                    "tool_choice": "required",  # Force tool use
                    "temperature": 0.7,
                    "max_tokens": 100
                }
                
                try:
                    response = await client.post(
                        f"{self.server_url}/v1/chat/completions",
                        json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        message = data["choices"][0].get("message", {})
                        tool_calls = message.get("tool_calls", [])
                        
                        if tool_calls:
                            tool_call = tool_calls[0]
                            function_name = tool_call.get("function", {}).get("name", "")
                            if function_name == time_tool.name:
                                self.log_test_step("tool_calling", "pass", f"Tool call detected: {function_name}")
                                
                                # Execute the tool to verify it works
                                tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                                tool_result = await time_tool.execute(tool_args)
                                if tool_result.get("result"):
                                    self.log_test_step("tool_execution", "pass", f"Tool executed successfully: {tool_result['result']}")
                                    return True
                                else:
                                    self.log_test_step("tool_execution", "fail", f"Tool execution failed: {tool_result.get('error')}")
                                    return False
                            else:
                                self.log_test_step("tool_calling", "fail", f"Wrong tool called: {function_name} (expected {time_tool.name})")
                                return False
                        else:
                            self.log_test_step("tool_calling", "fail", "No tool calls in response")
                            logger.debug(f"Response message: {message}")
                            return False
                    else:
                        self.log_test_step("tool_calling", "fail", "Response has no choices")
                        return False
                        
                except httpx.HTTPStatusError as e:
                    self.log_test_step("tool_calling", "fail", f"HTTP error: {e.response.status_code} - {e.response.text[:200]}")
                    return False
                except Exception as e:
                    self.log_test_step("tool_calling", "fail", f"Error: {e}")
                    return False
            
        except Exception as e:
            self.log_test_step("tool_calling", "fail", f"Error: {e}")
            logger.error("Tool calling test failed", exc_info=True)
            return False
    
    async def cleanup(self):
        """Clean up resources."""
        logger.info("")
        logger.info("-" * 70)
        logger.info("CLEANUP")
        logger.info("-" * 70)
        
        try:
            if self.service_manager and self.service_manager.llm_manager:
                if self.service_manager.llm_manager.is_model_loaded():
                    self.log_test_step("cleanup", "running", "Unloading model...")
                    await self.service_manager.llm_manager.unload_model()
                    self.log_test_step("cleanup", "pass", "Model unloaded")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    async def run(self) -> int:
        """Run all tests."""
        try:
            # Initialize
            if not await self.initialize():
                return 1
            
            # Run tests
            tests = [
                ("Server Startup", self.test_server_startup),
                ("OpenAI Compatibility", self.test_openai_compatibility),
                ("Template Verification", self.test_template_verification),
                ("Chat Completion", self.test_chat_completion),
                ("Tool Calling", self.test_tool_calling),
            ]
            
            all_passed = True
            for test_name, test_func in tests:
                try:
                    result = await test_func()
                    if not result:
                        all_passed = False
                except Exception as e:
                    logger.error(f"Test '{test_name}' raised exception: {e}", exc_info=True)
                    all_passed = False
            
            # Cleanup
            await self.cleanup()
            
            # Print summary
            logger.info("")
            logger.info("=" * 70)
            logger.info("TEST SUMMARY")
            logger.info("=" * 70)
            
            for step_name, passed in self.test_results.items():
                status = "PASS" if passed else "FAIL"
                symbol = "✓" if passed else "✗"
                logger.info(f"{symbol} {step_name}: {status}")
            
            if all_passed:
                logger.info("")
                logger.info("=" * 70)
                logger.info("✓ ALL TESTS PASSED")
                logger.info("=" * 70)
                return 0
            else:
                logger.info("")
                logger.info("=" * 70)
                logger.info("✗ SOME TESTS FAILED")
                logger.info("=" * 70)
                return 1
            
        except Exception as e:
            logger.error(f"Test suite failed with error: {e}", exc_info=True)
            await self.cleanup()
            return 1


async def main():
    """Main entry point."""
    test = LLMServerTest()
    exit_code = await test.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())

