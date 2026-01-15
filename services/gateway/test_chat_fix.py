#!/usr/bin/env python3
"""Test chat functionality fix."""
import asyncio
import httpx
import json
import time

async def test():
    base_url = "http://localhost:8000"
    
    print("=" * 60)
    print("TESTING CHAT FUNCTIONALITY FIX")
    print("=" * 60)
    
    # 1. Load model
    print("\n[1] Loading model...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url}/api/models/Llama-3.2-4X3B-MOE-Hell-California-10B-D_AU-Q4_k_s.gguf/load",
            json={"n_gpu_layers": -1}
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   ✓ Model load request successful")
        else:
            print(f"   ✗ Failed: {response.text[:200]}")
            return
    
    # 2. Wait for server to be ready
    print("\n[2] Waiting for LLM server to be ready...")
    for i in range(40):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get("http://localhost:8001/v1/models")
                if response.status_code == 200:
                    print(f"   ✓ Server is ready (waited {i+1}s)")
                    break
        except:
            pass
    else:
        print("   ✗ Server did not become ready")
        return
    
    # 3. Test chat
    print("\n[3] Testing chat...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url}/api/chat",
            json={"message": "Hello! Just say hi back.", "conversation_id": None}
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if "response" in data:
                print(f"   ✓ Chat successful!")
                print(f"   Response: {data['response'][:100]}...")
                return True
            else:
                print(f"   ✗ No response in data: {data}")
        else:
            print(f"   ✗ Chat failed: {response.text[:300]}")
    
    return False

if __name__ == "__main__":
    result = asyncio.run(test())
    exit(0 if result else 1)


