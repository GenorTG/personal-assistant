#!/usr/bin/env python3
"""Test script that mimics frontend behavior exactly.

This script:
1. Loads a model using the same API endpoint and format as the frontend
2. Makes a chat request using the same format as the frontend
3. Tests regenerate with the same sampler_params format as the frontend
4. Validates responses match what the frontend expects
"""
import time
import requests
import json
import sys
import os
import subprocess
import signal
import atexit
from typing import Optional, Dict, Any

# Add gateway src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Global variable to track gateway process
_gateway_process: Optional[subprocess.Popen] = None

BASE_URL = "http://localhost:8000"
LLM_SERVER_URL = "http://localhost:8001"

# Default model to test with (can be overridden via command line)
DEFAULT_MODEL = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"

# Sampler settings that match what frontend sends (with problematic stop tokens)
FRONTEND_SAMPLER_SETTINGS = {
    "temperature": 0.8,
    "top_p": 0.9,
    "top_k": 40,
    "min_p": 0,
    "repeat_penalty": 1.1,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "typical_p": 1,
    "tfs_z": 1,
    "mirostat_mode": 0,
    "mirostat_tau": 5,
    "mirostat_eta": 0.1,
    "max_tokens": 512,
    "stop": [
        "\n*{{user}}",
        "\n{{user}}",
        "{{user}}:",
        "User:"
    ]
}


def check_gateway_running() -> bool:
    """Check if gateway is already running."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2.0)
        return response.status_code == 200
    except:
        return False


def find_python_with_uvicorn() -> Optional[str]:
    """Find a Python interpreter that has uvicorn installed."""
    # Try current Python first
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "uvicorn", "--version"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return sys.executable
    except:
        pass
    
    # Try common venv locations
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    venv_paths = [
        os.path.join(project_root, "services", ".core_venv", "bin", "python"),
        os.path.join(project_root, ".venv", "bin", "python"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python"),
    ]
    
    for venv_python in venv_paths:
        if os.path.exists(venv_python):
            try:
                result = subprocess.run(
                    [venv_python, "-m", "uvicorn", "--version"],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    return venv_python
            except:
                pass
    
    return None


def start_gateway() -> Optional[subprocess.Popen]:
    """Start the gateway server in the background."""
    global _gateway_process
    
    print(f"[START] Starting gateway server...")
    
    # Find Python with uvicorn
    python_cmd = find_python_with_uvicorn()
    if not python_cmd:
        print(f"    ✗ Could not find Python with uvicorn installed")
        print(f"    Please ensure uvicorn is installed in your Python environment")
        print(f"    Or start the gateway manually and run the test again")
        return None
    
    # Get the gateway directory
    gateway_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Build command to start gateway
    cmd = [
        python_cmd,
        "-m", "uvicorn",
        "src.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--no-access-log"
    ]
    
    print(f"    Python: {python_cmd}")
    print(f"    Command: {' '.join(cmd)}")
    print(f"    Working directory: {gateway_dir}")
    
    try:
        # Start gateway in background
        # Use DEVNULL for output to avoid blocking, but allow stderr to go to terminal for debugging
        process = subprocess.Popen(
            cmd,
            cwd=gateway_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True
        )
        
        _gateway_process = process
        print(f"    ✓ Gateway process started (PID: {process.pid})")
        
        # Register cleanup function
        atexit.register(stop_gateway)
        
        return process
    except Exception as e:
        print(f"    ✗ Failed to start gateway: {e}")
        return None


def stop_gateway():
    """Stop the gateway server if we started it."""
    global _gateway_process
    
    if _gateway_process:
        print(f"\n[STOP] Stopping gateway server (PID: {_gateway_process.pid})...")
        try:
            # Try graceful shutdown first
            _gateway_process.terminate()
            try:
                _gateway_process.wait(timeout=5)
                print(f"    ✓ Gateway stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop
                print(f"    ⚠ Gateway didn't stop, forcing kill...")
                _gateway_process.kill()
                _gateway_process.wait()
                print(f"    ✓ Gateway force stopped")
        except Exception as e:
            print(f"    ✗ Error stopping gateway: {e}")
        finally:
            _gateway_process = None


def wait_for_gateway(max_wait: int = 60) -> bool:
    """Wait for gateway server to be ready."""
    print(f"[WAIT] Waiting for gateway at {BASE_URL}...")
    for i in range(max_wait):
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2.0)
            if response.status_code == 200:
                print(f"   ✓ Gateway is ready (waited {i+1}s)")
                return True
        except:
            pass
        if i % 5 == 0 and i > 0:
            print(f"   ... still waiting ({i+1}s)...")
        time.sleep(1)
    print(f"   ✗ Gateway not ready after {max_wait}s")
    return False


def wait_for_llm_server(max_wait: int = 90) -> bool:
    """Wait for LLM server to be ready."""
    print(f"[WAIT] Waiting for LLM server at {LLM_SERVER_URL}...")
    for i in range(max_wait):
        try:
            response = requests.get(f"{LLM_SERVER_URL}/v1/models", timeout=2.0)
            if response.status_code == 200:
                print(f"   ✓ LLM server is ready (waited {i+1}s)")
                return True
        except:
            pass
        if i % 5 == 0 and i > 0:
            print(f"   ... still waiting ({i+1}s)...")
        time.sleep(1)
    print(f"   ✗ LLM server not ready after {max_wait}s")
    return False


def load_model(model_id: str, options: Optional[Dict[str, Any]] = None) -> bool:
    """Load model using the same endpoint and format as frontend.
    
    Frontend uses: POST /api/models/{modelId}/load with options in body
    """
    print(f"\n[1] Loading model: {model_id}")
    print(f"    Options: {json.dumps(options or {}, indent=6)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/models/{model_id}/load",
            json=options or {},
            timeout=120.0
        )
        
        print(f"    Status: {response.status_code}")
        
        if response.status_code == 200:
            print("    ✓ Model load request successful")
            return True
        else:
            error_text = response.text[:500]
            print(f"    ✗ Failed: {error_text}")
            try:
                error_json = response.json()
                if "detail" in error_json:
                    print(f"    Detail: {error_json['detail']}")
            except:
                pass
            return False
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        return False


def send_chat_message(
    message: str,
    conversation_id: Optional[str] = None,
    sampler_settings: Optional[Dict[str, Any]] = None,
    include_logs: bool = True
) -> Optional[Dict[str, Any]]:
    """Send chat message using the same format as frontend.
    
    Frontend uses: POST /api/chat with body:
    {
        "message": "...",
        "conversation_id": "...",  // optional
        "temperature": ...,
        "top_p": ...,
        "stop": [...],
        // ... other sampler settings
    }
    """
    print(f"\n[2] Sending chat message...")
    print(f"    Message: {message[:50]}...")
    if conversation_id:
        print(f"    Conversation ID: {conversation_id}")
    if sampler_settings:
        print(f"    Sampler settings: {json.dumps(sampler_settings, indent=6)}")
    
    body: Dict[str, Any] = {
        "message": message
    }
    
    if conversation_id:
        body["conversation_id"] = conversation_id
    
    # Add sampler settings directly to body (not nested in sampler_params)
    if sampler_settings:
        for key, value in sampler_settings.items():
            if value is not None:
                body[key] = value
    
    headers = {}
    if include_logs:
        headers["X-Include-Logs"] = "true"
    
    # Print full request body
    print(f"\n    === REQUEST BODY ===")
    print(json.dumps(body, indent=4, default=str))
    print(f"    === END REQUEST BODY ===\n")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=body,
            headers=headers,
            timeout=60.0
        )
        
        print(f"    Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Print full response data for debugging
            print(f"\n    === FULL RESPONSE DATA ===")
            print(f"    Response keys: {list(data.keys())}")
            print(f"    Full response JSON:")
            print(json.dumps(data, indent=4, default=str))
            print(f"    === END FULL RESPONSE ===\n")
            
            # Check for response content
            if "response" in data:
                response_text = data["response"]
                print(f"    Response text: {repr(response_text)}")
                print(f"    Response length: {len(response_text) if response_text else 0} chars")
                print(f"    Response is empty: {not response_text or not response_text.strip()}")
                
                if response_text and response_text.strip():
                    print(f"    ✓ Chat successful!")
                    print(f"    Response preview: {response_text[:150]}...")
                    
                    # Check for empty response error
                    if "I apologize, but I couldn't generate a response" in response_text:
                        print(f"    ⚠ WARNING: Empty response fallback message detected!")
                        return None
                else:
                    print(f"    ✗ Empty response content!")
                
                # Show all logs - especially GENERATE, stop token, and parsing logs
                if "logs" in data and data["logs"]:
                    print(f"\n    === BACKEND LOGS ({len(data['logs'])} total) ===")
                    
                    # Categorize logs
                    generate_logs = [log for log in data["logs"] if "[GENERATE]" in log.get("message", "")]
                    stop_token_logs = [log for log in data["logs"] if "stop" in log.get("message", "").lower() or "token" in log.get("message", "").lower()]
                    parsing_logs = [log for log in data["logs"] if "parse" in log.get("message", "").lower() or "tool call" in log.get("message", "").lower()]
                    error_logs = [log for log in data["logs"] if log.get("level") in ["ERROR", "CRITICAL"]]
                    warning_logs = [log for log in data["logs"] if log.get("level") == "WARNING"]
                    
                    if generate_logs:
                        print(f"    [GENERATE] Logs ({len(generate_logs)}):")
                        for log in generate_logs:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    if stop_token_logs:
                        print(f"    Stop Token Logs ({len(stop_token_logs)}):")
                        for log in stop_token_logs:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    if parsing_logs:
                        print(f"    Parsing Logs ({len(parsing_logs)}):")
                        for log in parsing_logs:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    if warning_logs:
                        print(f"    Warnings ({len(warning_logs)}):")
                        for log in warning_logs[:10]:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    if error_logs:
                        print(f"    Errors ({len(error_logs)}):")
                        for log in error_logs:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    # Show metadata if available
                    if "metadata" in data:
                        print(f"\n    === METADATA ===")
                        print(json.dumps(data["metadata"], indent=4, default=str))
                    
                    print(f"    === END LOGS ===\n")
                
                if response_text and response_text.strip():
                    return data
                else:
                    print(f"    ✗ Empty response content")
                    if "logs" in data:
                        print(f"    Backend logs:")
                        for log in data.get("logs", [])[:5]:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    return None
            else:
                print(f"    ✗ No 'response' field in data")
                print(f"    Data keys: {list(data.keys())}")
                return None
        else:
            error_text = response.text[:500]
            print(f"    ✗ Chat failed: {error_text}")
            try:
                error_json = response.json()
                if "detail" in error_json:
                    print(f"    Detail: {error_json['detail']}")
            except:
                pass
            return None
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def regenerate_response(
    conversation_id: str,
    sampler_params: Optional[Dict[str, Any]] = None,
    include_logs: bool = True
) -> Optional[Dict[str, Any]]:
    """Regenerate response using the same format as frontend.
    
    Frontend uses: POST /api/chat/regenerate with body:
    {
        "conversation_id": "...",
        "sampler_params": {
            "temperature": ...,
            "stop": [...],
            // ... other sampler settings
        }
    }
    """
    print(f"\n[3] Regenerating response...")
    print(f"    Conversation ID: {conversation_id}")
    if sampler_params:
        print(f"    Sampler params: {json.dumps(sampler_params, indent=6)}")
    
    body: Dict[str, Any] = {
        "conversation_id": conversation_id
    }
    
    if sampler_params:
        body["sampler_params"] = sampler_params
    
    headers = {}
    if include_logs:
        headers["X-Include-Logs"] = "true"
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat/regenerate",
            json=body,
            headers=headers,
            timeout=60.0
        )
        
        print(f"    Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for response content
            if "response" in data:
                response_text = data["response"]
                if response_text and response_text.strip():
                    print(f"    ✓ Regenerate successful!")
                    print(f"    Response length: {len(response_text)} chars")
                    print(f"    Response preview: {response_text[:150]}...")
                    
                    # Check for empty response error
                    if "I apologize, but I couldn't generate a response" in response_text:
                        print(f"    ⚠ WARNING: Empty response fallback message detected!")
                        return None
                    
                    # Check logs if available
                    if "logs" in data and data["logs"]:
                        error_logs = [log for log in data["logs"] if log.get("level") in ["ERROR", "CRITICAL"]]
                        if error_logs:
                            print(f"    ⚠ WARNING: {len(error_logs)} error logs found:")
                            for log in error_logs[:3]:
                                print(f"      [{log.get('level')}] {log.get('message')}")
                    
                    return data
                else:
                    print(f"    ✗ Empty response content")
                    if "logs" in data:
                        print(f"    Backend logs:")
                        for log in data.get("logs", [])[:10]:
                            print(f"      [{log.get('level')}] {log.get('message')}")
                    return None
            else:
                print(f"    ✗ No 'response' field in data")
                print(f"    Data keys: {list(data.keys())}")
                return None
        else:
            error_text = response.text[:500]
            print(f"    ✗ Regenerate failed: {error_text}")
            try:
                error_json = response.json()
                if "detail" in error_json:
                    print(f"    Detail: {error_json['detail']}")
            except:
                pass
            return None
    except Exception as e:
        print(f"    ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_test(model_id: Optional[str] = None, keep_gateway_running: bool = False):
    """Run the full test flow.
    
    Args:
        model_id: Model to test (default: Qwen2.5-7B-Instruct-Q4_K_M.gguf)
        keep_gateway_running: If True, don't stop gateway after test (default: False)
    """
    model_id = model_id or DEFAULT_MODEL
    gateway_started_by_us = False
    
    print("=" * 70)
    print("FRONTEND FLOW TEST")
    print("=" * 70)
    print(f"Model: {model_id}")
    print(f"Gateway: {BASE_URL}")
    print(f"LLM Server: {LLM_SERVER_URL}")
    print("=" * 70)
    
    # Check if gateway is already running
    if check_gateway_running():
        print("\n[INFO] Gateway is already running")
    else:
        print("\n[INFO] Gateway is not running, starting it...")
        process = start_gateway()
        if not process:
            print("\n✗ Failed to start gateway server!")
            return False
        gateway_started_by_us = True
        
        # Wait for gateway to be ready (gateway can take a while to initialize services)
        if not wait_for_gateway(max_wait=120):
            print("\n✗ Gateway failed to start!")
            stop_gateway()
            return False
    
    # Load model (same as frontend)
    if not load_model(model_id, {"n_gpu_layers": -1}):
        return False
    
    # Wait for LLM server to be ready
    if not wait_for_llm_server():
        return False
    
    # Test 1: Send a chat message (same format as frontend)
    print("\n" + "=" * 70)
    print("TEST 1: Chat Message (Frontend Format)")
    print("=" * 70)
    
    chat_response = send_chat_message(
        message="Hi there! Just say hello back.",
        sampler_settings=FRONTEND_SAMPLER_SETTINGS
    )
    
    if not chat_response:
        print("\n✗ TEST 1 FAILED: Chat message returned empty or error")
        return False
    
    conversation_id = chat_response.get("conversation_id")
    if not conversation_id:
        print("\n✗ TEST 1 FAILED: No conversation_id in response")
        return False
    
    print(f"\n✓ TEST 1 PASSED: Got valid response with conversation_id: {conversation_id}")
    
    # Test 2: Regenerate with problematic stop tokens (same format as frontend)
    print("\n" + "=" * 70)
    print("TEST 2: Regenerate with Stop Tokens (Frontend Format)")
    print("=" * 70)
    
    regenerate_response_data = regenerate_response(
        conversation_id=conversation_id,
        sampler_params=FRONTEND_SAMPLER_SETTINGS
    )
    
    if not regenerate_response_data:
        print("\n✗ TEST 2 FAILED: Regenerate returned empty or error")
        return False
    
    print(f"\n✓ TEST 2 PASSED: Got valid regenerated response")
    
    # Test 3: Tool calling - calendar event (real use case)
    print("\n" + "=" * 70)
    print("TEST 3: Tool Calling (Calendar Event)")
    print("=" * 70)
    
    tool_chat_response = send_chat_message(
        message="Assistant, please add a meeting tomorrow for 2pm to 3pm called Important",
        conversation_id=None,  # New conversation for tool test
        sampler_settings=FRONTEND_SAMPLER_SETTINGS
    )
    
    if not tool_chat_response:
        print("\n✗ TEST 3 FAILED: Tool calling chat returned empty or error")
        return False
    
    # Check if tool calls were made
    tool_calls = tool_chat_response.get("tool_calls", [])
    response_text = tool_chat_response.get("response", "")
    
    print(f"\n    Response length: {len(response_text)} chars")
    print(f"    Tool calls: {len(tool_calls)}")
    print(f"    Response preview: {response_text[:200]}")
    
    if tool_calls:
        print(f"\n✓ TEST 3 PASSED: Model made {len(tool_calls)} tool call(s)")
        for i, tool_call in enumerate(tool_calls):
            func = tool_call.get("function", {})
            print(f"    Tool call {i+1}: {func.get('name')} with args: {func.get('arguments', {})}")
        
        # Check if we got a follow-up response
        if response_text and len(response_text) > 50:
            print(f"\n✓ TEST 3 PASSED: Got follow-up response after tool execution")
            print(f"    Follow-up: {response_text[:200]}")
        else:
            print(f"\n⚠ TEST 3 WARNING: Tool was called but no follow-up response")
    else:
        if response_text and len(response_text) > 50:
            print(f"\n⚠ TEST 3 WARNING: No tool calls detected, but got normal response")
            print(f"    This means tool_choice='auto' did NOT trigger tool usage")
            print(f"    Response: {response_text[:200]}")
            return False
        else:
            print(f"\n✗ TEST 3 FAILED: No tool calls AND empty/weak response")
            return False
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("✓ All tests passed!")
    print("=" * 70)
    
    # Cleanup: stop gateway if we started it
    if gateway_started_by_us and not keep_gateway_running:
        stop_gateway()
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test frontend flow")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Model ID to test (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--keep-gateway",
        action="store_true",
        help="Keep gateway running after test completes"
    )
    
    args = parser.parse_args()
    
    try:
        result = run_test(args.model, keep_gateway_running=args.keep_gateway)
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
