"""WebSocket manager service for broadcasting events."""
# Standard library
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Local
from ..api.routes.websocket import get_connection_manager

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events."""
    
    def __init__(self):
        self._connection_manager = None
    
    def _get_connection_manager(self):
        """Get the connection manager instance."""
        if self._connection_manager is None:
            self._connection_manager = get_connection_manager()
        return self._connection_manager
    
    async def broadcast_settings_update(self, settings: Dict[str, Any]):
        """Broadcast settings update event."""
        message = {
            "type": "event",
            "action": "settings_updated",
            "payload": settings,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted settings_updated event")
    
    async def broadcast_service_status(self, status: Dict[str, Any]):
        """Broadcast service status change event."""
        message = {
            "type": "event",
            "action": "service_status_changed",
            "payload": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted service_status_changed event")
    
    async def broadcast_download_progress(self, download_id: str, progress: Dict[str, Any]):
        """Broadcast download progress update."""
        message = {
            "type": "event",
            "action": "download_progress",
            "payload": {
                "download_id": download_id,
                **progress
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted download_progress event for {download_id}")
    
    async def broadcast_download_completed(self, download_id: str, result: Dict[str, Any]):
        """Broadcast download completion event."""
        message = {
            "type": "event",
            "action": "download_completed",
            "payload": {
                "download_id": download_id,
                **result
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted download_completed event for {download_id}")
    
    async def broadcast_model_loaded(self, model_id: str, model_info: Dict[str, Any]):
        """Broadcast model loaded event."""
        message = {
            "type": "event",
            "action": "model_loaded",
            "payload": {
                "model_id": model_id,
                **model_info
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted model_loaded event for {model_id}")
    
    async def broadcast_model_unloaded(self, model_id: Optional[str] = None):
        """Broadcast model unloaded event."""
        message = {
            "type": "event",
            "action": "model_unloaded",
            "payload": {
                "model_id": model_id
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted model_unloaded event")
    
    async def broadcast_model_status_changed(self, model_id: str, status: Dict[str, Any]):
        """Broadcast model status change event."""
        message = {
            "type": "event",
            "action": "model_status_changed",
            "payload": {
                "model_id": model_id,
                **status
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted model_status_changed event for {model_id}")
    
    async def broadcast_conversation_created(self, conversation: Dict[str, Any]):
        """Broadcast conversation created event."""
        message = {
            "type": "event",
            "action": "conversation_created",
            "payload": conversation,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted conversation_created event for {conversation.get('conversation_id')}")
    
    async def broadcast_conversation_deleted(self, conversation_id: str):
        """Broadcast conversation deleted event."""
        message = {
            "type": "event",
            "action": "conversation_deleted",
            "payload": {"conversation_id": conversation_id},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted conversation_deleted event for {conversation_id}")
    
    async def broadcast_conversation_updated(self, conversation: Dict[str, Any]):
        """Broadcast conversation updated event (name changed, pinned, etc.)."""
        message = {
            "type": "event",
            "action": "conversation_updated",
            "payload": conversation,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted conversation_updated event for {conversation.get('conversation_id')}")
    
    async def broadcast_conversations_list_changed(self):
        """Broadcast that the conversations list has changed (for refresh)."""
        message = {
            "type": "event",
            "action": "conversations_list_changed",
            "payload": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted conversations_list_changed event")
        
        # Also broadcast debug info update for debug panel (memory stats changed)
        try:
            from ...api.routes.system import _get_debug_info_internal
            debug_info = await _get_debug_info_internal()
            await self.broadcast_debug_info_updated(debug_info)
        except Exception as e:
            logger.debug(f"Failed to broadcast debug info after conversation change: {e}")
    
    def get_connection_count(self) -> int:
        """Get the number of active WebSocket connections."""
        return self._get_connection_manager().get_connection_count()
    
    async def broadcast_calendar_event_created(self, event: Dict[str, Any]):
        """Broadcast calendar event created."""
        message = {
            "type": "event",
            "action": "calendar_event_created",
            "payload": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted calendar_event_created event for {event.get('id')}")
    
    async def broadcast_calendar_event_updated(self, event: Dict[str, Any]):
        """Broadcast calendar event updated."""
        message = {
            "type": "event",
            "action": "calendar_event_updated",
            "payload": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted calendar_event_updated event for {event.get('id')}")
    
    async def broadcast_calendar_event_deleted(self, event_id: str):
        """Broadcast calendar event deleted."""
        message = {
            "type": "event",
            "action": "calendar_event_deleted",
            "payload": {"event_id": event_id},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted calendar_event_deleted event for {event_id}")
    
    async def broadcast_calendar_events_changed(self):
        """Broadcast that calendar events list has changed."""
        message = {
            "type": "event",
            "action": "calendar_events_changed",
            "payload": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted calendar_events_changed event")
    
    async def broadcast_todo_created(self, todo: Dict[str, Any]):
        """Broadcast todo created."""
        message = {
            "type": "event",
            "action": "todo_created",
            "payload": todo,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted todo_created event for {todo.get('id')}")
    
    async def broadcast_todo_updated(self, todo: Dict[str, Any]):
        """Broadcast todo updated."""
        message = {
            "type": "event",
            "action": "todo_updated",
            "payload": todo,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted todo_updated event for {todo.get('id')}")
    
    async def broadcast_todo_deleted(self, todo_id: str):
        """Broadcast todo deleted."""
        message = {
            "type": "event",
            "action": "todo_deleted",
            "payload": {"todo_id": todo_id},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug(f"Broadcasted todo_deleted event for {todo_id}")
    
    async def broadcast_todos_changed(self):
        """Broadcast that todos list has changed."""
        message = {
            "type": "event",
            "action": "todos_changed",
            "payload": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted todos_changed event")
    
    async def broadcast_debug_info_updated(self, debug_info: Dict[str, Any]):
        """Broadcast debug info update event."""
        message = {
            "type": "event",
            "action": "debug_info_updated",
            "payload": debug_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self._get_connection_manager().broadcast(message)
        logger.debug("Broadcasted debug_info_updated event")


# Global instance
_websocket_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance."""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager


