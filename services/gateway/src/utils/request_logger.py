"""Request-scoped logging handler for capturing logs per API request."""
import logging
import traceback
import time
from contextvars import ContextVar
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict

# Context variable to store logs for the current request
_request_logs: ContextVar[Optional['RequestLogStore']] = ContextVar('request_logs', default=None)


@dataclass
class LogEntry:
    """A single log entry captured during a request."""
    timestamp: float
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger: str
    message: str
    exception: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log entry to dictionary."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "exception": self.exception
        }


@dataclass
class RequestLogStore:
    """Stores logs for a single request."""
    logs: List[LogEntry] = field(default_factory=list)
    max_logs: int = 1000
    
    def add_log(
        self,
        level: str,
        logger_name: str,
        message: str,
        exception: Optional[Exception] = None
    ):
        """Add a log entry."""
        if len(self.logs) >= self.max_logs:
            # Remove oldest log if we've hit the limit
            self.logs.pop(0)
        
        exception_str = None
        if exception:
            exception_str = ''.join(traceback.format_exception(
                type(exception),
                exception,
                exception.__traceback__
            ))
        
        entry = LogEntry(
            timestamp=time.time(),
            level=level,
            logger=logger_name,
            message=str(message),
            exception=exception_str
        )
        self.logs.append(entry)
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all logs as dictionaries."""
        return [log.to_dict() for log in self.logs]
    
    def get_summary(self) -> Dict[str, int]:
        """Get summary of logs by level."""
        summary = defaultdict(int)
        for log in self.logs:
            summary[log.level] += 1
        return dict(summary)
    
    def clear(self):
        """Clear all logs."""
        self.logs.clear()


class RequestScopedLogHandler(logging.Handler):
    """Custom logging handler that captures logs in request-scoped storage."""
    
    def __init__(self, max_logs: int = 1000):
        super().__init__()
        self.max_logs = max_logs
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to the request log store."""
        try:
            log_store = _request_logs.get()
            if log_store is None:
                # No request context, skip
                return
            
            # Format the message
            try:
                message = self.format(record)
            except Exception:
                message = record.getMessage()
            
            # Get exception info if available
            exception = None
            if record.exc_info:
                exception = record.exc_info[1]
            
            # Add to store
            log_store.add_log(
                level=record.levelname,
                logger_name=record.name,
                message=message,
                exception=exception
            )
        except Exception:
            # Don't let logging errors break the application
            pass


def get_request_log_store() -> Optional[RequestLogStore]:
    """Get the current request's log store."""
    return _request_logs.get()


def set_request_log_store(store: Optional[RequestLogStore]):
    """Set the current request's log store."""
    _request_logs.set(store)


def create_request_log_store(max_logs: int = 1000) -> RequestLogStore:
    """Create a new request log store."""
    return RequestLogStore(max_logs=max_logs)


