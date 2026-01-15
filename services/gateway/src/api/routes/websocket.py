"""WebSocket endpoint for real-time communication."""
import json
import logging
import uuid
from datetime import datetime, date
from typing import Dict, Set, Optional, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


def serialize_for_json(obj: Any) -> Any:
    """Recursively serialize objects for JSON, handling datetime and other non-serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    elif hasattr(obj, 'dict'):
        # Pydantic model
        return serialize_for_json(obj.dict())
    elif hasattr(obj, 'model_dump'):
        # Pydantic v2 model
        return serialize_for_json(obj.model_dump())
    else:
        return obj


class WebSocketConnectionManager:
    """Manages WebSocket connections for real-time communication."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, Dict] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: Optional[str] = None) -> str:
        """Accept a WebSocket connection and return its ID."""
        if connection_id is None:
            connection_id = str(uuid.uuid4())
        
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.connection_metadata[connection_id] = {
            "connected_at": None,
            "last_activity": None,
        }
        logger.info(f"WebSocket connection established: {connection_id}")
        return connection_id
    
    def disconnect(self, connection_id: str):
        """Remove a connection."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.connection_metadata:
            del self.connection_metadata[connection_id]
        logger.info(f"WebSocket connection closed: {connection_id}")
    
    async def send_personal_message(self, message: dict, connection_id: str):
        """Send a message to a specific connection."""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                else:
                    logger.warning(f"Connection {connection_id} is not in CONNECTED state")
                    self.disconnect(connection_id)
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {e}")
                self.disconnect(connection_id)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection_id, websocket in list(self.active_connections.items()):
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
                else:
                    disconnected.append(connection_id)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_id}: {e}")
                disconnected.append(connection_id)
        
        # Clean up disconnected clients
        for connection_id in disconnected:
            self.disconnect(connection_id)
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)


# Global connection manager instance
connection_manager = WebSocketConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    connection_id = None
    try:
        # Accept connection
        connection_id = await connection_manager.connect(websocket)
        
        # Send welcome message
        await websocket.send_json({
            "type": "event",
            "action": "connected",
            "payload": {
                "connection_id": connection_id,
                "message": "WebSocket connection established"
            }
        })
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    await handle_message(websocket, connection_id, message)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {connection_id}: {data}")
                    await websocket.send_json({
                        "type": "response",
                        "action": "error",
                        "error": "Invalid JSON format"
                    })
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error handling message from {connection_id}: {e}", exc_info=True)
                try:
                    await websocket.send_json({
                        "type": "response",
                        "action": "error",
                        "error": str(e)
                    })
                except:
                    pass
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        if connection_id:
            connection_manager.disconnect(connection_id)


async def handle_message(websocket: WebSocket, connection_id: str, message: dict):
    """Handle incoming WebSocket messages."""
    message_type = message.get("type", "request")
    action = message.get("action")
    message_id = message.get("id")
    
    if message_type == "request":
        # Handle request messages
        await handle_request(websocket, connection_id, action, message_id, message.get("payload", {}))
    elif message_type == "ping":
        # Handle ping for keepalive
        await websocket.send_json({
            "type": "response",
            "action": "pong",
            "id": message_id
        })
    else:
        logger.warning(f"Unknown message type from {connection_id}: {message_type}")


async def handle_request(websocket: WebSocket, connection_id: str, action: str, message_id: Optional[str], payload: dict):
    """Handle request actions."""
    try:
        # Import here to avoid circular dependencies
        from ...services.service_manager import service_manager
        
        response = None
        
        # === Settings Operations ===
        if action == "get_settings":
            # Get current settings
            if service_manager and hasattr(service_manager, 'llm_manager'):
                from ...api.routes.settings import get_settings
                settings_response = await get_settings()
                # Convert Pydantic model to dict and serialize datetime objects
                if hasattr(settings_response, 'dict'):
                    settings_data = settings_response.dict()
                elif hasattr(settings_response, 'model_dump'):
                    settings_data = settings_response.model_dump()
                else:
                    settings_data = dict(settings_response)
                # Serialize datetime objects
                settings_data = serialize_for_json(settings_data)
                response = {
                    "type": "response",
                    "action": "get_settings",
                    "id": message_id,
                    "payload": settings_data
                }
        
        elif action == "update_settings":
            # Update settings
            if service_manager and hasattr(service_manager, 'llm_manager'):
                from ...api.routes.settings import update_settings
                from ..schemas import AISettings
                
                # Convert payload to AISettings object
                settings_dict = payload.get("settings", {})
                try:
                    # Create AISettings from dict (Pydantic will validate)
                    settings_update = AISettings(**settings_dict)
                    settings_response = await update_settings(settings_update)
                    # Convert to dict and serialize datetime objects
                    if hasattr(settings_response, 'dict'):
                        settings_data = settings_response.dict()
                    elif hasattr(settings_response, 'model_dump'):
                        settings_data = settings_response.model_dump()
                    else:
                        settings_data = dict(settings_response)
                    # Serialize datetime objects
                    settings_data = serialize_for_json(settings_data)
                    response = {
                        "type": "response",
                        "action": "update_settings",
                        "id": message_id,
                        "payload": settings_data
                    }
                except Exception as e:
                    logger.error(f"Error updating settings via WebSocket: {e}", exc_info=True)
                    response = {
                        "type": "response",
                        "action": "update_settings",
                        "id": message_id,
                        "error": f"Failed to update settings: {str(e)}"
                    }
        
        # === Service Status Operations ===
        elif action == "get_service_status":
            # Get service status
            if service_manager:
                from ...api.routes.system import get_services_status
                status_data = await get_services_status()
                # Serialize datetime objects
                status_data = serialize_for_json(status_data)
                response = {
                    "type": "response",
                    "action": "get_service_status",
                    "id": message_id,
                    "payload": status_data
                }
        
        # === Download Operations ===
        elif action == "get_downloads":
            # Get download status
            if service_manager and hasattr(service_manager, 'llm_manager'):
                from ...api.routes.downloads import list_downloads
                downloads_data = await list_downloads()
                # Serialize datetime objects
                downloads_data = serialize_for_json(downloads_data)
                response = {
                    "type": "response",
                    "action": "get_downloads",
                    "id": message_id,
                    "payload": downloads_data
                }
        
        # === Model Operations ===
        elif action == "list_models":
            # List all models
            if service_manager and hasattr(service_manager, 'llm_manager'):
                from ...api.routes.models import list_models
                models_data = await list_models()
                # Convert list of Pydantic models to dicts and serialize datetime objects
                models_list = []
                for model in models_data:
                    if hasattr(model, 'dict'):
                        model_dict = model.dict()
                    elif hasattr(model, 'model_dump'):
                        model_dict = model.model_dump()
                    else:
                        model_dict = dict(model)
                    # Serialize datetime objects
                    models_list.append(serialize_for_json(model_dict))
                response = {
                    "type": "response",
                    "action": "list_models",
                    "id": message_id,
                    "payload": models_list
                }
        
        elif action == "get_model_info":
            # Get model info
            if service_manager and hasattr(service_manager, 'llm_manager'):
                from ...api.routes.models import get_model_info
                model_id = payload.get("model_id")
                if not model_id:
                    raise ValueError("model_id is required")
                model_data = await get_model_info(model_id)
                # Convert to dict and serialize datetime objects
                if hasattr(model_data, 'dict'):
                    model_dict = model_data.dict()
                elif hasattr(model_data, 'model_dump'):
                    model_dict = model_data.model_dump()
                else:
                    model_dict = dict(model_data)
                # Serialize datetime objects
                model_dict = serialize_for_json(model_dict)
                response = {
                    "type": "response",
                    "action": "get_model_info",
                    "id": message_id,
                    "payload": model_dict
                }
        
        # === Conversation Operations ===
        elif action == "list_conversations":
            # List conversations
            if service_manager and hasattr(service_manager, 'chat_manager'):
                from ...api.routes.conversations import list_conversations
                limit = payload.get("limit")
                offset = payload.get("offset", 0)
                include_names = payload.get("include_names", True)
                conversations_data = await list_conversations(limit=limit, offset=offset, include_names=include_names)
                # Convert list of Pydantic models to dicts and serialize datetime objects
                convs_list = []
                for conv in conversations_data:
                    if hasattr(conv, 'dict'):
                        conv_dict = conv.dict()
                    elif hasattr(conv, 'model_dump'):
                        conv_dict = conv.model_dump()
                    else:
                        conv_dict = dict(conv)
                    # Serialize datetime objects
                    convs_list.append(serialize_for_json(conv_dict))
                response = {
                    "type": "response",
                    "action": "list_conversations",
                    "id": message_id,
                    "payload": convs_list
                }
        
        elif action == "get_conversation":
            # Get single conversation
            if service_manager and hasattr(service_manager, 'chat_manager'):
                from ...api.routes.conversations import get_conversation
                conversation_id = payload.get("conversation_id")
                if not conversation_id:
                    raise ValueError("conversation_id is required")
                conv_data = await get_conversation(conversation_id)
                # Convert to dict and serialize datetime objects
                if hasattr(conv_data, 'dict'):
                    conv_dict = conv_data.dict()
                elif hasattr(conv_data, 'model_dump'):
                    conv_dict = conv_data.model_dump()
                else:
                    conv_dict = dict(conv_data)
                # Serialize datetime objects
                conv_dict = serialize_for_json(conv_dict)
                response = {
                    "type": "response",
                    "action": "get_conversation",
                    "id": message_id,
                    "payload": conv_dict
                }
        
        elif action == "create_conversation":
            # Create new conversation
            if service_manager and hasattr(service_manager, 'chat_manager'):
                from ...api.routes.conversations import create_conversation
                conv_data = await create_conversation()
                response = {
                    "type": "response",
                    "action": "create_conversation",
                    "id": message_id,
                    "payload": conv_data
                }
        
        # === Subscription ===
        elif action == "subscribe":
            # Subscribe to specific event types
            event_types = payload.get("events", [])
            # Store subscription in metadata (simplified - could be more sophisticated)
            if connection_id in connection_manager.connection_metadata:
                connection_manager.connection_metadata[connection_id]["subscriptions"] = event_types
            response = {
                "type": "response",
                "action": "subscribe",
                "id": message_id,
                "payload": {"subscribed_to": event_types}
            }
        
        else:
            response = {
                "type": "response",
                "action": action,
                "id": message_id,
                "error": f"Unknown action: {action}"
            }
        
        if response:
            await websocket.send_json(response)
    
    except Exception as e:
        logger.error(f"Error handling request {action}: {e}", exc_info=True)
        await websocket.send_json({
            "type": "response",
            "action": action,
            "id": message_id,
            "error": str(e)
        })


def get_connection_manager() -> WebSocketConnectionManager:
    """Get the global WebSocket connection manager instance."""
    return connection_manager

