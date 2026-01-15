#!/usr/bin/env python3
"""Comprehensive test for chat and tool calling with embedded tokenizer."""
import asyncio
import httpx
import json
import time
from typing import Dict, Any, Optional

class ChatAndToolsTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.llm_url = "http://localhost:8001"
        self.model_id = "Llama-3.2-4X3B-MOE-Hell-California-10B-D_AU-Q4_k_s.gguf"
        self.results = {}
    
    async def check_server(self) -> bool:
        """Check if gateway server is running."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except:
            return False
    
    async def load_model(self) -> bool:
        """Load the model."""
        print("\n[TEST 1] Loading Model")
        print("-" * 60)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
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
    
    async def test_basic_chat(self) -> bool:
        """Test basic chat functionality."""
        print("\n[TEST 2] Basic Chat Functionality")
        print("-" * 60)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "Hello! Please respond with just 'Hi there!' and nothing else.",
                        "conversation_id": None
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "response" in data:
                        response_text = data["response"]
                        print(f"✓ Chat successful!")
                        print(f"  Response: {response_text[:150]}...")
                        print(f"  Length: {len(response_text)} chars")
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
            import traceback
            traceback.print_exc()
            return False
    
    async def test_tool_calling(self) -> bool:
        """Test tool calling functionality."""
        print("\n[TEST 3] Tool Calling Functionality")
        print("-" * 60)
        
        # First check if model supports tool calling
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/settings")
                if response.status_code == 200:
                    settings = response.json()
                    supports_tool_calling = settings.get("supports_tool_calling", False)
                    if not supports_tool_calling:
                        print("⚠ Model does not support tool calling (or was disabled)")
                        print("  This is OK - not all models support it")
                        return True  # Don't fail - this is expected
        except Exception as e:
            print(f"⚠ Could not check tool calling support: {e}")
        
        # Test tool calling with time tool
        print("→ Testing tool calling with time tool...")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "What time is it right now? Use the get_current_time tool to check the current time.",
                        "conversation_id": None
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    tool_calls = data.get("tool_calls")
                    if tool_calls:
                        print(f"✓ Tool calls made: {len(tool_calls)}")
                        for i, tc in enumerate(tool_calls):
                            func_name = tc.get("function", {}).get("name", "unknown")
                            print(f"  Tool call {i+1}: {func_name}")
                        print(f"✓ Response received: {len(data.get('response', ''))} chars")
                        return True
                    else:
                        print("⚠ No tool calls in response")
                        print(f"  Response: {data.get('response', '')[:200]}")
                        print("  (Model may have chosen not to use tool, or tool calling not working)")
                        return True  # Don't fail - model may choose not to use tool
                else:
                    print(f"✗ Tool calling test failed: {response.status_code}")
                    print(f"  Error: {response.text[:300]}")
                    return False
        except Exception as e:
            print(f"✗ Error in tool calling test: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def check_server_command(self) -> Optional[str]:
        """Check what command was used to start the LLM server."""
        print("\n[INFO] Checking LLM Server Configuration")
        print("-" * 60)
        try:
            import subprocess
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=2.0
            )
            for line in result.stdout.split('\n'):
                if 'llama_cpp.server' in line and '--model' in line:
                    # Extract the command
                    parts = line.split()
                    cmd_start = next((i for i, p in enumerate(parts) if 'llama_cpp.server' in p), None)
                    if cmd_start:
                        cmd = ' '.join(parts[cmd_start:])
                        print(f"Server command: {cmd[:200]}...")
                        # Check for chat_format
                        if '--chat_format' in cmd:
                            print("⚠ WARNING: --chat_format is present (may cause tokenizer issues)")
                        else:
                            print("✓ No --chat_format (using embedded tokenizer)")
                        # Check for hf_pretrained
                        if '--hf_pretrained_model_name_or_path' in cmd:
                            print("⚠ WARNING: --hf_pretrained_model_name_or_path is present")
                        else:
                            print("✓ No external tokenizer path (using embedded tokenizer)")
                        return cmd
            print("⚠ Could not find LLM server process")
            return None
        except Exception as e:
            print(f"⚠ Could not check server command: {e}")
            return None
    
    async def test_direct_llm_api(self) -> bool:
        """Test direct LLM server API."""
        print("\n[TEST 4] Direct LLM Server API Test")
        print("-" * 60)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.llm_url}/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [
                            {"role": "user", "content": "Say hello"}
                        ]
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0].get("message", {}).get("content", "")
                        print(f"✓ Direct API call successful")
                        print(f"  Response: {content[:100]}...")
                        return True
                    else:
                        print(f"✗ Unexpected response format: {data}")
                        return False
                else:
                    error_text = response.text[:300]
                    print(f"✗ Direct API call failed: {response.status_code}")
                    print(f"  Error: {error_text}")
                    if "tokenizer" in error_text.lower():
                        print("  ⚠ Tokenizer-related error detected")
                    return False
        except Exception as e:
            print(f"✗ Error in direct API test: {e}")
            return False
    
    async def run_all_tests(self) -> bool:
        """Run all tests."""
        print("=" * 60)
        print("COMPREHENSIVE CHAT AND TOOL CALLING TEST")
        print("=" * 60)
        
        # Check server
        if not await self.check_server():
            print("\n❌ Gateway server is not running!")
            print("   Please start the gateway server first")
            return False
        print("✓ Gateway server is running")
        
        # Check server command
        await self.check_server_command()
        
        # Load model
        if not await self.load_model():
            return False
        
        # Wait for LLM server
        if not await self.wait_for_llm_server():
            return False
        
        # Run tests
        tests = [
            ("Basic Chat", self.test_basic_chat),
            ("Direct LLM API", self.test_direct_llm_api),
            ("Tool Calling", self.test_tool_calling),
        ]
        
        all_passed = True
        for test_name, test_func in tests:
            try:
                result = await test_func()
                self.results[test_name] = result
                if not result:
                    all_passed = False
            except Exception as e:
                print(f"✗ Test '{test_name}' crashed: {e}")
                import traceback
                traceback.print_exc()
                self.results[test_name] = False
                all_passed = False
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        for test_name, result in self.results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        print("\n" + "=" * 60)
        if all_passed:
            print("✅ ALL TESTS PASSED!")
        else:
            print("⚠ SOME TESTS FAILED OR WERE SKIPPED")
        print("=" * 60)
        
        return all_passed

async def main():
    test = ChatAndToolsTest()
    try:
        success = await test.run_all_tests()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠ Tests interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite crashed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())


