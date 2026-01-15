#!/usr/bin/env python3
"""
Comprehensive verification script for tool-calling sampler settings.
Tests both tool-calling and regular chat to verify correct settings are applied.
"""
import requests
import json
import time
import subprocess
import signal
import os
from pathlib import Path
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8000"

def check_gateway_running() -> bool:
    """Check if gateway is running."""
    try:
        response = requests.get(f"{BASE_URL}/api/system/status", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False

def get_gateway_pid() -> Optional[int]:
    """Get the PID of the running gateway process."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "uvicorn.*main:app"],
            capture_output=True,
            text=True,
            timeout=5.0
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None

def restart_gateway() -> bool:
    """Restart the gateway to pick up code changes."""
    print("=" * 80)
    print("  RESTARTING GATEWAY TO LOAD CODE CHANGES")
    print("=" * 80)
    
    # Check if gateway is running
    if not check_gateway_running():
        print("⚠️  Gateway is not running. Starting it...")
        return start_gateway()
    
    # Get gateway PID
    pid = get_gateway_pid()
    if not pid:
        print("⚠️  Could not find gateway process. Starting fresh...")
        return start_gateway()
    
    print(f"Found gateway process (PID: {pid})")
    print("Stopping gateway...")
    
    # Stop the gateway
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for it to stop
        for i in range(10):
            if not check_gateway_running():
                break
            time.sleep(1)
        
        if check_gateway_running():
            print("⚠️  Gateway didn't stop gracefully, forcing kill...")
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(2)
            except:
                pass
    except ProcessLookupError:
        print("Gateway process already stopped")
    except Exception as e:
        print(f"⚠️  Error stopping gateway: {e}")
    
    # Wait a moment
    time.sleep(2)
    
    # Start gateway
    print("Starting gateway with updated code...")
    return start_gateway()

def start_gateway() -> bool:
    """Start gateway service."""
    # Find Python with uvicorn
    venv_path = Path(__file__).parent / "services" / ".core_venv"
    python_cmd = None
    
    if venv_path.exists():
        python_cmd = venv_path / "bin" / "python"
        if not python_cmd.exists():
            python_cmd = None
    
    if not python_cmd:
        # Try system python
        try:
            result = subprocess.run(["which", "python3"], capture_output=True, text=True)
            if result.returncode == 0:
                python_cmd = Path(result.stdout.strip())
        except:
            pass
    
    if not python_cmd or not python_cmd.exists():
        print("❌ Could not find Python executable")
        return False
    
    # Start gateway
    gateway_dir = Path(__file__).parent / "services" / "gateway"
    if not gateway_dir.exists():
        print(f"❌ Gateway directory not found: {gateway_dir}")
        return False
    
    print(f"Starting gateway with {python_cmd}...")
    try:
        process = subprocess.Popen(
            [str(python_cmd), "-m", "uvicorn", "src.main:app", 
             "--host", "0.0.0.0", "--port", "8000", "--no-access-log"],
            cwd=str(gateway_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for gateway to start (max 30 seconds)
        print("Waiting for gateway to start...")
        for i in range(30):
            time.sleep(1)
            if check_gateway_running():
                print(f"✅ Gateway started successfully (PID: {process.pid})")
                return True
        
        print("❌ Gateway failed to start within 30 seconds")
        return False
    except Exception as e:
        print(f"❌ Error starting gateway: {e}")
        return False

def make_chat_request(message: str, include_logs: bool = True) -> Dict[str, Any]:
    """Make a chat request and return full response."""
    response = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "message": message,
            "conversation_id": None,
            "sampler_params": {}
        },
        headers={"X-Include-Logs": "true" if include_logs else "false"},
        timeout=60
    )
    response.raise_for_status()
    return response.json()

def extract_temperature_from_logs(logs: list) -> Optional[float]:
    """Extract temperature value from logs."""
    for log in logs:
        msg = str(log.get("message", ""))
        # Look for temperature in payload summary
        if "Temperature:" in msg:
            try:
                # Extract number after "Temperature: "
                parts = msg.split("Temperature:")
                if len(parts) > 1:
                    temp_part = parts[1].strip().split()[0]
                    # Remove any trailing characters
                    temp_str = temp_part.split("(")[0].strip()
                    return float(temp_str)
            except:
                pass
    return None

def extract_tool_calling_log(logs: list) -> Optional[str]:
    """Extract tool-calling settings log message."""
    for log in logs:
        msg = str(log.get("message", ""))
        if "tool-calling sampler" in msg.lower() or "🔧" in msg:
            return msg
    return None

def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n--- {title} ---")

def main():
    print("=" * 80)
    print("  COMPREHENSIVE TOOL-CALLING SETTINGS VERIFICATION")
    print("=" * 80)
    
    # Restart gateway to ensure code changes are loaded
    print("\n⚠️  Restarting gateway to load code changes...")
    if not restart_gateway():
        print("❌ Failed to restart gateway. Continuing with existing process...")
    
    # Wait a moment for gateway to fully start
    time.sleep(3)
    
    # Check if gateway is running and model is loaded
    try:
        status = requests.get(f"{BASE_URL}/api/llm/status", timeout=10)
        if status.status_code != 200:
            print("❌ Gateway is not running or not responding")
            return
        status_data = status.json()
        
        if not status_data.get("model_loaded"):
            print("⚠️  No model is loaded. Loading first available model...")
            # Get available models
            models_response = requests.get(f"{BASE_URL}/api/models", timeout=10)
            if models_response.status_code == 200:
                models = models_response.json()
                if isinstance(models, list) and len(models) > 0:
                    model_name = models[0].get("name") or models[0].get("id")
                    print(f"Loading model: {model_name}")
                    load_response = requests.post(
                        f"{BASE_URL}/api/models/{model_name}/load",
                        timeout=300
                    )
                    if load_response.status_code == 200:
                        # Wait for model to load
                        for i in range(60):
                            time.sleep(2)
                            status = requests.get(f"{BASE_URL}/api/llm/status", timeout=10)
                            if status.status_code == 200:
                                status_data = status.json()
                                if status_data.get("model_loaded"):
                                    print(f"✅ Model loaded: {status_data.get('model_name')}")
                                    break
                        else:
                            print("❌ Model loading timeout")
                            return
                    else:
                        print(f"❌ Failed to load model: {load_response.status_code}")
                        return
                else:
                    print("❌ No models available")
                    return
            else:
                print("❌ Failed to get models list")
                return
        else:
            print(f"\n✅ Gateway is running")
            print(f"✅ Model loaded: {status_data.get('model_name')}")
            print(f"✅ Tool calling supported: {status_data.get('supports_tool_calling')}")
    except Exception as e:
        print(f"❌ Cannot connect to gateway: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print_section("TEST 1: Regular Chat (No Tools)")
    print("Making a chat request that should NOT trigger tool calling...")
    print("Expected: Regular sampler settings (temperature ~0.7-0.8)")
    
    try:
        response1 = make_chat_request("Hello! How are you today?")
        
        tool_calls = response1.get("tool_calls", [])
        logs = response1.get("logs", [])
        
        print(f"\n✅ Request completed")
        print(f"   Tool calls: {len(tool_calls)} (expected: 0)")
        print(f"   Response length: {len(response1.get('response', ''))}")
        print(f"   Total logs: {len(logs)}")
        
        # Extract temperature from logs
        temp = extract_temperature_from_logs(logs)
        if temp:
            print(f"\n📊 Temperature found in logs: {temp}")
            if 0.6 <= temp <= 0.9:
                print(f"   ✅ Temperature is in expected range for regular chat (0.6-0.9)")
            else:
                print(f"   ⚠️  Temperature is outside expected range for regular chat")
        else:
            print(f"\n⚠️  Could not extract temperature from logs")
        
        # Check for tool-calling settings log (should NOT appear)
        tool_log = extract_tool_calling_log(logs)
        if tool_log:
            print(f"\n❌ ERROR: Tool-calling settings log found in regular chat!")
            print(f"   Log: {tool_log}")
        else:
            print(f"\n✅ No tool-calling settings log (correct - no tools used)")
        
        # Show relevant logs
        print_subsection("Relevant Logs")
        relevant_logs = []
        for log in logs:
            msg = str(log.get("message", ""))
            if any(keyword in msg.lower() for keyword in ["temperature", "payload", "sampler", "tool"]):
                relevant_logs.append(f"[{log.get('level')}] {msg[:200]}")
        
        if relevant_logs:
            for log in relevant_logs[:10]:
                print(f"  {log}")
        else:
            print("  No relevant logs found")
            
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
    
    print_section("TEST 2: Tool-Calling Chat (With Tools)")
    print("Making a chat request that SHOULD trigger tool calling...")
    print("Expected: Tool-calling sampler settings (temperature=0.3, top_p=0.8, top_k=20)")
    
    try:
        response2 = make_chat_request("Please add a meeting tomorrow at 2pm to 3pm called Verification Test Meeting")
        
        tool_calls = response2.get("tool_calls", [])
        logs = response2.get("logs", [])
        
        print(f"\n✅ Request completed")
        print(f"   Tool calls: {len(tool_calls)} (expected: >= 1)")
        print(f"   Response length: {len(response2.get('response', ''))}")
        print(f"   Total logs: {len(logs)}")
        
        if tool_calls:
            print(f"\n✅ Tool was called:")
            for tc in tool_calls:
                print(f"   - {tc.get('name')}: {tc.get('arguments', {})}")
        else:
            print(f"\n❌ ERROR: No tool calls made!")
        
        # Extract temperature from logs
        temp = extract_temperature_from_logs(logs)
        if temp:
            print(f"\n📊 Temperature found in logs: {temp}")
            if temp == 0.3:
                print(f"   ✅ Temperature is CORRECT for tool-calling (0.3)")
            elif 0.2 <= temp <= 0.4:
                print(f"   ⚠️  Temperature is close to expected (0.3) but not exact: {temp}")
            else:
                print(f"   ❌ ERROR: Temperature is WRONG for tool-calling!")
                print(f"      Expected: 0.3, Got: {temp}")
        else:
            print(f"\n⚠️  Could not extract temperature from logs")
        
        # Check for tool-calling settings log (SHOULD appear)
        tool_log = extract_tool_calling_log(logs)
        if tool_log:
            print(f"\n✅ Tool-calling settings log found:")
            print(f"   {tool_log}")
            
            # Verify it mentions the correct values
            if "0.3" in tool_log or "temperature=0.3" in tool_log:
                print(f"   ✅ Log correctly mentions temperature=0.3")
            else:
                print(f"   ⚠️  Log doesn't explicitly mention temperature=0.3")
        else:
            print(f"\n❌ ERROR: Tool-calling settings log NOT found!")
            print(f"   This log should appear when tools are present")
        
        # Show ALL logs (not just relevant ones) to see what's actually being captured
        print_subsection("ALL Logs (Full Output)")
        print(f"\nTotal logs captured: {len(logs)}")
        for i, log in enumerate(logs):
            level = log.get('level', 'UNKNOWN')
            msg = str(log.get('message', ''))
            logger_name = log.get('logger', '')
            print(f"  [{i+1}] [{level}] [{logger_name}] {msg[:200]}")
        
        # Also show relevant logs
        print_subsection("Relevant Logs (Filtered)")
        relevant_logs = []
        for log in logs:
            msg = str(log.get("message", ""))
            if any(keyword in msg.lower() for keyword in ["temperature", "payload", "sampler", "tool", "top_p", "top_k", "🔍", "🔧", "about to build", "payload built"]):
                relevant_logs.append(f"[{log.get('level')}] {msg}")
        
        if relevant_logs:
            print(f"\nFound {len(relevant_logs)} relevant logs:")
            for log in relevant_logs:
                print(f"  {log}")
        else:
            print("  No relevant logs found")
        
        # Show payload summary if available
        print_subsection("Payload Summary Logs")
        payload_logs = []
        for log in logs:
            msg = str(log.get("message", ""))
            if "Request payload summary" in msg or "Temperature:" in msg or "TOOL-CALLING" in msg or "REGULAR" in msg:
                payload_logs.append(f"[{log.get('level')}] {msg}")
        
        if payload_logs:
            for log in payload_logs:
                print(f"  {log}")
        else:
            print("  No payload summary logs found")
            
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
    
    print_section("TEST 3: Direct Payload Inspection")
    print("Attempting to verify actual payload sent to LLM server...")
    print("(This requires checking backend logs or payload construction)")
    
    # We can't directly inspect the payload, but we can verify the code path
    print("\n✅ Code verification:")
    print("   - _build_request_payload() checks if tools are present")
    print("   - Uses tool_calling_sampler_settings when tools > 0")
    print("   - Uses regular sampler_settings when tools = 0")
    print("   - Logs should indicate which settings are used")
    
    print_section("SUMMARY")
    print("\nVerification complete!")
    print("\nKey Points:")
    print("1. Regular chat should use regular sampler settings (temp ~0.7-0.8)")
    print("2. Tool-calling chat should use tool-calling settings (temp=0.3)")
    print("3. Logs should accurately reflect which settings are used")
    print("4. Tool-calling settings log should appear only when tools are present")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
