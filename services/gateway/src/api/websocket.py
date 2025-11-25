"""WebSocket handlers for real-time chat."""
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter

ws_router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, conversation_id: str):
        """Accept a WebSocket connection."""
        await websocket.accept()
        self.active_connections[conversation_id] = websocket
    
    def disconnect(self, conversation_id: str):
        """Remove a WebSocket connection."""
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]
    
    async def send_message(self, conversation_id: str, message: dict):
        """Send message to a specific connection."""
        if conversation_id in self.active_connections:
            websocket = self.active_connections[conversation_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                # Connection may be closed
                self.disconnect(conversation_id)
                raise e


manager = ConnectionManager()


@ws_router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for real-time chat."""
    await manager.connect(websocket, conversation_id)
    try:
        while True:
            data = await websocket.receive_json()
            # TODO: Process chat message and stream response
            await websocket.send_json({
                "type": "response",
                "content": "Not implemented yet",
                "done": True
            })
    except WebSocketDisconnect:
        manager.disconnect(conversation_id)
