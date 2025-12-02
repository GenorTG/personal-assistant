"""Memory tools for explicit save/recall."""
from typing import Dict, Any, Optional
import httpx
from ..base import BaseTool
from ...config.settings import settings


class MemoryTools(BaseTool):
    """Tools for explicitly saving and recalling memories."""
    
    def __init__(self):
        self.memory_service_url = "http://localhost:8005"
    
    @property
    def name(self) -> str:
        return "memory"
    
    @property
    def description(self) -> str:
        return "Save and recall explicit memories. Use this to store important information that should be remembered across conversations."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["save", "recall", "search"],
                        "description": "Memory operation: save a memory, recall by key, or search memories"
                    },
                    "key": {
                        "type": "string",
                        "description": "Memory key/identifier (for save and recall operations)"
                    },
                    "value": {
                        "type": "string",
                        "description": "Memory value to save (for save operation)"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (for search operation)"
                    }
                },
                "required": ["operation"]
            }
        }
    
    async def execute(
        self,
        operation: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute memory operation.
        
        Args:
            operation: Operation to perform
            key: Memory key
            value: Memory value
            query: Search query
        
        Returns:
            Dictionary with operation result
        """
        try:
            if operation == "save":
                if not key or not value:
                    return {
                        "error": "Both 'key' and 'value' are required for save operation"
                    }
                
                # Save to Memory service via conversation storage
                # Use a special conversation ID for explicit memories
                conversation_id = f"memory_{key}"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{self.memory_service_url}/api/memory/save-message",
                        json={
                            "conversation_id": conversation_id,
                            "messages": [{
                                "role": "user",
                                "content": f"Memory: {key} = {value}",
                                "timestamp": "2024-01-01T00:00:00Z"
                            }],
                            "name": f"Memory: {key}"
                        }
                    )
                    
                    if response.status_code == 200:
                        return {
                            "result": {
                                "message": f"Memory saved: {key}",
                                "key": key,
                                "value": value
                            }
                        }
                    else:
                        return {
                            "error": f"Failed to save memory: {response.status_code}"
                        }
            
            elif operation == "recall":
                if not key:
                    return {
                        "error": "'key' is required for recall operation"
                    }
                
                # Retrieve from Memory service
                conversation_id = f"memory_{key}"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.memory_service_url}/api/conversations/{conversation_id}"
                    )
                    
                    if response.status_code == 200:
                        messages = response.json()
                        if messages:
                            # Extract value from last message
                            last_msg = messages[-1]
                            content = last_msg.get("content", "")
                            # Extract value from "Memory: key = value" format
                            if " = " in content:
                                value = content.split(" = ", 1)[1]
                                return {
                                    "result": {
                                        "key": key,
                                        "value": value
                                    }
                                }
                        
                        return {
                            "error": f"Memory not found: {key}"
                        }
                    elif response.status_code == 404:
                        return {
                            "error": f"Memory not found: {key}"
                        }
                    else:
                        return {
                            "error": f"Failed to recall memory: {response.status_code}"
                        }
            
            elif operation == "search":
                if not query:
                    return {
                        "error": "'query' is required for search operation"
                    }
                
                # Search Memory service
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{self.memory_service_url}/api/memory/retrieve-context",
                        json={
                            "query": query,
                            "top_k": 5
                        }
                    )
                    
                    if response.status_code == 200:
                        context = response.json()
                        retrieved = context.get("retrieved_messages", [])
                        
                        return {
                            "result": {
                                "query": query,
                                "memories": retrieved,
                                "count": len(retrieved)
                            }
                        }
                    else:
                        return {
                            "error": f"Failed to search memories: {response.status_code}"
                        }
            
            else:
                return {
                    "error": f"Unknown operation: {operation}"
                }
        
        except httpx.ConnectError:
            return {
                "error": "Memory service not available"
            }
        except Exception as e:
            return {
                "error": f"Error performing memory operation: {str(e)}"
            }

