"""Memory Service - FastAPI application for memory and context management."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.routes import router
from src.config.settings import settings

# Import MemoryStore for type hints
from src.memory.store import MemoryStore

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
    logger.info("Starting Memory Service...")
    logger.info(f"Port: {settings.port}")
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"Vector Store: {settings.vector_store_dir}")
    
    # Initialize memory store
    from src.memory.store import MemoryStore
    memory_store = MemoryStore()
    await memory_store.initialize()
    app.state.memory_store = memory_store
    
    logger.info("Memory Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Memory Service...")
    if hasattr(app.state, 'memory_store'):
        app.state.memory_store.vector_store.cleanup()
    logger.info("Memory Service stopped")


# Create FastAPI app
app = FastAPI(
    title="Memory Service",
    description="Memory and context management service for Personal Assistant",
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
        "service": "memory",
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

