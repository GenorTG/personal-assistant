"""Tool Service - FastAPI application for tool execution and management."""
import logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Tool Service...")
    logger.info(f"Port: {settings.port}")
    
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
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

