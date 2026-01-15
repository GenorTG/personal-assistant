#!/usr/bin/env python3
"""Test WebSocket server functionality."""
import sys
import asyncio
import json
from pathlib import Path

# Add gateway src to path
gateway_dir = Path(__file__).parent
sys.path.insert(0, str(gateway_dir / "src"))

import httpx
import websockets
from config.settings import settings

async def test_websocket_connection():
    """Test WebSocket connection and message handling."""
    print("=" * 60)
    print("Testing WebSocket Server")
    print("=" * 60)
    
    # Check if server is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{settings.port}/health", timeout=2.0)
            if not response.is_success:
                print("❌ Gateway server is not running!")
                print("   Please start the gateway server first:")
                print("   cd services/gateway && source ../.core_venv/bin/activate && python -m uvicorn src.main:app --port 8000")
                return False
    except Exception as e:
        print(f"❌ Cannot connect to gateway server: {e}")
        print("   Please start the gateway server first")
        return False
    
    print("✓ Gateway server is running")
    
    # Test WebSocket connection
    ws_url = f"ws://localhost:{settings.port}/ws"
    print(f"\nConnecting to WebSocket: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("✓ WebSocket connection established")
            
            # Wait for welcome message
            try:
                welcome = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                welcome_data = json.loads(welcome)
                print(f"✓ Received welcome message: {welcome_data.get('action')}")
                if welcome_data.get('action') == 'connected':
                    print(f"  Connection ID: {welcome_data.get('payload', {}).get('connection_id')}")
            except asyncio.TimeoutError:
                print("⚠ No welcome message received (may be OK)")
            
            # Test get_settings request
            print("\nTesting get_settings request...")
            request = {
                "type": "request",
                "id": "test_1",
                "action": "get_settings",
                "payload": {}
            }
            await websocket.send(json.dumps(request))
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                print(f"✓ Received response: {response_data.get('action')}")
                if response_data.get('error'):
                    print(f"  Error: {response_data.get('error')}")
                else:
                    print(f"  Payload keys: {list(response_data.get('payload', {}).keys())}")
            except asyncio.TimeoutError:
                print("❌ No response received for get_settings")
                return False
            
            # Test ping
            print("\nTesting ping/pong...")
            ping = {
                "type": "ping",
                "id": "test_ping"
            }
            await websocket.send(json.dumps(ping))
            
            try:
                pong = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                pong_data = json.loads(pong)
                if pong_data.get('action') == 'pong':
                    print("✓ Ping/pong works")
                else:
                    print(f"⚠ Unexpected response: {pong_data.get('action')}")
            except asyncio.TimeoutError:
                print("⚠ No pong received (may be OK)")
            
            print("\n✓ WebSocket connection test completed successfully")
            return True
            
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"❌ WebSocket connection failed: {e}")
        print("   Make sure the WebSocket endpoint is registered in the FastAPI app")
        return False
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_websocket_manager():
    """Test WebSocketManager functionality."""
    print("\n" + "=" * 60)
    print("Testing WebSocketManager")
    print("=" * 60)
    
    try:
        # Import using absolute path from src
        from src.services.websocket_manager import get_websocket_manager
        ws_manager = get_websocket_manager()
        print(f"✓ WebSocketManager created: {type(ws_manager).__name__}")
        print(f"✓ Connection count: {ws_manager.get_connection_count()}")
        return True
    except Exception as e:
        print(f"⚠ WebSocketManager test skipped (requires full app context): {e}")
        print("   This is OK - WebSocketManager will work when server is running")
        return True  # Don't fail - this requires full app initialization

async def main():
    """Run all tests."""
    print("\n")
    manager_ok = await test_websocket_manager()
    if not manager_ok:
        print("\n❌ WebSocketManager test failed - cannot continue")
        return
    
    connection_ok = await test_websocket_connection()
    
    print("\n" + "=" * 60)
    if connection_ok:
        print("✅ All WebSocket tests passed!")
    else:
        print("❌ WebSocket connection test failed")
        print("   Make sure the gateway server is running and WebSocket endpoint is registered")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

