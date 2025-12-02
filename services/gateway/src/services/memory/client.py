"""HTTP client for Memory service."""
from typing import List, Dict, Any, Optional
import httpx
import logging
from ...config.settings import settings

logger = logging.getLogger(__name__)


class MemoryServiceClient:
    """HTTP client for communicating with Memory service."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or "http://localhost:8005"
        self.timeout = 30.0
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to Memory service."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            logger.warning(f"Memory service not available at {self.base_url}")
            raise RuntimeError("Memory service not available")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # 404 is a valid response (resource not found), return None
                logger.debug(f"Resource not found: {url}")
                return None
            logger.error(f"Memory service error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error calling Memory service: {e}", exc_info=True)
            raise
    
    async def retrieve_context(
        self,
        query: str,
        top_k: Optional[int] = None,
        exclude_conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve relevant context for a query."""
        return await self._request(
            "POST",
            "/api/memory/retrieve-context",
            json_data={
                "query": query,
                "top_k": top_k,
                "exclude_conversation_id": exclude_conversation_id
            }
        )
    
    async def save_message(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        name: Optional[str] = None
    ):
        """Save messages to memory."""
        return await self._request(
            "POST",
            "/api/memory/save-message",
            json_data={
                "conversation_id": conversation_id,
                "messages": messages,
                "name": name
            }
        )
    
    async def get_conversation(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Get all messages from a conversation.
        
        Returns:
            List of messages if conversation exists, None if not found (404)
        """
        params = {}
        if limit:
            params["limit"] = limit
        
        try:
            result = await self._request(
                "GET",
                f"/api/conversations/{conversation_id}",
                params=params
            )
            # _request returns None for 404, which is what we want
            if result is None:
                return None
            # Extract messages from response
            if isinstance(result, dict) and "messages" in result:
                return result["messages"]
            elif isinstance(result, list):
                return result
            return result
        except RuntimeError:
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def list_conversations(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all conversations with metadata."""
        params = {"offset": offset}
        if limit:
            params["limit"] = limit
        
        try:
            return await self._request(
                "GET",
                "/api/conversations",
                params=params
            )
        except RuntimeError:
            return []
    
    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages."""
        try:
            await self._request("DELETE", f"/api/conversations/{conversation_id}")
            return True
        except RuntimeError:
            return False
    
    async def set_conversation_name(self, conversation_id: str, name: str) -> bool:
        """Set the name of a conversation."""
        try:
            await self._request(
                "PUT",
                f"/api/conversations/{conversation_id}/name",
                json_data={"name": name}
            )
            return True
        except RuntimeError:
            return False
    
    async def get_conversation_count(self) -> int:
        """Get the total number of conversations."""
        try:
            conversations = await self.list_conversations()
            return len(conversations)
        except RuntimeError:
            return 0
    
    async def get_message_count(self) -> int:
        """Get the total number of messages."""
        # This endpoint doesn't exist in Memory service yet, so we'll calculate it
        try:
            conversations = await self.list_conversations()
            total = 0
            for conv in conversations:
                total += conv.get("message_count", 0)
            return total
        except RuntimeError:
            return 0
    
    async def get_db_size(self) -> int:
        """Get size of database file in bytes."""
        # This endpoint doesn't exist in Memory service yet
        return 0
    
    async def get_last_entry_timestamp(self) -> Optional[str]:
        """Get timestamp of last entry in memory database."""
        # This endpoint doesn't exist in Memory service yet
        try:
            conversations = await self.list_conversations(limit=1)
            if conversations:
                return conversations[0].get("updated_at")
        except RuntimeError:
            pass
        return None
    
    async def get_vector_store_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        # This endpoint doesn't exist in Memory service yet
        return {
            "type": "unknown",
            "initialized": False,
            "entry_count": 0,
            "last_entry": None
        }
    
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value from the database."""
        # Settings are still stored in Gateway's local database for now
        # This can be migrated later if needed
        return default
    
    async def set_setting(self, key: str, value: str, encrypted: bool = False):
        """Set a setting value in the database."""
        # Settings are still stored in Gateway's local database for now
        # This can be migrated later if needed
        pass
    
    # Alias methods for compatibility with existing code
    async def store_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        name: Optional[str] = None
    ):
        """Alias for save_message for compatibility."""
        return await self.save_message(conversation_id, messages, name)
    
    async def is_available(self) -> bool:
        """Check if Memory service is available."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False
    
    # System prompt methods
    async def get_system_prompt(self, prompt_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get system prompt (default if prompt_id not provided)."""
        try:
            params = {}
            if prompt_id:
                params["prompt_id"] = prompt_id
            return await self._request("GET", "/api/settings/system-prompt", params=params)
        except RuntimeError:
            return None
    
    async def reset_all_data(self, keep_models: bool = True) -> Dict[str, Any]:
        """Reset all app data (conversations, settings, vector store).
        
        Args:
            keep_models: If True, keeps downloaded models
        
        Returns:
            Dictionary with counts of deleted items
        """
        try:
            result = await self._request(
                "POST",
                "/api/reset",
                params={"keep_models": keep_models}
            )
            return result or {}
        except RuntimeError:
            logger.error("Memory service not available for reset")
            raise
        except Exception as e:
            logger.error(f"Error resetting app data: {e}")
            raise
    
    async def set_system_prompt(
        self,
        content: str,
        name: Optional[str] = None,
        prompt_id: Optional[str] = None,
        is_default: bool = False
    ) -> Optional[str]:
        """Create or update system prompt."""
        try:
            if prompt_id:
                # Update existing prompt
                result = await self._request(
                    "PUT",
                    f"/api/settings/system-prompt/{prompt_id}",
                    json_data={
                        "content": content,
                        "name": name,
                        "is_default": is_default
                    }
                )
            else:
                # Create new prompt
                result = await self._request(
                    "POST",
                    "/api/settings/system-prompt",
                    json_data={
                        "content": content,
                        "name": name,
                        "is_default": is_default
                    }
                )
            return result.get("id") or prompt_id
        except RuntimeError:
            return None
    
    async def list_system_prompts(self) -> List[Dict[str, Any]]:
        """List all system prompts."""
        try:
            return await self._request("GET", "/api/settings/system-prompts")
        except RuntimeError:
            return []
    
    async def delete_system_prompt(self, prompt_id: str) -> bool:
        """Delete a system prompt."""
        try:
            await self._request("DELETE", f"/api/settings/system-prompt/{prompt_id}")
            return True
        except RuntimeError:
            return False
    
    async def update_message(
        self,
        conversation_id: str,
        message_index: int,
        new_content: str,
        role: Optional[str] = None
    ) -> bool:
        """Update a message in a conversation by index."""
        result = await self._request(
            "PUT",
            f"/conversations/{conversation_id}/messages/{message_index}",
            json_data={"content": new_content, "role": role}
        )
        return result is not None and result.get("status") == "success"
    
    async def delete_last_message(self, conversation_id: str) -> bool:
        """Delete the last message from a conversation."""
        result = await self._request(
            "DELETE",
            f"/conversations/{conversation_id}/messages/last"
        )
        return result is not None and result.get("status") == "success"
    
    async def truncate_conversation_at(self, conversation_id: str, message_index: int) -> bool:
        """Truncate conversation at a specific message index."""
        result = await self._request(
            "POST",
            f"/conversations/{conversation_id}/truncate",
            json_data={"message_index": message_index}
        )
        return result is not None and result.get("status") == "success"

