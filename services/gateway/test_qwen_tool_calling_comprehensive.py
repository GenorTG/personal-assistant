#!/usr/bin/env python3
"""Comprehensive test for Qwen 2.5 tool calling functionality."""
import asyncio
import httpx
import json
import time
from typing import Dict, Any, Optional

class QwenToolCallingTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.llm_url = "http://localhost:8001"
        self.model_id = "MaziyarPanahi/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct.Q4_K_M.gguf"
        self.results = {}
    
    async def check_server(self) -> bool:
        """Check if gateway server is running."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except:
            return False
    
    async def unload_current_model(self):
        """Unload any currently loaded model."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.base_url}/api/models/unload")
                if response.status_code == 200:
                    await asyncio.sleep(2)
                    return True
        except:
            pass
        return False
    
    async def load_model(self) -> bool:
        """Load the Qwen model."""
        print("\n[TEST 1] Loading Qwen Model")
        print("-" * 70)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/models/{self.model_id}/load",
                    json={"n_gpu_layers": -1}
                )
                if response.status_code == 200:
                    data = response.json()
                    print(f"✓ Model loaded: {data.get('message', 'OK')}")
                    print(f"  Supports tool calling: {data.get('supports_tool_calling', False)}")
                    return True
                else:
                    print(f"✗ Failed to load model: {response.status_code}")
                    print(f"  Error: {response.text[:300]}")
                    return False
        except Exception as e:
            print(f"✗ Error loading model: {e}")
            return False
    
    async def wait_for_llm_server(self, max_wait: int = 60) -> bool:
        """Wait for LLM server to be ready."""
        print("\n[WAIT] Waiting for LLM server to be ready...")
        for i in range(max_wait):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(f"{self.llm_url}/v1/models")
                    if response.status_code == 200:
                        print(f"✓ LLM server is ready (waited {i+1}s)")
                        return True
            except:
                pass
            await asyncio.sleep(1)
        print(f"✗ LLM server did not become ready after {max_wait}s")
        return False
    
    async def check_tool_calling_status(self) -> Dict[str, Any]:
        """Check if tool calling is enabled."""
        print("\n[TEST 2] Checking Tool Calling Status")
        print("-" * 70)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/settings")
                if response.status_code == 200:
                    settings = response.json()
                    supports = settings.get("supports_tool_calling", False)
                    current_model = settings.get("current_model", "None")
                    print(f"  Current model: {current_model}")
                    print(f"  Supports tool calling: {supports}")
                    return {"supports": supports, "model": current_model}
                else:
                    print(f"✗ Failed to get settings: {response.status_code}")
                    return {"supports": False, "model": None}
        except Exception as e:
            print(f"✗ Error checking status: {e}")
            return {"supports": False, "model": None}
    
    async def test_basic_chat(self) -> bool:
        """Test basic chat functionality."""
        print("\n[TEST 3] Basic Chat Functionality")
        print("-" * 70)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "Say 'Hello, I am Qwen and I am working!' and nothing else.",
                        "conversation_id": None
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "response" in data:
                        response_text = data["response"]
                        print(f"✓ Chat successful!")
                        print(f"  Response: {response_text[:150]}...")
                        return True
                    else:
                        print(f"✗ No response in data: {data}")
                        return False
                else:
                    print(f"✗ Chat failed: {response.status_code}")
                    print(f"  Error: {response.text[:300]}")
                    return False
        except Exception as e:
            print(f"✗ Error in chat: {e}")
            return False
    
    async def test_tool_calling(self) -> Dict[str, Any]:
        """Test tool calling functionality."""
        print("\n[TEST 4] Tool Calling Functionality")
        print("-" * 70)
        result = {
            "supports": False,
            "made_tool_call": False,
            "response": None,
            "tool_calls": [],
            "error": None
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # First check status
                status = await self.check_tool_calling_status()
                result["supports"] = status["supports"]
                
                if not result["supports"]:
                    print("⚠ Tool calling is disabled - this should not happen for Qwen!")
                    return result
                
                print("→ Attempting tool call request...")
                print("  Request: 'What time is it? Use the get_current_time tool to check the current time.'")
                
                # Make tool call request
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "What time is it? Use the get_current_time tool to check the current time.",
                        "conversation_id": None
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    result["response"] = data.get("response", "")
                    tool_calls = data.get("tool_calls", [])
                    result["tool_calls"] = tool_calls
                    
                    if tool_calls and len(tool_calls) > 0:
                        result["made_tool_call"] = True
                        print(f"✓✓✓ TOOL CALL MADE! ✓✓✓")
                        for i, tc in enumerate(tool_calls):
                            func_name = tc.get("function", {}).get("name", "unknown")
                            func_args = tc.get("function", {}).get("arguments", "{}")
                            print(f"  Tool call {i+1}: {func_name}")
                            print(f"    Arguments: {func_args}")
                        print(f"  Response: {result['response'][:200]}...")
                    else:
                        print("⚠ No tool calls in response")
                        print(f"  Response: {result['response'][:300]}...")
                        # Check if response mentions tool
                        if "tool" in result["response"].lower() or "time" in result["response"].lower():
                            print("  (Response mentions tool/time - model may have tried to use it)")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                    print(f"✗ Tool calling test failed: {response.status_code}")
                    print(f"  Error: {result['error']}")
        except Exception as e:
            result["error"] = str(e)
            print(f"✗ Error in tool calling test: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    async def test_direct_llm_api(self) -> Dict[str, Any]:
        """Test direct LLM server API with tool calling."""
        print("\n[TEST 5] Direct LLM Server API with Tool Calling")
        print("-" * 70)
        result = {
            "success": False,
            "tool_calls": [],
            "response": None,
            "error": None
        }
        
        try:
            # Create a test tool
            test_tool = {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current time in ISO format",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "format": {
                                "type": "string",
                                "description": "Time format",
                                "enum": ["iso", "unix"]
                            }
                        }
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.llm_url}/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are Qwen, a helpful assistant. When asked to use a tool, you must call it."
                            },
                            {
                                "role": "user",
                                "content": "What is the current time? You MUST use the get_current_time tool. Call it now."
                            }
                        ],
                        "tools": [test_tool],
                        "tool_choice": "auto",
                        "max_tokens": 200
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        message = data["choices"][0].get("message", {})
                        result["response"] = message.get("content", "")
                        tool_calls = message.get("tool_calls")
                        
                        if tool_calls:
                            result["success"] = True
                            result["tool_calls"] = tool_calls
                            print(f"✓ Direct API call successful with tool calls!")
                            for i, tc in enumerate(tool_calls):
                                func_name = tc.get("function", {}).get("name", "unknown")
                                print(f"  Tool call {i+1}: {func_name}")
                        else:
                            print(f"⚠ Direct API call successful but no tool calls")
                            print(f"  Response: {result['response'][:200]}...")
                    else:
                        result["error"] = "No choices in response"
                        print(f"✗ Unexpected response format: {data}")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                    print(f"✗ Direct API call failed: {response.status_code}")
        except Exception as e:
            result["error"] = str(e)
            print(f"✗ Error in direct API test: {e}")
        
        return result
    
    async def test_full_tool_execution_flow(self) -> Dict[str, Any]:
        """Test full flow: request → tool call → execution → response."""
        print("\n[TEST 6] Full Tool Execution Flow")
        print("-" * 70)
        result = {
            "success": False,
            "tool_called": False,
            "tool_executed": False,
            "final_response": None,
            "error": None
        }
        
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                # Make a request that should trigger tool execution
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "Please check the current time using the get_current_time tool and tell me what time it is.",
                        "conversation_id": None
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    tool_calls = data.get("tool_calls", [])
                    final_response = data.get("response", "")
                    
                    if tool_calls:
                        result["tool_called"] = True
                        print(f"✓ Tool call made: {tool_calls[0].get('function', {}).get('name')}")
                        
                        # Check if response indicates tool was executed
                        if "time" in final_response.lower() and len(final_response) > 50:
                            result["tool_executed"] = True
                            result["success"] = True
                            print(f"✓ Tool appears to have been executed")
                            print(f"  Final response: {final_response[:200]}...")
                        else:
                            print(f"⚠ Tool called but execution unclear")
                            print(f"  Response: {final_response[:200]}...")
                    else:
                        print(f"⚠ No tool calls in response")
                        print(f"  Response: {final_response[:200]}...")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                    print(f"✗ Request failed: {response.status_code}")
        except Exception as e:
            result["error"] = str(e)
            print(f"✗ Error in full flow test: {e}")
        
        return result
    
    async def run_all_tests(self):
        """Run all tests."""
        print("=" * 70)
        print("COMPREHENSIVE QWEN TOOL CALLING TEST")
        print("=" * 70)
        
        # Check server
        if not await self.check_server():
            print("\n❌ Gateway server is not running!")
            print("   Please start the gateway server first")
            return
        
        print("✓ Gateway server is running")
        
        # Unload current model
        await self.unload_current_model()
        
        # Load Qwen model
        if not await self.load_model():
            print("\n❌ Failed to load Qwen model - cannot continue")
            return
        
        # Wait for server
        if not await self.wait_for_llm_server():
            print("\n❌ LLM server not ready - cannot continue")
            return
        
        # Run tests
        tests = [
            ("Basic Chat", self.test_basic_chat),
            ("Tool Calling Status", self.check_tool_calling_status),
            ("Tool Calling", self.test_tool_calling),
            ("Direct LLM API", self.test_direct_llm_api),
            ("Full Tool Execution Flow", self.test_full_tool_execution_flow),
        ]
        
        all_passed = True
        for test_name, test_func in tests:
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                else:
                    result = test_func()
                self.results[test_name] = result
                if isinstance(result, bool) and not result:
                    all_passed = False
                elif isinstance(result, dict):
                    if result.get("error") or (result.get("success") is False and "success" in result):
                        all_passed = False
            except Exception as e:
                print(f"✗ Test '{test_name}' crashed: {e}")
                import traceback
                traceback.print_exc()
                self.results[test_name] = {"error": str(e)}
                all_passed = False
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        for test_name, result in self.results.items():
            if isinstance(result, bool):
                status = "✓ PASS" if result else "✗ FAIL"
            elif isinstance(result, dict):
                if result.get("made_tool_call") or result.get("tool_called"):
                    status = "✓✓✓ PASS (TOOL CALLS WORK!)"
                elif result.get("error"):
                    status = f"✗ FAIL: {result.get('error')[:50]}"
                elif result.get("success") is False:
                    status = "✗ FAIL"
                else:
                    status = "⚠ PARTIAL"
            else:
                status = "?"
            print(f"{status}: {test_name}")
        
        print("\n" + "=" * 70)
        if all_passed:
            print("✅ ALL TESTS PASSED!")
        else:
            print("⚠ SOME TESTS FAILED OR WERE INCOMPLETE")
        print("=" * 70)

async def main():
    test = QwenToolCallingTest()
    try:
        await test.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⚠ Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

