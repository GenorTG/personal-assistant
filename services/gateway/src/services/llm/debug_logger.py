"""Debug logger for LLM requests and responses."""
import json
import time
from typing import List, Dict, Any, Optional
from collections import deque
from threading import Lock

# Global log store with thread-safe access
_llm_logs: deque = deque(maxlen=100)  # Keep last 100 requests
_log_lock = Lock()


class LLMDebugLog:
    """Stores debug information for a single LLM request/response."""
    
    def __init__(self):
        self.timestamp = time.time()
        self.request: Optional[Dict[str, Any]] = None
        self.response: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.duration_ms: Optional[float] = None
        self.tool_calls: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "request": self.request,
            "response": self.response,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tool_calls": self.tool_calls,
            "metadata": self.metadata
        }


def log_llm_request(
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> LLMDebugLog:
    """Log an LLM request.
    
    Args:
        payload: The request payload being sent to the LLM
        metadata: Optional metadata about the request
        
    Returns:
        LLMDebugLog instance that can be updated with response
    """
    log_entry = LLMDebugLog()
    
    # Sanitize payload for logging (remove very large content if needed)
    sanitized_payload = _sanitize_payload(payload.copy())
    log_entry.request = sanitized_payload
    log_entry.metadata = metadata or {}
    
    with _log_lock:
        _llm_logs.append(log_entry)
    
    return log_entry


def log_llm_response(
    log_entry: LLMDebugLog,
    response: Dict[str, Any],
    duration_ms: float,
    tool_calls: Optional[List[Dict[str, Any]]] = None
):
    """Update log entry with response information.
    
    Args:
        log_entry: The LLMDebugLog instance from log_llm_request
        response: The response from the LLM
        duration_ms: Request duration in milliseconds
        tool_calls: Extracted tool calls if any
    """
    log_entry.response = _sanitize_payload(response.copy())
    log_entry.duration_ms = duration_ms
    if tool_calls:
        log_entry.tool_calls = tool_calls


def log_llm_error(
    log_entry: LLMDebugLog,
    error: str,
    duration_ms: Optional[float] = None
):
    """Update log entry with error information.
    
    Args:
        log_entry: The LLMDebugLog instance from log_llm_request
        error: Error message
        duration_ms: Request duration in milliseconds if available
    """
    log_entry.error = error
    if duration_ms is not None:
        log_entry.duration_ms = duration_ms


def get_llm_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent LLM logs.
    
    Args:
        limit: Maximum number of logs to return
        
    Returns:
        List of log entries as dictionaries
    """
    with _log_lock:
        logs = list(_llm_logs)
    
    # Return most recent logs first
    logs.reverse()
    return [log.to_dict() for log in logs[:limit]]


def clear_llm_logs():
    """Clear all stored LLM logs."""
    with _log_lock:
        _llm_logs.clear()


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize payload for logging (truncate very long content)."""
    sanitized = payload.copy()
    
    # Truncate very long messages/content
    if "messages" in sanitized:
        messages = sanitized["messages"]
        for msg in messages:
            if isinstance(msg, dict) and "content" in msg:
                content = msg["content"]
                if isinstance(content, str) and len(content) > 5000:
                    msg["content"] = content[:5000] + f"... [truncated, total length: {len(content)}]"
    
    # Truncate very long tool definitions
    if "tools" in sanitized:
        tools = sanitized["tools"]
        for tool in tools:
            if isinstance(tool, dict) and "function" in tool:
                func = tool["function"]
                if "description" in func and isinstance(func["description"], str) and len(func["description"]) > 1000:
                    func["description"] = func["description"][:1000] + "... [truncated]"
    
    return sanitized
