#!/usr/bin/env python3
"""Direct test of LLM server to see actual errors."""
import httpx
import json
import sys

def test_llm_server():
    url = "http://localhost:8001"
    
    print("=" * 60)
    print("DIRECT LLM SERVER TEST")
    print("=" * 60)
    
    # Test 1: Check if server is up
    print("\n[1] Checking server status...")
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{url}/v1/models")
            print(f"✓ Server is up (status: {resp.status_code})")
            if resp.status_code == 200:
                models = resp.json()
                print(f"  Models: {json.dumps(models, indent=2)}")
    except Exception as e:
        print(f"✗ Server check failed: {e}")
        return False
    
    # Test 2: Try a simple chat completion
    print("\n[2] Testing chat completion...")
    try:
        with httpx.Client(timeout=30.0) as client:
            payload = {
                "model": "test",
                "messages": [
                    {"role": "user", "content": "Say hello"}
                ],
                "max_tokens": 10
            }
            print(f"  Payload: {json.dumps(payload, indent=2)}")
            resp = client.post(f"{url}/v1/chat/completions", json=payload)
            print(f"  Status: {resp.status_code}")
            print(f"  Headers: {dict(resp.headers)}")
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ Chat completion successful!")
                print(f"  Response: {json.dumps(data, indent=2)[:500]}")
                return True
            else:
                print(f"✗ Chat completion failed")
                print(f"  Response text: {resp.text[:1000]}")
                try:
                    error_data = resp.json()
                    print(f"  Error JSON: {json.dumps(error_data, indent=2)}")
                except:
                    pass
                return False
    except httpx.HTTPStatusError as e:
        print(f"✗ HTTP error: {e}")
        print(f"  Response: {e.response.text[:1000]}")
        return False
    except Exception as e:
        print(f"✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_llm_server()
    sys.exit(0 if success else 1)


