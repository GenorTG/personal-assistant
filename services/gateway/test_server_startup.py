#!/usr/bin/env python3
"""Test script to diagnose server startup issues with real-time logging."""
import subprocess
import time
import httpx
import json
import sys
import threading
from pathlib import Path

def read_output(proc, output_lines):
    """Read subprocess output in real-time."""
    try:
        for line in proc.stdout:
            if line:
                line = line.rstrip()
                print(f"[SERVER] {line}")
                output_lines.append(line)
    except Exception as e:
        print(f"[ERROR] Failed to read output: {e}")

def main():
    model_path = "/home/genortg/Github Personal/personal-assistant/data/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    port = 8043
    
    print("=" * 80)
    print("Testing llama-cpp-python server startup")
    print("=" * 80)
    print(f"Model: {model_path}")
    print(f"Port: {port}")
    print()
    
    # Build command - EXACT working manual test command
    cmd = [
        sys.executable,
        "-m", "llama_cpp.server",
        "--model", model_path,
        "--host", "127.0.0.1",
        "--port", str(port),
        "--n_ctx", "2048",
        "--n_gpu_layers", "-1",
        "--chat_format", "chatml-function-calling"
    ]
    
    print("Command:")
    print(" ".join(cmd))
    print()
    print("Starting server...")
    print("-" * 80)
    
    # Start server
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Read output in real-time
    output_lines = []
    output_thread = threading.Thread(target=read_output, args=(proc, output_lines), daemon=True)
    output_thread.start()
    
    # Wait for server to start
    max_wait = 120  # 2 minutes
    start_time = time.time()
    server_ready = False
    
    print(f"Waiting for server to start (max {max_wait}s)...")
    
    while time.time() - start_time < max_wait:
        if proc.poll() is not None:
            print(f"\n[ERROR] Server process exited with code {proc.returncode}")
            print("Last output:")
            for line in output_lines[-20:]:
                print(f"  {line}")
            return 1
        
        # Check if server is responding
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(f"http://127.0.0.1:{port}/v1/models")
                if r.status_code == 200:
                    print(f"\n[SUCCESS] Server is ready after {time.time() - start_time:.1f}s")
                    server_ready = True
                    break
        except Exception:
            pass
        
        time.sleep(1)
        if int(time.time() - start_time) % 5 == 0:
            elapsed = int(time.time() - start_time)
            print(f"[WAIT] Still waiting... ({elapsed}s elapsed)")
    
    if not server_ready:
        print(f"\n[ERROR] Server failed to start within {max_wait}s")
        proc.terminate()
        proc.wait()
        return 1
    
    print()
    print("=" * 80)
    print("Testing simple request (no tools)")
    print("=" * 80)
    
    # Test 1: Simple request
    try:
        with httpx.Client(timeout=30.0) as client:
            payload = {
                "model": "test",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10
            }
            print(f"Sending request: {json.dumps(payload, indent=2)}")
            r = client.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=payload)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                result = r.json()
                print("✅ Simple request works!")
                print(f"Response: {json.dumps(result, indent=2)[:500]}")
            else:
                print(f"❌ Error: {r.text[:500]}")
                return 1
    except Exception as e:
        print(f"❌ Exception: {e}")
        proc.terminate()
        proc.wait()
        return 1
    
    print()
    print("=" * 80)
    print("Testing function calling request")
    print("=" * 80)
    
    # Test 2: Function calling
    try:
        with httpx.Client(timeout=60.0) as client:
            payload = {
                "model": "test",
                "messages": [
                    {
                        "role": "system",
                        "content": "A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. The assistant calls functions with appropriate input when necessary"
                    },
                    {
                        "role": "user",
                        "content": "Add 3 and 5 using add_numbers"
                    }
                ],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "add_numbers",
                        "parameters": {
                            "type": "object",
                            "title": "add_numbers",
                            "properties": {
                                "a": {"title": "A", "type": "integer"},
                                "b": {"title": "B", "type": "integer"}
                            },
                            "required": ["a", "b"]
                        }
                    }
                }],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "add_numbers"}
                },
                "temperature": 0.0,
                "max_tokens": 200
            }
            print(f"Sending request with tools...")
            r = client.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=payload)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                result = r.json()
                message = result.get("choices", [{}])[0].get("message", {})
                if "tool_calls" in message:
                    print("✅✅✅ TOOL CALLS WORK! ✅✅✅")
                    print(json.dumps(message.get("tool_calls"), indent=2))
                    success = True
                else:
                    print("❌ No tool_calls in response")
                    print(f"Message: {json.dumps(message, indent=2)[:500]}")
                    success = False
            else:
                print(f"❌ Error: {r.text[:500]}")
                try:
                    error_json = r.json()
                    print(f"Error details: {json.dumps(error_json, indent=2)}")
                except:
                    pass
                success = False
            
            if success:
                print()
                print("=" * 80)
                print("✅ ALL TESTS PASSED!")
                print("=" * 80)
            else:
                print()
                print("=" * 80)
                print("❌ FUNCTION CALLING TEST FAILED")
                print("=" * 80)
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    # Cleanup
    print()
    print("Stopping server...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
        print("Server stopped")
    except subprocess.TimeoutExpired:
        print("Server didn't stop gracefully, killing...")
        proc.kill()
        proc.wait()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
