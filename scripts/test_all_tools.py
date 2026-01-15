#!/usr/bin/env python3
"""
Comprehensive test script for ALL tool functionality.
Tests tools using the EXACT SAME API endpoints and request format as the frontend.
"""
import json
import os
import subprocess
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_URL = "http://localhost:8000"
TIMEOUT = 300.0  # 5 minutes for model loading

class ToolTester:
    """Test all tools systematically using frontend API format."""
    
    def __init__(self):
        self.results = []
        self.model_name = None
        self.model_loaded = False
        # Track created resources for cleanup
        self.created_event_ids = []
        self.created_todo_ids = []
        self.created_conversation_ids = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️",
            "TEST": "🧪"
        }.get(level, "ℹ️")
        print(f"[{timestamp}] {prefix} {message}")
        
    def log_result(self, test_name: str, success: bool, details: Optional[Dict[str, Any]] = None):
        """Log test result."""
        result = {
            "test": test_name,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.results.append(result)
        if success:
            self.log(f"PASS: {test_name}", "SUCCESS")
        else:
            self.log(f"FAIL: {test_name}", "ERROR")
            if details:
                self.log(f"  Details: {json.dumps(details, indent=2)}", "ERROR")
    
    def check_gateway_running(self) -> bool:
        """Check if gateway is running."""
        try:
            response = requests.get(f"{BASE_URL}/api/system/status", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def stop_gateway(self) -> bool:
        """Stop gateway service if running."""
        if not self.check_gateway_running():
            return True
        
        self.log("Stopping gateway to pick up code changes...", "WARNING")
        try:
            # Find and kill uvicorn process
            result = subprocess.run(
                ["pgrep", "-f", "uvicorn src.main:app --host 0.0.0.0 --port 8000"],
                capture_output=True, text=True
            )
            pids = [int(p) for p in result.stdout.strip().split('\n') if p]
            for pid in pids:
                try:
                    os.kill(pid, 15)  # SIGTERM
                except:
                    pass
            # Wait a moment for graceful shutdown
            time.sleep(3)
            # Verify it's stopped
            for _ in range(10):
                if not self.check_gateway_running():
                    return True
                time.sleep(0.5)
            # Force kill if still running
            for pid in pids:
                try:
                    os.kill(pid, 9)  # SIGKILL
                except:
                    pass
            time.sleep(1)
            return True
        except Exception as e:
            self.log(f"Error stopping gateway: {e}", "WARNING")
            return False
    
    def start_gateway(self) -> bool:
        """Start gateway service if not running. Always restarts to pick up changes."""
        self.log("Checking if gateway is running...")
        if self.check_gateway_running():
            self.log("Gateway is running. Restarting to pick up code changes...", "WARNING")
            self.stop_gateway()
            time.sleep(1)  # Brief pause before restart
        
        self.log("Gateway not running. Attempting to start it...", "WARNING")
        
        # Try to start gateway automatically
        
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
            self.log("Could not find Python executable. Please start gateway manually.", "ERROR")
            return False
        
        # Check if uvicorn is available
        try:
            result = subprocess.run([str(python_cmd), "-m", "uvicorn", "--version"], 
                                  capture_output=True, timeout=5.0)
            if result.returncode != 0:
                self.log("uvicorn not found. Please start gateway manually.", "ERROR")
                return False
        except:
            self.log("Could not verify uvicorn. Please start gateway manually.", "ERROR")
            return False
        
        # Start gateway
        gateway_dir = Path(__file__).parent / "services" / "gateway"
        if not gateway_dir.exists():
            self.log(f"Gateway directory not found: {gateway_dir}", "ERROR")
            return False
        
        self.log(f"Starting gateway with {python_cmd}...")
        try:
            process = subprocess.Popen(
                [str(python_cmd), "-m", "uvicorn", "src.main:app", 
                 "--host", "0.0.0.0", "--port", "8000", "--no-access-log"],
                cwd=str(gateway_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait for gateway to start (max 30 seconds)
            self.log("Waiting for gateway to start...")
            for _ in range(30):
                time.sleep(1)
                if self.check_gateway_running():
                    self.log(f"Gateway started successfully (PID: {process.pid})", "SUCCESS")
                    return True
            
            self.log("Gateway failed to start within 30 seconds", "ERROR")
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
            return False
        except Exception as e:
            self.log(f"Failed to start gateway: {e}", "ERROR")
            return False
    
    def list_available_models(self) -> List[str]:
        """List available models."""
        try:
            response = requests.get(f"{BASE_URL}/api/models", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                models = data
            elif isinstance(data, dict):
                models = data.get("models", [])
            else:
                models = []
            
            model_names = []
            for m in models:
                if isinstance(m, dict):
                    model_names.append(m.get("id") or m.get("name"))
                elif isinstance(m, str):
                    model_names.append(m)
            
            return [m for m in model_names if m]
        except Exception as e:
            self.log(f"Error listing models: {e}", "ERROR")
            return []
    
    def load_model(self, model_name: str) -> bool:
        """Load a model using the EXACT same endpoint as frontend."""
        self.log(f"Loading model: {model_name}")
        try:
            # Frontend uses: POST /api/models/{modelId}/load
            response = requests.post(
                f"{BASE_URL}/api/models/{model_name}/load",
                json={},  # Frontend sends empty JSON
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            
            # Wait for model to load
            if data.get("status") == "loading":
                self.log("Model is loading, waiting for completion...")
                max_wait = 300  # 5 minutes
                waited = 0
                while waited < max_wait:
                    time.sleep(2)
                    status_response = requests.get(f"{BASE_URL}/api/llm/status", timeout=10.0)
                    status_data = status_response.json()
                    if status_data.get("model_loaded"):
                        self.log("Model loaded successfully", "SUCCESS")
                        self.model_loaded = True
                        self.model_name = model_name
                        return True
                    waited += 2
                
                self.log("Model loading timeout", "ERROR")
                return False
            else:
                self.model_loaded = True
                self.model_name = model_name
                return True
        except Exception as e:
            self.log(f"Error loading model: {e}", "ERROR")
            return False
    
    def test_list_tools(self) -> bool:
        """Test listing all available tools."""
        self.log("Testing: List Tools", "TEST")
        try:
            # Frontend uses: GET /api/tools
            response = requests.get(f"{BASE_URL}/api/tools", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            tools = data.get("tools", [])
            tool_count = data.get("count", 0)
            
            self.log(f"Found {tool_count} tools:")
            for tool in tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "")[:60]
                self.log(f"  - {name}: {desc}")
            
            self.log_result("List Tools", True, {"count": tool_count, "tools": [t.get("name") for t in tools]})
            return True
        except Exception as e:
            self.log_result("List Tools", False, {"error": str(e)})
            return False
    
    def test_tool_execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool using EXACT frontend format."""
        try:
            # Frontend uses: POST /api/tools/execute
            # Body: { "tool_name": "...", "parameters": {...} }
            response = requests.post(
                f"{BASE_URL}/api/tools/execute",
                json={
                    "tool_name": tool_name,
                    "parameters": parameters
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "result": None}
    
    # ========== CALENDAR TOOL TESTS ==========
    
    def test_calendar_list(self) -> bool:
        """Test calendar list action."""
        self.log("Testing: Calendar - List Events", "TEST")
        result = self.test_tool_execute("calendar", {"action": "list"})
        
        if "error" in result and result["error"]:
            self.log_result("Calendar - List", False, result)
            return False
        
        events = result.get("result", {}).get("events", [])
        self.log(f"Found {len(events)} calendar events")
        self.log_result("Calendar - List", True, {"event_count": len(events)})
        return True
    
    def test_calendar_create(self) -> bool:
        """Test calendar create action."""
        self.log("Testing: Calendar - Create Event", "TEST")
        
        # Create event for tomorrow at 2pm-3pm
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        end_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0).isoformat()
        
        result = self.test_tool_execute("calendar", {
            "action": "create",
            "title": "Test Meeting",
            "start_time": start_time,
            "end_time": end_time,
            "description": "Test event created by tool tester",
            "location": "Test Location"
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Create", False, result)
            return False
        
        event = result.get("result", {}).get("event")
        if not event:
            self.log_result("Calendar - Create", False, {"error": "No event in result", "result": result})
            return False
        
        event_id = event.get("id")
        conflicts = result.get("result", {}).get("conflicts", [])
        has_conflicts = result.get("result", {}).get("has_conflicts", False)
        
        # VERIFY: Check that the event was actually created with correct data
        if not event_id:
            self.log_result("Calendar - Create", False, {"error": "Event ID missing"})
            return False
        
        # Verify event data matches what we sent
        expected_title = "Test Meeting"
        if event.get("title") != expected_title:
            self.log_result("Calendar - Create", False, {
                "error": f"Title mismatch: expected '{expected_title}', got '{event.get('title')}'"
            })
            return False
        
        # Verify times are correct (parse and compare dates, allow for timezone)
        event_start = event.get("start_time", "")
        event_end = event.get("end_time", "")
        if not event_start or not event_end:
            self.log_result("Calendar - Create", False, {"error": "Start or end time missing"})
            return False
        
        try:
            parsed_start = datetime.fromisoformat(event_start.replace("Z", "+00:00"))
            _parsed_end = datetime.fromisoformat(event_end.replace("Z", "+00:00"))  # Available for future end time validation
            expected_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            _expected_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))  # Available for future end time validation
            
            # Compare dates (ignore timezone for date comparison)
            if parsed_start.date() != expected_start.date():
                self.log_result("Calendar - Create", False, {
                    "error": f"Start date mismatch: expected {expected_start.date()}, got {parsed_start.date()}"
                })
                return False
            
            # Verify times are approximately correct (within 1 hour tolerance for timezone)
            start_hour_diff = abs((parsed_start.replace(tzinfo=None) - expected_start.replace(tzinfo=None)).total_seconds() / 3600)
            if start_hour_diff > 1:
                self.log_result("Calendar - Create", False, {
                    "error": f"Start time too far off: expected ~{expected_start}, got {parsed_start}"
                })
                return False
        except Exception as e:
            self.log(f"⚠️  Could not verify times precisely: {e}", "WARNING")
        
        # Verify description and location
        expected_desc = "Test event created by tool tester"
        if event.get("description") != expected_desc:
            self.log_result("Calendar - Create", False, {
                "error": f"Description mismatch: expected '{expected_desc}', got '{event.get('description')}'"
            })
            return False
        
        expected_location = "Test Location"
        if event.get("location") != expected_location:
            self.log_result("Calendar - Create", False, {
                "error": f"Location mismatch: expected '{expected_location}', got '{event.get('location')}'"
            })
            return False
        
        # Track for cleanup
        if event_id:
            self.created_event_ids.append(event_id)
        
        self.log(f"Created event: {event.get('title')} (ID: {event_id})")
        self.log(f"  Verified: title={event.get('title')}, start={event_start[:19]}, end={event_end[:19]}")
        if has_conflicts:
            self.log(f"⚠️  Event has {len(conflicts)} conflicts", "WARNING")
        
        self.log_result("Calendar - Create", True, {
            "event_id": event_id,
            "title": event.get("title"),
            "has_conflicts": has_conflicts,
            "verified": True
        })
        return True
    
    def test_calendar_get(self, event_id: str) -> bool:
        """Test calendar get action."""
        self.log(f"Testing: Calendar - Get Event ({event_id})", "TEST")
        
        result = self.test_tool_execute("calendar", {
            "action": "get",
            "event_id": event_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Get", False, result)
            return False
        
        event = result.get("result")
        if not event:
            self.log_result("Calendar - Get", False, {"error": "No event in result"})
            return False
        
        # VERIFY: Check that we got the correct event
        if event.get("id") != event_id:
            self.log_result("Calendar - Get", False, {
                "error": f"Event ID mismatch: expected {event_id}, got {event.get('id')}"
            })
            return False
        
        # Verify event has required fields
        required_fields = ["title", "start_time", "end_time"]
        for field in required_fields:
            if not event.get(field):
                self.log_result("Calendar - Get", False, {
                    "error": f"Missing required field: {field}"
                })
                return False
        
        self.log(f"Retrieved event: {event.get('title')}")
        self.log(f"  Verified: ID matches, all required fields present")
        self.log_result("Calendar - Get", True, {
            "event_id": event_id,
            "verified": True
        })
        return True
    
    def test_calendar_update(self, event_id: str) -> bool:
        """Test calendar update action."""
        self.log(f"Testing: Calendar - Update Event ({event_id})", "TEST")
        
        new_title = "Updated Test Meeting"
        new_description = "Updated description"
        
        result = self.test_tool_execute("calendar", {
            "action": "update",
            "event_id": event_id,
            "title": new_title,
            "description": new_description
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Update", False, result)
            return False
        
        event = result.get("result", {}).get("event")
        if not event:
            self.log_result("Calendar - Update", False, {"error": "No event in result"})
            return False
        
        # VERIFY: Check that the event was actually updated
        if event.get("title") != new_title:
            self.log_result("Calendar - Update", False, {
                "error": f"Title not updated: expected '{new_title}', got '{event.get('title')}'"
            })
            return False
        
        if event.get("description") != new_description:
            self.log_result("Calendar - Update", False, {
                "error": f"Description not updated: expected '{new_description}', got '{event.get('description')}'"
            })
            return False
        
        # Double-check by fetching the event again
        verify_result = self.test_tool_execute("calendar", {
            "action": "get",
            "event_id": event_id
        })
        
        if verify_result.get("error"):
            self.log_result("Calendar - Update", False, {
                "error": f"Could not verify update: {verify_result.get('error')}"
            })
            return False
        
        verified_event = verify_result.get("result")
        if verified_event.get("title") != new_title or verified_event.get("description") != new_description:
            self.log_result("Calendar - Update", False, {
                "error": "Update not persisted - fetched event doesn't match updated values"
            })
            return False
        
        self.log(f"Updated event: {event.get('title')}")
        self.log(f"  Verified: title and description updated and persisted")
        self.log_result("Calendar - Update", True, {
            "event_id": event_id,
            "verified": True
        })
        return True
    
    def test_calendar_check_conflicts(self) -> bool:
        """Test calendar check_conflicts action."""
        self.log("Testing: Calendar - Check Conflicts", "TEST")
        
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        end_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0).isoformat()
        
        result = self.test_tool_execute("calendar", {
            "action": "check_conflicts",
            "start_time": start_time,
            "end_time": end_time
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Check Conflicts", False, result)
            return False
        
        available = result.get("result", {}).get("available", False)
        conflicts = result.get("result", {}).get("conflicts", [])
        
        self.log(f"Time slot available: {available}, Conflicts: {len(conflicts)}")
        self.log_result("Calendar - Check Conflicts", True, {
            "available": available,
            "conflict_count": len(conflicts)
        })
        return True
    
    def test_calendar_all_day(self) -> bool:
        """Test calendar all-day event creation."""
        self.log("Testing: Calendar - All Day Event", "TEST")
        
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_time = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        result = self.test_tool_execute("calendar", {
            "action": "create",
            "title": "All Day Test Event",
            "start_time": start_time,
            "end_time": end_time,
            "all_day": True
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - All Day", False, result)
            return False
        
        event = result.get("result", {}).get("event")
        if not event:
            self.log_result("Calendar - All Day", False, {"error": "No event in result"})
            return False
        
        # VERIFY: Check that all_day flag is set
        if not event.get("all_day"):
            self.log_result("Calendar - All Day", False, {
                "error": "Event not marked as all_day",
                "event": event
            })
            return False
        
        # Verify times are set to full day (00:00:00 to 23:59:59)
        try:
            event_start = datetime.fromisoformat(event.get("start_time", "").replace("Z", "+00:00"))
            event_end = datetime.fromisoformat(event.get("end_time", "").replace("Z", "+00:00"))
            
            # All-day events should span the full day
            if event_start.hour != 0 or event_start.minute != 0:
                self.log(f"⚠️  Warning: All-day event start time is not 00:00: {event_start}", "WARNING")
            
            if event_end.hour != 23 or (event_end.minute != 59 and event_end.second < 59):
                self.log(f"⚠️  Warning: All-day event end time is not 23:59:59: {event_end}", "WARNING")
        except Exception as e:
            self.log(f"⚠️  Could not verify all-day times: {e}", "WARNING")
        
        # Track for cleanup
        event_id = event.get("id")
        if event_id:
            self.created_event_ids.append(event_id)
        
        self.log("Created all-day event successfully")
        self.log_result("Calendar - All Day", True, {"event_id": event_id})
        return True
    
    def test_calendar_delete_day(self) -> bool:
        """Test calendar delete_day action."""
        self.log("Testing: Calendar - Delete Day", "TEST")
        
        tomorrow = datetime.now() + timedelta(days=1)
        date_str = tomorrow.strftime("%Y-%m-%d")
        
        result = self.test_tool_execute("calendar", {
            "action": "delete_day",
            "date": date_str
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Delete Day", False, result)
            return False
        
        deleted_count = result.get("result", {}).get("deleted_count", 0)
        self.log(f"Deleted {deleted_count} events from {date_str}")
        self.log_result("Calendar - Delete Day", True, {"deleted_count": deleted_count})
        return True
    
    def test_calendar_delete(self, event_id: str) -> bool:
        """Test calendar delete action."""
        self.log(f"Testing: Calendar - Delete Event ({event_id})", "TEST")
        
        result = self.test_tool_execute("calendar", {
            "action": "delete",
            "event_id": event_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Calendar - Delete", False, result)
            return False
        
        # VERIFY: Check that the event was actually deleted
        # Try to get the event - it should fail
        verify_result = self.test_tool_execute("calendar", {
            "action": "get",
            "event_id": event_id
        })
        
        if not verify_result.get("error"):
            # Event still exists - deletion failed!
            self.log_result("Calendar - Delete", False, {
                "error": "Event still exists after deletion - delete did not work"
            })
            return False
        
        # Also verify it's not in the list
        list_result = self.test_tool_execute("calendar", {"action": "list"})
        events = list_result.get("result", {}).get("events", [])
        event_ids = [e.get("id") for e in events if e.get("id")]
        
        if event_id in event_ids:
            self.log_result("Calendar - Delete", False, {
                "error": "Event still appears in list after deletion"
            })
            return False
        
        self.log(f"Deleted event: {event_id}")
        self.log(f"  Verified: event no longer exists (get failed, not in list)")
        self.log_result("Calendar - Delete", True, {
            "event_id": event_id,
            "verified": True
        })
        return True
    
    # ========== TIME TOOL TESTS ==========
    
    def test_time_tool(self) -> bool:
        """Test time tool."""
        self.log("Testing: Time Tool - Get Current Time", "TEST")
        
        result = self.test_tool_execute("get_current_time", {})
        
        if "error" in result and result.get("error"):
            self.log_result("Time Tool", False, result)
            return False
        
        time_str = result.get("result")
        if not time_str:
            self.log_result("Time Tool", False, {"error": "No time in result"})
            return False
        
        # VERIFY: Check that the time is valid and recent
        try:
            parsed_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            # Get current UTC time for comparison
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            
            # If parsed time has timezone, compare with timezone awareness
            if parsed_time.tzinfo:
                time_diff = abs((now_utc - parsed_time).total_seconds())
            else:
                # If no timezone, assume it's UTC and compare
                parsed_time_utc = parsed_time.replace(tzinfo=timezone.utc)
                time_diff = abs((now_utc - parsed_time_utc).total_seconds())
            
            # Time should be within last 60 seconds (reasonable for API call)
            if time_diff > 60:
                self.log_result("Time Tool", False, {
                    "error": f"Time seems too old: {time_str} (diff: {time_diff}s)",
                    "result": result
                })
                return False
            
            # Verify it's in ISO format
            if "T" not in time_str or len(time_str) < 19:
                self.log_result("Time Tool", False, {
                    "error": f"Time not in ISO format: {time_str}",
                    "result": result
                })
                return False
        except Exception as e:
            self.log_result("Time Tool", False, {
                "error": f"Could not parse time: {e}",
                "result": result
            })
            return False
        
        self.log(f"Current time: {time_str}")
        self.log(f"  Verified: valid ISO format, recent timestamp")
        self.log_result("Time Tool", True, {
            "time": time_str,
            "verified": True
        })
        return True
    
    # ========== BENCHMARK TOOL TESTS ==========
    
    def test_benchmark_tool(self) -> bool:
        """Test benchmark tool (add_numbers)."""
        self.log("Testing: Benchmark Tool - Add Numbers", "TEST")
        
        a, b = 5, 3
        expected = 8
        
        result = self.test_tool_execute("add_numbers", {
            "a": a,
            "b": b
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Benchmark Tool", False, result)
            return False
        
        sum_result = result.get("result")
        
        # VERIFY: Check the actual calculation result
        if sum_result != expected:
            self.log_result("Benchmark Tool", False, {
                "error": f"Calculation failed: {a} + {b} = {sum_result}, expected {expected}",
                "result": result
            })
            return False
        
        # Verify it's actually a number
        if not isinstance(sum_result, (int, float)):
            self.log_result("Benchmark Tool", False, {
                "error": f"Result is not a number: {type(sum_result)}",
                "result": result
            })
            return False
        
        self.log(f"{a} + {b} = {sum_result} ✓")
        self.log_result("Benchmark Tool", True, {
            "result": sum_result,
            "verified": True
        })
        return True
    
    # ========== GOOGLE SEARCH TOOL TESTS ==========
    
    def test_google_search(self) -> bool:
        """Test Google Search tool."""
        self.log("Testing: Google Search Tool", "TEST")
        
        query = "Python programming"
        result = self.test_tool_execute("google_search", {
            "query": query
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Google Search", False, result)
            return False
        
        search_results = result.get("result", {})
        results_list = search_results.get("results", [])
        
        # VERIFY: Check that we got actual search results
        if not results_list:
            self.log_result("Google Search", False, {
                "error": "No search results returned",
                "result": result
            })
            return False
        
        # Verify results have expected structure
        if not isinstance(results_list, list):
            self.log_result("Google Search", False, {
                "error": f"Results is not a list: {type(results_list)}",
                "result": result
            })
            return False
        
        # Check that at least one result has relevant fields
        has_valid_result = False
        for res in results_list[:3]:  # Check first 3 results
            if isinstance(res, dict):
                # Check for common search result fields
                if res.get("title") or res.get("snippet") or res.get("url") or res.get("link"):
                    has_valid_result = True
                    break
        
        if not has_valid_result:
            self.log_result("Google Search", False, {
                "error": "Results don't have expected structure (title/snippet/url)",
                "result": result
            })
            return False
        
        # Verify results are related to the query (basic check)
        found_relevant = False
        for res in results_list[:3]:
            title = (res.get("title") or "").lower()
            snippet = (res.get("snippet") or "").lower()
            if "python" in title or "python" in snippet:
                found_relevant = True
                break
        
        if not found_relevant:
            self.log(f"⚠️  Warning: No results found containing 'python' in title/snippet", "WARNING")
        
        self.log(f"Search completed: {len(results_list)} results")
        self.log(f"  Verified: {len(results_list)} results with valid structure")
        self.log_result("Google Search", True, {
            "result_count": len(results_list),
            "verified": True
        })
        return True
    
    # ========== WEBHOOK TOOL TESTS ==========
    
    def test_webhook_tool(self) -> bool:
        """Test webhook tool."""
        self.log("Testing: Webhook Tool", "TEST")
        
        # Use httpbin.org for testing
        result = self.test_tool_execute("call_webhook", {
            "url": "https://httpbin.org/post",
            "method": "POST",
            "body": {
                "test": "data",
                "timestamp": datetime.now().isoformat()
            }
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Webhook Tool", False, result)
            return False
        
        webhook_result = result.get("result", {})
        status_code = webhook_result.get("status_code")
        
        if status_code != 200:
            self.log_result("Webhook Tool", False, {
                "error": f"Expected 200, got {status_code}",
                "result": result
            })
            return False
        
        self.log(f"Webhook call successful: {status_code}")
        self.log_result("Webhook Tool", True, {"status_code": status_code})
        return True
    
    # ========== TODO TOOL TESTS ==========
    
    def test_todo_list(self) -> bool:
        """Test todo list action."""
        self.log("Testing: Todo - List Todos", "TEST")
        result = self.test_tool_execute("todo", {"action": "list"})
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - List", False, result)
            return False
        
        todos_result = result.get("result", {})
        todos = todos_result.get("todos", [])
        
        self.log(f"Found {len(todos)} todos")
        self.log_result("Todo - List", True, {"count": len(todos)})
        return True
    
    def test_todo_create(self) -> bool:
        """Test todo create action."""
        self.log("Testing: Todo - Create", "TEST")
        
        result = self.test_tool_execute("todo", {
            "action": "create",
            "title": "Test Todo",
            "description": "This is a test todo",
            "priority": "high",
            "status": "pending"
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Create", False, result)
            return False
        
        todo_result = result.get("result", {})
        todo = todo_result.get("todo")
        
        if not todo:
            self.log_result("Todo - Create", False, {
                "error": "No todo returned in result",
                "result": result
            })
            return False
        
        todo_id = todo.get("id")
        if not todo_id:
            self.log_result("Todo - Create", False, {
                "error": "Todo missing ID",
                "result": result
            })
            return False
        
        # VERIFY: Check that todo was actually created
        list_result = self.test_tool_execute("todo", {"action": "list"})
        todos = list_result.get("result", {}).get("todos", [])
        created_todo = next((t for t in todos if t.get("id") == todo_id), None)
        
        if not created_todo:
            self.log_result("Todo - Create", False, {
                "error": f"Todo {todo_id} not found in list after creation",
                "result": result
            })
            return False
        
        # Verify fields
        if created_todo.get("title") != "Test Todo":
            self.log_result("Todo - Create", False, {
                "error": f"Title mismatch: expected 'Test Todo', got '{created_todo.get('title')}'",
                "result": result
            })
            return False
        
        if created_todo.get("priority") != "high":
            self.log_result("Todo - Create", False, {
                "error": f"Priority mismatch: expected 'high', got '{created_todo.get('priority')}'",
                "result": result
            })
            return False
        
        self.log(f"Created todo: {created_todo.get('title')} (ID: {todo_id})")
        self.log(f"  Verified: title={created_todo.get('title')}, priority={created_todo.get('priority')}, status={created_todo.get('status')}")
        self.log_result("Todo - Create", True, {
            "todo_id": todo_id,
            "title": created_todo.get("title"),
            "verified": True
        })
        
        # Track for cleanup
        self.created_todo_ids.append(todo_id)
        return True
    
    def test_todo_get(self, todo_id: str) -> bool:
        """Test todo get action."""
        self.log(f"Testing: Todo - Get ({todo_id})", "TEST")
        
        result = self.test_tool_execute("todo", {
            "action": "get",
            "todo_id": todo_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Get", False, result)
            return False
        
        todo_result = result.get("result", {})
        todo = todo_result.get("todo")
        
        if not todo:
            self.log_result("Todo - Get", False, {
                "error": "No todo returned",
                "result": result
            })
            return False
        
        # VERIFY: Check ID matches and required fields present
        if todo.get("id") != todo_id:
            self.log_result("Todo - Get", False, {
                "error": f"ID mismatch: expected {todo_id}, got {todo.get('id')}",
                "result": result
            })
            return False
        
        if not todo.get("title"):
            self.log_result("Todo - Get", False, {
                "error": "Todo missing title",
                "result": result
            })
            return False
        
        self.log(f"Retrieved todo: {todo.get('title')}")
        self.log(f"  Verified: ID matches, all required fields present")
        self.log_result("Todo - Get", True, {"todo_id": todo_id, "verified": True})
        return True
    
    def test_todo_update(self, todo_id: str) -> bool:
        """Test todo update action."""
        self.log(f"Testing: Todo - Update ({todo_id})", "TEST")
        
        new_title = "Updated Test Todo"
        new_description = "Updated description"
        new_priority = "urgent"
        
        result = self.test_tool_execute("todo", {
            "action": "update",
            "todo_id": todo_id,
            "title": new_title,
            "description": new_description,
            "priority": new_priority
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Update", False, result)
            return False
        
        todo_result = result.get("result", {})
        updated_todo = todo_result.get("todo")
        
        if not updated_todo:
            self.log_result("Todo - Update", False, {
                "error": "No todo returned after update",
                "result": result
            })
            return False
        
        # VERIFY: Check that todo was actually updated
        if updated_todo.get("title") != new_title:
            self.log_result("Todo - Update", False, {
                "error": f"Title not updated: expected '{new_title}', got '{updated_todo.get('title')}'",
                "result": result
            })
            return False
        
        if updated_todo.get("description") != new_description:
            self.log_result("Todo - Update", False, {
                "error": f"Description not updated: expected '{new_description}', got '{updated_todo.get('description')}'",
                "result": result
            })
            return False
        
        if updated_todo.get("priority") != new_priority:
            self.log_result("Todo - Update", False, {
                "error": f"Priority not updated: expected '{new_priority}', got '{updated_todo.get('priority')}'",
                "result": result
            })
            return False
        
        # Verify it persists by fetching again
        get_result = self.test_tool_execute("todo", {
            "action": "get",
            "todo_id": todo_id
        })
        persisted_todo = get_result.get("result", {}).get("todo")
        
        if persisted_todo.get("title") != new_title:
            self.log_result("Todo - Update", False, {
                "error": "Update did not persist - title mismatch on re-fetch",
                "result": result
            })
            return False
        
        self.log(f"Updated todo: {new_title}")
        self.log(f"  Verified: title and priority updated and persisted")
        self.log_result("Todo - Update", True, {
            "todo_id": todo_id,
            "new_title": new_title,
            "verified": True
        })
        return True
    
    def test_todo_complete(self, todo_id: str) -> bool:
        """Test todo complete action."""
        self.log(f"Testing: Todo - Complete ({todo_id})", "TEST")
        
        result = self.test_tool_execute("todo", {
            "action": "complete",
            "todo_id": todo_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Complete", False, result)
            return False
        
        # VERIFY: Check that todo status is now completed
        get_result = self.test_tool_execute("todo", {
            "action": "get",
            "todo_id": todo_id
        })
        todo = get_result.get("result", {}).get("todo")
        
        if not todo:
            self.log_result("Todo - Complete", False, {
                "error": "Todo not found after complete",
                "result": result
            })
            return False
        
        if todo.get("status") != "completed":
            self.log_result("Todo - Complete", False, {
                "error": f"Status not updated: expected 'completed', got '{todo.get('status')}'",
                "result": result
            })
            return False
        
        if not todo.get("completed_at"):
            self.log_result("Todo - Complete", False, {
                "error": "completed_at not set",
                "result": result
            })
            return False
        
        self.log(f"Completed todo: {todo.get('title')}")
        self.log_result("Todo - Complete", True, {"todo_id": todo_id, "verified": True})
        return True
    
    def test_todo_uncomplete(self, todo_id: str) -> bool:
        """Test todo uncomplete action."""
        self.log(f"Testing: Todo - Uncomplete ({todo_id})", "TEST")
        
        result = self.test_tool_execute("todo", {
            "action": "uncomplete",
            "todo_id": todo_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Uncomplete", False, result)
            return False
        
        # VERIFY: Check that todo status is now pending
        get_result = self.test_tool_execute("todo", {
            "action": "get",
            "todo_id": todo_id
        })
        todo = get_result.get("result", {}).get("todo")
        
        if not todo:
            self.log_result("Todo - Uncomplete", False, {
                "error": "Todo not found after uncomplete",
                "result": result
            })
            return False
        
        if todo.get("status") != "pending":
            self.log_result("Todo - Uncomplete", False, {
                "error": f"Status not updated: expected 'pending', got '{todo.get('status')}'",
                "result": result
            })
            return False
        
        self.log(f"Uncompleted todo: {todo.get('title')}")
        self.log_result("Todo - Uncomplete", True, {"todo_id": todo_id, "verified": True})
        return True
    
    def test_todo_delete(self, todo_id: str) -> bool:
        """Test todo delete action."""
        self.log(f"Testing: Todo - Delete ({todo_id})", "TEST")
        
        result = self.test_tool_execute("todo", {
            "action": "delete",
            "todo_id": todo_id
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Delete", False, result)
            return False
        
        # VERIFY: Check that todo was actually deleted
        get_result = self.test_tool_execute("todo", {
            "action": "get",
            "todo_id": todo_id
        })
        
        if "error" not in get_result or not get_result.get("error"):
            # Todo still exists - that's a problem
            self.log_result("Todo - Delete", False, {
                "error": "Todo still exists after delete",
                "result": result
            })
            return False
        
        # Also verify it's not in the list
        list_result = self.test_tool_execute("todo", {"action": "list"})
        todos = list_result.get("result", {}).get("todos", [])
        deleted_todo = next((t for t in todos if t.get("id") == todo_id), None)
        
        if deleted_todo:
            self.log_result("Todo - Delete", False, {
                "error": "Todo found in list after delete",
                "result": result
            })
            return False
        
        self.log(f"Deleted todo: {todo_id}")
        self.log(f"  Verified: todo no longer exists (get failed, not in list)")
        self.log_result("Todo - Delete", True, {"todo_id": todo_id, "verified": True})
        return True
    
    def test_todo_clear_completed(self) -> bool:
        """Test clear completed todos action."""
        self.log("Testing: Todo - Clear Completed", "TEST")
        
        # First, create a completed todo
        create_result = self.test_tool_execute("todo", {
            "action": "create",
            "title": "Completed Test Todo",
            "status": "completed"
        })
        completed_todo_id = create_result.get("result", {}).get("todo", {}).get("id")
        
        # Now clear completed
        result = self.test_tool_execute("todo", {
            "action": "clear_completed"
        })
        
        if "error" in result and result.get("error"):
            self.log_result("Todo - Clear Completed", False, result)
            return False
        
        # VERIFY: Check that completed todo was deleted
        if completed_todo_id:
            get_result = self.test_tool_execute("todo", {
                "action": "get",
                "todo_id": completed_todo_id
            })
            if "error" not in get_result or not get_result.get("error"):
                self.log_result("Todo - Clear Completed", False, {
                    "error": "Completed todo still exists after clear",
                    "result": result
                })
                return False
        
        deleted_count = result.get("result", {}).get("deleted_count", 0)
        self.log(f"Cleared {deleted_count} completed todos")
        self.log_result("Todo - Clear Completed", True, {"deleted_count": deleted_count})
        return True
    
    # ========== LLM TOOL CALLING TESTS ==========
    
    def test_llm_tool_calling(self) -> bool:
        """Test LLM making tool calls via chat."""
        if not self.model_loaded:
            self.log("Skipping LLM tool calling test - no model loaded", "WARNING")
            return False
        
        self.log("Testing: LLM Tool Calling via Chat", "TEST")
        
        try:
            # Frontend uses: POST /api/chat (not /api/chat/send)
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json={
                    "message": "Please add a meeting tomorrow at 2pm to 3pm called 'LLM Test Meeting'",
                    "conversation_id": None,
                    "sampler_params": {}
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            
            tool_calls = data.get("tool_calls", [])
            response_text = data.get("response", "")
            conversation_id = data.get("conversation_id")
            
            # Track conversation for cleanup
            if conversation_id:
                self.created_conversation_ids.append(conversation_id)
            
            # Track any calendar events created by LLM tool calls
            if tool_calls:
                for tool_call in tool_calls:
                    if tool_call.get("name") == "calendar":
                        try:
                            import json
                            args = json.loads(tool_call.get("arguments", "{}"))
                            if args.get("action") == "create":
                                # We'll find and track this event during cleanup
                                pass
                        except:
                            pass
            
            if tool_calls:
                self.log(f"LLM made {len(tool_calls)} tool call(s)")
                
                # VERIFY: Check that tool calls were actually executed and worked
                calendar_tool_called = False
                calendar_event_created = False
                
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args_str = tool_call.get("arguments", "{}")
                    
                    # Parse arguments
                    try:
                        import json
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except:
                        tool_args = {}
                    
                    self.log(f"  - {tool_name}: {tool_args}")
                    
                    # If calendar tool was called to create an event, verify it was created
                    if tool_name == "calendar" and tool_args.get("action") == "create":
                        calendar_tool_called = True
                        
                        # Wait a moment for the event to be created
                        time.sleep(0.5)
                        
                        # Check if event was actually created
                        list_result = self.test_tool_execute("calendar", {"action": "list"})
                        events = list_result.get("result", {}).get("events", [])
                        
                        # Look for the event that matches what was requested
                        expected_title = "LLM Test Meeting"
                        found_event = None
                        for event in events:
                            if event.get("title") == expected_title:
                                found_event = event
                                break
                        
                        # Check if any event was created at the requested time
                        expected_start = tool_args.get("start_time", "").replace("Z", "+00:00")
                        found_event_at_time = None
                        for event in events:
                            event_start = event.get("start_time", "").replace("Z", "+00:00")
                            if event_start == expected_start or event_start[:16] == expected_start[:16]:  # Allow for timezone differences
                                found_event_at_time = event
                                break
                        
                        if not found_event_at_time:
                            self.log_result("LLM Tool Calling", False, {
                                "error": f"Calendar tool called but NO event created at requested time {expected_start}",
                                "tool_calls": len(tool_calls),
                                "events_found": len(events),
                                "tool_args": tool_args
                            })
                            return False
                        
                        # Now check if the title matches
                        event_title = found_event_at_time.get("title")
                        if event_title != expected_title:
                            # Check if title was even provided in tool call
                            if "title" not in tool_args:
                                self.log_result("LLM Tool Calling", False, {
                                    "error": f"LLM did not include 'title' parameter in tool call. Event created with title '{event_title}' instead of '{expected_title}'",
                                    "tool_calls": len(tool_calls),
                                    "tool_args": tool_args,
                                    "created_event_title": event_title
                                })
                            else:
                                self.log_result("LLM Tool Calling", False, {
                                    "error": f"Event created but wrong title: expected '{expected_title}', got '{event_title}'",
                                    "tool_calls": len(tool_calls),
                                    "tool_args": tool_args
                                })
                            return False
                        
                        found_event = found_event_at_time
                        
                        calendar_event_created = True
                        self.log(f"  ✓ Verified: Event '{expected_title}' was created (ID: {found_event.get('id')})")
                        self.log(f"  ✓ Verified: Event title matches expected value")
                        
                        # Track for cleanup
                        if found_event.get("id"):
                            self.created_event_ids.append(found_event.get("id"))
                
                # Verify we got a meaningful response
                if not response_text or len(response_text.strip()) < 10:
                    self.log(f"⚠️  Warning: Response is very short: '{response_text}'", "WARNING")
                
                self.log_result("LLM Tool Calling", True, {
                    "tool_calls": len(tool_calls),
                    "response_length": len(response_text),
                    "calendar_verified": calendar_event_created if calendar_tool_called else None,
                    "verified": True
                })
                return True
            else:
                self.log("LLM did not make tool calls", "WARNING")
                self.log(f"Response: {response_text[:100]}")
                self.log_result("LLM Tool Calling", False, {
                    "error": "No tool calls made",
                    "response": response_text[:200]
                })
                return False
        except Exception as e:
            self.log_result("LLM Tool Calling", False, {"error": str(e)})
            return False
    
    def test_llm_todo_calling(self) -> bool:
        """Test LLM making todo tool calls via chat."""
        if not self.model_loaded:
            self.log("Skipping LLM todo tool calling test - no model loaded", "WARNING")
            return False
        
        self.log("Testing: LLM Todo Tool Calling via Chat", "TEST")
        
        try:
            # Frontend uses: POST /api/chat (not /api/chat/send)
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json={
                    "message": "Please add 'LLM Test Todo' to my todo list with high priority",
                    "conversation_id": None,
                    "sampler_params": {}
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            
            tool_calls = data.get("tool_calls", [])
            response_text = data.get("response", "")
            conversation_id = data.get("conversation_id")
            
            # Track conversation for cleanup
            if conversation_id:
                self.created_conversation_ids.append(conversation_id)
            
            if tool_calls:
                self.log(f"LLM made {len(tool_calls)} tool call(s)")
                
                # VERIFY: Check that tool calls were actually executed and worked
                todo_tool_called = False
                todo_created = False
                
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args_str = tool_call.get("arguments", "{}")
                    
                    # Parse arguments
                    try:
                        import json
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except:
                        tool_args = {}
                    
                    self.log(f"  - {tool_name}: {tool_args}")
                    
                    # If todo tool was called to create a todo, verify it was created
                    if tool_name == "todo" and tool_args.get("action") == "create":
                        todo_tool_called = True
                        
                        # Wait a moment for the todo to be created
                        time.sleep(0.5)
                        
                        # Check if todo was actually created
                        list_result = self.test_tool_execute("todo", {"action": "list"})
                        todos = list_result.get("result", {}).get("todos", [])
                        
                        # Look for the todo that matches what was requested
                        expected_title = "LLM Test Todo"
                        created_todo = None
                        
                        for todo in todos:
                            if todo.get("title") == expected_title:
                                created_todo = todo
                                break
                        
                        if created_todo:
                            todo_created = True
                            self.log(f"  ✓ Verified: Todo '{expected_title}' was created (ID: {created_todo.get('id')})")
                            self.log(f"  ✓ Verified: Todo title matches expected value")
                            
                            # Verify priority
                            if created_todo.get("priority") == "high":
                                self.log(f"  ✓ Verified: Priority is 'high' as requested")
                            else:
                                self.log(f"  ⚠️  Priority is '{created_todo.get('priority')}' instead of 'high'", "WARNING")
                            
                            # Track for cleanup
                            self.created_todo_ids.append(created_todo.get("id"))
                        else:
                            # Check if any todo was created (maybe title was different)
                            recent_todos = [t for t in todos if abs((datetime.fromisoformat(t.get("created_at", "").replace("Z", "+00:00")) - datetime.now()).total_seconds()) < 120]
                            if recent_todos:
                                self.log(f"  ⚠️  Todo was created but with different title: '{recent_todos[0].get('title')}'", "WARNING")
                                self.created_todo_ids.append(recent_todos[0].get("id"))
                            else:
                                self.log_result("LLM Todo Tool Calling", False, {
                                    "error": "Todo tool called but NO todo created",
                                    "tool_calls": len(tool_calls),
                                    "todos_found": len(todos),
                                    "tool_args": tool_args
                                })
                                return False
                
                if not todo_tool_called:
                    self.log_result("LLM Todo Tool Calling", False, {
                        "error": "LLM did not call todo tool",
                        "tool_calls": len(tool_calls),
                        "response": response_text[:200]
                    })
                    return False
                
                if not todo_created:
                    self.log_result("LLM Todo Tool Calling", False, {
                        "error": "Todo tool called but todo not found in list",
                        "tool_calls": len(tool_calls),
                        "tool_args": tool_args
                    })
                    return False
                
                self.log_result("LLM Todo Tool Calling", True, {
                    "tool_calls": len(tool_calls),
                    "todo_created": True,
                    "verified": True
                })
                return True
            else:
                self.log_result("LLM Todo Tool Calling", False, {
                    "error": "No tool calls made by LLM",
                    "response": response_text[:200]
                })
                return False
                
        except Exception as e:
            self.log_result("LLM Todo Tool Calling", False, {
                "error": str(e),
                "exception_type": type(e).__name__
            })
            return False
    
    # ========== CLEANUP METHODS ==========
    
    def cleanup_calendar_events(self):
        """Delete all test calendar events."""
        if not self.created_event_ids:
            return
        
        self.log(f"Cleaning up {len(self.created_event_ids)} test calendar events...", "TEST")
        deleted_count = 0
        
        for event_id in self.created_event_ids:
            try:
                result = self.test_tool_execute("calendar", {
                    "action": "delete",
                    "event_id": event_id
                })
                if not result.get("error"):
                    deleted_count += 1
            except Exception as e:
                self.log(f"Failed to delete event {event_id}: {e}", "WARNING")
        
        # Also try to delete any events with test titles
        try:
            list_result = self.test_tool_execute("calendar", {"action": "list"})
            events = list_result.get("result", {}).get("events", [])
            test_titles = ["Test Meeting", "Updated Test Meeting", "All Day Test Event", "LLM Test Meeting"]
            
            for event in events:
                if event.get("title") in test_titles:
                    try:
                        self.test_tool_execute("calendar", {
                            "action": "delete",
                            "event_id": event.get("id")
                        })
                        deleted_count += 1
                    except:
                        pass
        except:
            pass
        
        self.log(f"Deleted {deleted_count} test calendar events", "SUCCESS")
    
    def cleanup_todos(self):
        """Delete all test todos."""
        if not self.created_todo_ids:
            return
        
        self.log(f"Cleaning up {len(self.created_todo_ids)} test todos...", "TEST")
        deleted_count = 0
        
        for todo_id in self.created_todo_ids:
            try:
                result = self.test_tool_execute("todo", {
                    "action": "delete",
                    "todo_id": todo_id
                })
                if not result.get("error"):
                    deleted_count += 1
            except Exception as e:
                self.log(f"Failed to delete todo {todo_id}: {e}", "WARNING")
        
        # Also try to delete any todos with test titles
        try:
            list_result = self.test_tool_execute("todo", {"action": "list"})
            todos = list_result.get("result", {}).get("todos", [])
            test_titles = ["Test Todo", "Updated Test Todo", "Completed Test Todo", "LLM Test Todo"]
            
            for todo in todos:
                if todo.get("title") in test_titles:
                    try:
                        self.test_tool_execute("todo", {
                            "action": "delete",
                            "todo_id": todo.get("id")
                        })
                        deleted_count += 1
                    except:
                        pass
        except:
            pass
        
        self.log(f"Deleted {deleted_count} test todos", "SUCCESS")
    
    def cleanup_conversations(self):
        """Delete all test conversations."""
        if not self.created_conversation_ids:
            return
        
        self.log(f"Cleaning up {len(self.created_conversation_ids)} test conversations...", "TEST")
        deleted_count = 0
        
        for conv_id in self.created_conversation_ids:
            try:
                response = requests.delete(
                    f"{BASE_URL}/api/conversations/{conv_id}",
                    timeout=10.0
                )
                if response.status_code == 200:
                    deleted_count += 1
            except Exception as e:
                self.log(f"Failed to delete conversation {conv_id}: {e}", "WARNING")
        
        self.log(f"Deleted {deleted_count} test conversations", "SUCCESS")
    
    def cleanup_vector_store(self):
        """Clean up vector store pollution from test conversations."""
        if not self.created_conversation_ids:
            return
        
        self.log("Cleaning up vector store test data...", "TEST")
        
        # Try to disable vector memory for test conversations
        try:
            for conv_id in self.created_conversation_ids:
                try:
                    # Try to disable vector memory for this conversation first
                    _ = requests.put(
                        f"{BASE_URL}/api/conversations/{conv_id}/vector-memory",
                        json={"enabled": False},
                        timeout=10.0
                    )
                    # Don't fail if endpoint doesn't exist
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code != 404:
                        self.log(f"Vector store cleanup warning for {conv_id}: {e}", "WARNING")
                except:
                    # Endpoint may not exist, that's okay
                    pass
        except Exception as e:
            self.log(f"Vector store cleanup error (may be expected): {e}", "WARNING")
        
        self.log("Vector store cleanup completed", "SUCCESS")
    
    def cleanup_all(self):
        """Clean up all test data."""
        self.log("\n" + "=" * 80)
        self.log("CLEANUP: Removing Test Data")
        self.log("=" * 80)
        
        self.cleanup_calendar_events()
        self.cleanup_todos()
        self.cleanup_conversations()
        self.cleanup_vector_store()
        
        self.log("Cleanup completed", "SUCCESS")
    
    # ========== MAIN TEST RUNNER ==========
    
    def run_all_tests(self, model_name: Optional[str] = None):
        """Run all tool tests."""
        self.log("=" * 80)
        self.log("COMPREHENSIVE TOOL TESTING SUITE")
        self.log("=" * 80)
        
        # Check gateway
        if not self.start_gateway():
            self.log("Cannot proceed without gateway. Exiting.", "ERROR")
            return
        
        # List tools first
        self.test_list_tools()
        
        # Load model if specified
        if model_name:
            if not self.load_model(model_name):
                self.log("Model loading failed, but continuing with direct tool tests", "WARNING")
        else:
            # Try to find a model
            models = self.list_available_models()
            if models:
                self.log(f"Found {len(models)} models. Using first one: {models[0]}")
                if not self.load_model(models[0]):
                    self.log("Model loading failed, but continuing with direct tool tests", "WARNING")
        
        # Test all tools systematically
        self.log("\n" + "=" * 80)
        self.log("TESTING INDIVIDUAL TOOLS")
        self.log("=" * 80)
        
        # Time tool
        self.test_time_tool()
        
        # Benchmark tool
        self.test_benchmark_tool()
        
        # Google Search tool
        self.test_google_search()
        
        # Webhook tool
        self.test_webhook_tool()
        
        # Calendar tool - comprehensive tests
        self.log("\n" + "=" * 80)
        self.log("TESTING CALENDAR TOOL (All Actions)")
        self.log("=" * 80)
        
        self.test_calendar_list()
        self.test_calendar_check_conflicts()
        self.test_calendar_create()
        
        # Get the created event ID for further tests
        list_result = self.test_tool_execute("calendar", {"action": "list"})
        events = list_result.get("result", {}).get("events", [])
        test_event_id = None
        for event in events:
            if event.get("title") == "Test Meeting":
                test_event_id = event.get("id")
                break
        
        if test_event_id:
            self.test_calendar_get(test_event_id)
            self.test_calendar_update(test_event_id)
        
        self.test_calendar_all_day()
        
        # Delete the test event before delete_day test (delete_day will clean up all events on that day)
        if test_event_id:
            self.test_calendar_delete(test_event_id)
        
        # Test delete_day (this will delete all events on tomorrow, including the all-day event)
        self.test_calendar_delete_day()
        
        # Todo tool - comprehensive tests
        self.log("\n" + "=" * 80)
        self.log("TESTING TODO TOOL (All Actions)")
        self.log("=" * 80)
        
        self.test_todo_list()
        self.test_todo_create()
        
        # Get the created todo ID for further tests
        list_result = self.test_tool_execute("todo", {"action": "list"})
        todos = list_result.get("result", {}).get("todos", [])
        test_todo_id = None
        for todo in todos:
            if todo.get("title") == "Test Todo":
                test_todo_id = todo.get("id")
                break
        
        if test_todo_id:
            self.test_todo_get(test_todo_id)
            self.test_todo_update(test_todo_id)
            self.test_todo_complete(test_todo_id)
            self.test_todo_uncomplete(test_todo_id)
            self.test_todo_delete(test_todo_id)
        
        self.test_todo_clear_completed()
        
        # LLM tool calling test
        if self.model_loaded:
            self.log("\n" + "=" * 80)
            self.log("TESTING LLM TOOL CALLING")
            self.log("=" * 80)
            self.test_llm_tool_calling()
            self.test_llm_todo_calling()
        
        # Print summary
        self.log("\n" + "=" * 80)
        self.log("TEST SUMMARY")
        self.log("=" * 80)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed
        
        self.log(f"Total tests: {total}")
        self.log(f"Passed: {passed}", "SUCCESS" if passed > 0 else "INFO")
        self.log(f"Failed: {failed}", "ERROR" if failed > 0 else "SUCCESS")
        
        if failed > 0:
            self.log("\nFailed tests:")
            for result in self.results:
                if not result["success"]:
                    self.log(f"  - {result['test']}", "ERROR")
        
        # Cleanup test data
        self.cleanup_all()
        
        # Save results to file
        results_file = Path("tool_test_results.json")
        with open(results_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed
                },
                "results": self.results,
                "cleanup": {
                    "events_deleted": len(self.created_event_ids),
                    "conversations_deleted": len(self.created_conversation_ids)
                }
            }, f, indent=2)
        
        self.log(f"\nResults saved to: {results_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test all tool functionality")
    parser.add_argument(
        "--model",
        type=str,
        help="Model name to load (optional)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Base URL for API (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
                                                                      
    global BASE_URL
    BASE_URL = args.base_url
    
    tester = ToolTester()
    tester.run_all_tests(model_name=args.model)


if __name__ == "__main__":
    main()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  