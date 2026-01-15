#!/usr/bin/env python3
"""Test script to verify tool calling functionality."""
import asyncio
import httpx
import json
import sys
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

async def test_tool_debug():
    """Test tool debug endpoint."""
    print("=" * 60)
    print("TEST 1: Tool Debug Info")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/api/tools/debug")
            response.raise_for_status()
            debug_info = response.json()
            print(json.dumps(debug_info, indent=2))
            return debug_info
        except Exception as e:
            print(f"Error: {e}")
            return None

async def test_list_tools():
    """Test listing available tools."""
    print("\n" + "=" * 60)
    print("TEST 2: List Available Tools")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/api/tools")
            response.raise_for_status()
            data = response.json()
            print(f"Total tools: {data.get('count', 0)}")
            for tool in data.get('tools', []):
                print(f"  - {tool.get('name')}: {tool.get('description', '')[:50]}")
            return data
        except Exception as e:
            print(f"Error: {e}")
            return None

async def test_calendar_list():
    """Test listing calendar events."""
    print("\n" + "=" * 60)
    print("TEST 3: List Calendar Events")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/api/tools/calendar/events")
            response.raise_for_status()
            data = response.json()
            events = data.get('result', {}).get('events', [])
            print(f"Total events: {len(events)}")
            for event in events:
                print(f"  - {event.get('title')} ({event.get('start_time')})")
            return data
        except Exception as e:
            print(f"Error: {e}")
            return None

async def test_create_calendar_event():
    """Test creating a calendar event directly."""
    print("\n" + "=" * 60)
    print("TEST 4: Create Calendar Event (Direct)")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        try:
            # Create event for tomorrow at 2pm
            tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
            end_time = tomorrow + timedelta(hours=1)
            
            payload = {
                "tool_name": "calendar",
                "parameters": {
                    "action": "create",
                    "title": "Test Event from Script",
                    "description": "This is a test event created by the tool calling test script",
                    "start_time": tomorrow.isoformat(),
                    "end_time": end_time.isoformat(),
                    "location": "Test Location"
                }
            }
            
            response = await client.post(
                f"{BASE_URL}/api/tools/execute",
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            print(f"Event created: {json.dumps(result, indent=2)}")
            return result
        except Exception as e:
            print(f"Error: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return None

async def test_chat_with_tool_request():
    """Test chat endpoint with a request that should trigger tool calling."""
    print("\n" + "=" * 60)
    print("TEST 5: Chat Request (Should Trigger Tool Calling)")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        try:
            payload = {
                "message": "Please add an event to my calendar for tomorrow at 3pm called 'Meeting with Team'",
                "conversation_id": None
            }
            
            print(f"Sending message: {payload['message']}")
            response = await client.post(
                f"{BASE_URL}/api/chat",
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"\nResponse: {result.get('response', '')[:200]}")
            tool_calls = result.get('tool_calls', [])
            print(f"\nTool calls detected: {len(tool_calls)}")
            for i, tc in enumerate(tool_calls):
                print(f"  Tool call {i+1}:")
                print(f"    Name: {tc.get('name')}")
                print(f"    Arguments: {json.dumps(tc.get('arguments', {}), indent=6)}")
                print(f"    Success: {tc.get('success', False)}")
                if tc.get('error'):
                    print(f"    Error: {tc.get('error')}")
                if tc.get('result'):
                    print(f"    Result: {str(tc.get('result'))[:100]}")
            
            return result
        except Exception as e:
            print(f"Error: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return None

async def main():
    """Run all tests."""
    print("Tool Calling Test Suite")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    # Test 1: Debug info
    debug_info = await test_tool_debug()
    
    # Test 2: List tools
    tools_data = await test_list_tools()
    
    # Test 3: List calendar events
    calendar_data = await test_calendar_list()
    
    # Test 4: Create event directly
    create_result = await test_create_calendar_event()
    
    # Wait a moment
    await asyncio.sleep(1)
    
    # Test 5: Chat with tool request
    chat_result = await test_chat_with_tool_request()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tool manager initialized: {debug_info.get('tool_manager_initialized') if debug_info else 'Unknown'}")
    print(f"Model loaded: {debug_info.get('model_loaded') if debug_info else 'Unknown'}")
    print(f"Model supports tool calling: {debug_info.get('model_supports_tool_calling') if debug_info else 'Unknown'}")
    print(f"Tool manager connected: {debug_info.get('tool_manager_connected') if debug_info else 'Unknown'}")
    print(f"Available tools: {debug_info.get('tool_count', 0) if debug_info else 0}")
    print(f"Tool calls in chat response: {len(chat_result.get('tool_calls', [])) if chat_result else 0}")
    
    if chat_result and len(chat_result.get('tool_calls', [])) == 0:
        print("\n⚠️  WARNING: No tool calls detected in chat response!")
        print("   This suggests tool calling is not working properly.")
        print("   Check the logs for more details.")

if __name__ == "__main__":
    asyncio.run(main())

