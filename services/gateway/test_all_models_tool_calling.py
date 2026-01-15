#!/usr/bin/env python3
"""Test all downloaded models for tool calling support."""
import asyncio
import httpx
import json
import time
from typing import Dict, Any, Optional, List

class ModelToolCallingTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.llm_url = "http://localhost:8001"
        self.results = {}
    
    async def check_server(self) -> bool:
        """Check if gateway server is running."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except:
            return False
    
    async def get_downloaded_models(self) -> List[Dict[str, Any]]:
        """Get list of downloaded models."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/models")
                if response.status_code == 200:
                    data = response.json()
                    # Handle both list and dict response formats
                    if isinstance(data, list):
                        models = data
                    elif isinstance(data, dict):
                        models = data.get("models", [])
                    else:
                        models = []
                    
                    # Filter to only downloaded models
                    downloaded = [m for m in models if isinstance(m, dict) and m.get("downloaded", False)]
                    return downloaded
                return []
        except Exception as e:
            print(f"✗ Error getting models: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def unload_current_model(self):
        """Unload any currently loaded model."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.base_url}/api/models/unload")
                if response.status_code == 200:
                    # Wait a bit for unload to complete
                    await asyncio.sleep(2)
                    return True
        except:
            pass
        return False
    
    async def load_model(self, model_id: str) -> bool:
        """Load a model."""
        print(f"\n  → Loading model: {model_id}")
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/models/{model_id}/load",
                    json={"n_gpu_layers": -1}
                )
                if response.status_code == 200:
                    data = response.json()
                    print(f"  ✓ Model loaded successfully")
                    print(f"    Supports tool calling: {data.get('supports_tool_calling', False)}")
                    return True
                else:
                    print(f"  ✗ Failed to load: {response.status_code}")
                    print(f"    Error: {response.text[:200]}")
                    return False
        except Exception as e:
            print(f"  ✗ Error loading model: {e}")
            return False
    
    async def wait_for_llm_server(self, max_wait: int = 60) -> bool:
        """Wait for LLM server to be ready."""
        for i in range(max_wait):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(f"{self.llm_url}/v1/models")
                    if response.status_code == 200:
                        return True
            except:
                pass
            await asyncio.sleep(1)
        return False
    
    async def test_basic_chat(self, model_id: str) -> bool:
        """Test basic chat functionality."""
        print(f"  → Testing basic chat...")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "Say 'Hello, I am working!' and nothing else.",
                        "conversation_id": None
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "response" in data and data["response"]:
                        print(f"  ✓ Chat works: {data['response'][:100]}...")
                        return True
                    else:
                        print(f"  ✗ No response in data")
                        return False
                else:
                    print(f"  ✗ Chat failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"  ✗ Error in chat: {e}")
            return False
    
    async def test_tool_calling(self, model_id: str) -> Dict[str, Any]:
        """Test tool calling functionality."""
        print(f"  → Testing tool calling...")
        result = {
            "supports": False,
            "made_tool_call": False,
            "response": None,
            "error": None,
            "metadata_says_supports": False
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Check metadata first
                models_resp = await client.get(f"{self.base_url}/api/models")
                if models_resp.status_code == 200:
                    models_data = models_resp.json()
                    if isinstance(models_data, list):
                        for m in models_data:
                            if m.get("model_id") == model_id:
                                result["metadata_says_supports"] = m.get("supports_tool_calling", False)
                                print(f"    Metadata says supports tool calling: {result['metadata_says_supports']}")
                                break
                
                # Check if model supports tool calling (runtime state)
                settings_resp = await client.get(f"{self.base_url}/api/settings")
                if settings_resp.status_code == 200:
                    settings = settings_resp.json()
                    supports = settings.get("supports_tool_calling", False)
                    result["supports"] = supports
                    print(f"    Runtime state says supports tool calling: {supports}")
                
                # Try to make a tool call even if disabled - sometimes models work despite being marked as disabled
                print(f"  → Attempting tool call request...")
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "message": "What is the current time? Use the get_current_time tool to check the current time.",
                        "conversation_id": None
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    result["response"] = data.get("response", "")
                    tool_calls = data.get("tool_calls", [])
                    
                    if tool_calls and len(tool_calls) > 0:
                        result["made_tool_call"] = True
                        result["supports"] = True  # If it made a call, it supports it
                        print(f"  ✓✓✓ TOOL CALL MADE! ✓✓✓")
                        print(f"    Tool: {tool_calls[0].get('name', 'unknown')}")
                        print(f"    Arguments: {tool_calls[0].get('arguments', {})}")
                        print(f"    Response: {result['response'][:200]}...")
                    else:
                        print(f"  ⚠ No tool calls in response")
                        print(f"    Response: {result['response'][:200]}...")
                        # Check if response mentions using the tool
                        response_lower = result["response"].lower()
                        if any(word in response_lower for word in ["tool", "function", "get_current_time", "called"]):
                            print(f"    (Response mentions tool/function - model may have tried to use it)")
                else:
                    result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
                    print(f"  ✗ Tool calling test failed: {response.status_code}")
        except Exception as e:
            result["error"] = str(e)
            print(f"  ✗ Error in tool calling test: {e}")
            import traceback
            traceback.print_exc()
        
        return result
    
    async def test_model(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single model."""
        model_id = model.get("id", "")
        model_name = model.get("name", model_id)
        
        print("\n" + "=" * 70)
        print(f"TESTING MODEL: {model_name}")
        print("=" * 70)
        
        result = {
            "model_id": model_id,
            "model_name": model_name,
            "loaded": False,
            "chat_works": False,
            "tool_calling": {
                "supports": False,
                "made_tool_call": False,
                "response": None,
                "error": None
            }
        }
        
        # Unload current model
        await self.unload_current_model()
        
        # Load model
        if await self.load_model(model_id):
            result["loaded"] = True
            await self.wait_for_llm_server()
            
            # Test basic chat
            if await self.test_basic_chat(model_id):
                result["chat_works"] = True
                
                # Test tool calling
                tool_result = await self.test_tool_calling(model_id)
                result["tool_calling"] = tool_result
            else:
                print(f"  ⚠ Skipping tool calling test (chat doesn't work)")
        else:
            print(f"  ⚠ Skipping tests (model failed to load)")
        
        return result
    
    async def run_all_tests(self):
        """Run tests for all downloaded models."""
        print("=" * 70)
        print("COMPREHENSIVE TOOL CALLING TEST FOR ALL MODELS")
        print("=" * 70)
        
        # Check server
        if not await self.check_server():
            print("\n❌ Gateway server is not running!")
            print("   Please start the gateway server first")
            return
        
        print("✓ Gateway server is running")
        
        # Get downloaded models
        print("\n[1] Fetching downloaded models...")
        models = await self.get_downloaded_models()
        
        if not models:
            print("✗ No downloaded models found")
            return
        
        print(f"✓ Found {len(models)} downloaded model(s)")
        for m in models:
            print(f"  - {m.get('name', m.get('id', 'unknown'))}")
        
        # Test each model
        print(f"\n[2] Testing {len(models)} model(s)...")
        for i, model in enumerate(models, 1):
            print(f"\n[{i}/{len(models)}] Testing model...")
            result = await self.test_model(model)
            model_id = model.get("id", model.get("model_id", "unknown"))
            self.results[model_id] = result
            
            # Small delay between models
            if i < len(models):
                await asyncio.sleep(3)
        
        # Print summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        for model_id, result in self.results.items():
            model_name = result.get("model_name", model_id)
            print(f"\n📦 {model_name}")
            print(f"   Model ID: {model_id}")
            print(f"   Loaded: {'✓' if result['loaded'] else '✗'}")
            print(f"   Chat: {'✓' if result['chat_works'] else '✗'}")
            tool_info = result.get("tool_calling", {})
            if tool_info.get("supports"):
                if tool_info.get("made_tool_call"):
                    print(f"   Tool Calling: ✓ SUPPORTS AND WORKS")
                else:
                    print(f"   Tool Calling: ⚠ SUPPORTS BUT DIDN'T MAKE CALL")
                    if tool_info.get("response"):
                        print(f"     Response: {tool_info['response'][:100]}...")
            else:
                print(f"   Tool Calling: ✗ NOT SUPPORTED OR DISABLED")
            if tool_info.get("error"):
                print(f"   Error: {tool_info['error']}")
        
        # Count successes
        total = len(self.results)
        loaded = sum(1 for r in self.results.values() if r["loaded"])
        chat_works = sum(1 for r in self.results.values() if r["chat_works"])
        tool_supports = sum(1 for r in self.results.values() if r.get("tool_calling", {}).get("supports", False))
        tool_works = sum(1 for r in self.results.values() if r.get("tool_calling", {}).get("made_tool_call", False))
        
        print("\n" + "=" * 70)
        print("OVERALL STATISTICS")
        print("=" * 70)
        print(f"Total models tested: {total}")
        print(f"Models loaded successfully: {loaded}/{total}")
        print(f"Models with working chat: {chat_works}/{total}")
        print(f"Models that support tool calling: {tool_supports}/{total}")
        print(f"Models that actually make tool calls: {tool_works}/{total}")
        print("=" * 70)

async def main():
    test = ModelToolCallingTest()
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

