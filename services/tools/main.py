"""Tool Service - FastAPI application for tool execution and management."""
import logging
import sys
import platform
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.routes import router
from src.config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Fix Windows asyncio connection errors
if platform.system() == "Windows":
    def _suppress_connection_errors(loop, context):
        """Suppress non-critical connection errors on Windows."""
        exception = context.get('exception')
        if isinstance(exception, ConnectionResetError):
            # This is a non-critical error that happens during connection cleanup
            # It's safe to ignore on Windows - it's a known asyncio/Windows issue
            return
        # For other exceptions, use default handler
        if hasattr(loop, 'default_exception_handler') and loop.default_exception_handler:
            loop.default_exception_handler(context)
        else:
            # Fallback: just log to debug
            logger.debug(f"Unhandled asyncio exception: {context}")
    
    # Store handler for later use
    _connection_error_handler = _suppress_connection_errors
else:
    _connection_error_handler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Tool Service...")
    logger.info(f"Port: {settings.port}")
    
    # Set asyncio exception handler on Windows to suppress connection errors
    if platform.system() == "Windows" and _connection_error_handler:
        try:
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(_connection_error_handler)
            logger.debug("Configured asyncio exception handler for Windows")
        except Exception as e:
            logger.debug(f"Could not set asyncio exception handler: {e}")
    
    # Initialize tool registry
    from src.tools.registry import ToolRegistry
    tool_registry = ToolRegistry()
    await tool_registry.initialize()
    app.state.tool_registry = tool_registry
    
    logger.info("Tool Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Tool Service...")


# Create FastAPI app
app = FastAPI(
    title="Tool Service",
    description="Tool execution and management service for Personal Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "tools",
        "port": settings.port
    }


if __name__ == "__main__":
    import uvicorn
    
    # Also suppress asyncio logger errors for ConnectionResetError on Windows
    if platform.system() == "Windows":
        asyncio_logger = logging.getLogger('asyncio')
        original_error = asyncio_logger.error
        
        def filtered_error(msg, *args, **kwargs):
            # Filter out ConnectionResetError messages
            if 'ConnectionResetError' in str(msg) or 'connection_lost' in str(msg):
                asyncio_logger.debug(msg, *args, **kwargs)
            else:
                original_error(msg, *args, **kwargs)
        
        asyncio_logger.error = filtered_error
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

