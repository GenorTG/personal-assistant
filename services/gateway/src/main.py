"""FastAPI application entry point."""
import os
import logging

# Configure logger early
import time
logger = logging.getLogger(__name__)
startup_start = time.time()

# Check NumPy version compatibility BEFORE importing ChromaDB
try:
    import numpy as np
    numpy_version = np.__version__
    major_version = int(numpy_version.split('.')[0])
    if major_version >= 2:
        logger.error("=" * 60)
        logger.error("CRITICAL: NumPy 2.x detected! ChromaDB 0.5.0 is incompatible.")
        logger.error(f"Current NumPy version: {numpy_version}")
        logger.error("=" * 60)
        logger.error("FIX: Run: pip install 'numpy>=1.22.0,<2.0.0' --force-reinstall")
        logger.error("=" * 60)
        raise ImportError(
            f"NumPy {numpy_version} is incompatible with ChromaDB 0.5.0. "
            "Please install NumPy 1.x: pip install 'numpy>=1.22.0,<2.0.0' --force-reinstall"
        )
    else:
        logger.info(f"NumPy version check: OK (v{numpy_version})")
except ImportError as e:
    if "incompatible" in str(e).lower():
        raise
    # NumPy not installed yet, will be installed by dependencies
    pass

# Log that we're starting to import main.py
logger.info("=" * 60)
logger.info("IMPORTING: backend.src.main")
logger.info("=" * 60)

# Disable ChromaDB telemetry before any imports that might use it
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Suppress ChromaDB telemetry errors
chromadb_telemetry_logger = logging.getLogger("chromadb.telemetry.product.posthog")
chromadb_telemetry_logger.setLevel(logging.CRITICAL)
chromadb_telemetry_logger.disabled = True

logger.info("ChromaDB telemetry disabled")

logger.info("Importing FastAPI and dependencies...")
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
logger.info("FastAPI imports complete")

logger.info("Importing settings and routers...")
from .config.settings import settings
logger.info(f"Settings loaded: {settings.app_name} v{settings.app_version}")

logger.info("Importing API routes...")
logger.info("  (This imports service_manager, which may take a moment)")
import_start = time.time()
from .api.routes import router
import_time = time.time() - import_start
logger.info("API routes imported (took %.2fs)", import_time)

logger.info("Importing WebSocket router...")
from .api.websocket import ws_router
logger.info("WebSocket router imported")

# Create FastAPI app
logger.info("Creating FastAPI app...")
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)
logger.info("FastAPI app created")

# CORS middleware
import os
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
if settings.debug:
    # In debug mode, allow all origins for development
    cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request logging middleware - completely suppress frequent polling endpoints
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    # Endpoints that are polled frequently - completely suppress logging
    QUIET_PATHS = [
        "/api/settings",
        "/api/voice/stt/settings",
        "/api/voice/tts/settings",
        "/api/conversations",
        "/health",
    ]
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Completely suppress logging for quiet paths
        is_quiet = any(path.startswith(quiet_path) for quiet_path in self.QUIET_PATHS)
        if is_quiet:
            # Just process the request without any logging
            return await call_next(request)
        
        # For other paths, log normally
        import logging
        logger = logging.getLogger(__name__)
        logger.info("%s %s", request.method, path)
        response = await call_next(request)
        logger.info("%s %s -> %s", request.method, path, response.status_code)
        return response

# Always enable request logging
app.add_middleware(RequestLoggingMiddleware)

# Note: We're not mounting static files since Next.js runs separately
# The NoCacheStaticFiles class is kept for backward compatibility but not used

# Include routers - API routes must be registered first to take precedence
# Routes already have /api/ prefix, so no need to add prefix here
app.include_router(router, tags=["api"])
from .api import upload
app.include_router(upload.router, tags=["voice"])
app.include_router(ws_router, tags=["websocket"])

# Log registered routes - always enabled
import_time = time.time() - startup_start
logger.info(f"Application imports completed in {import_time:.2f} seconds")
logger.info("=" * 60)
logger.info("REGISTERED API ROUTES:")
logger.info("=" * 60)
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        logger.info(f"  {list(route.methods)} {route.path}")
    elif hasattr(route, 'path'):
        logger.info(f"  {route.path}")
logger.info("=" * 60)

# Serve static files (old frontend) - only mount if Next.js isn't being used
# For Next.js frontend running separately, this won't interfere
# Note: API routes are registered first, so they take precedence
# IMPORTANT: Don't mount static files if Next.js frontend exists (it runs separately)
frontend_path = Path(__file__).parent.parent.parent / "frontend"
frontend_next_path = Path(__file__).parent.parent.parent / "frontend-next"
# Only mount old frontend if Next.js frontend doesn't exist (backward compatibility)
# Since we're using Next.js, we should NOT mount static files
if False and frontend_path.exists() and not frontend_next_path.exists():
    # Use custom StaticFiles class that adds no-cache headers in debug mode
    static_files = NoCacheStaticFiles(directory=str(frontend_path), html=True)
    # Mount at root but API routes will take precedence
    app.mount("/", static_files, name="static")


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    startup_start_time = time.time()
    
    # Log all registered routes again at startup
    logger.info("=" * 60)
    logger.info("STARTUP: Verifying API routes are registered")
    logger.info("=" * 60)
    api_routes = [r for r in app.routes if hasattr(r, 'path') and '/api/' in str(getattr(r, 'path', ''))]
    for route in api_routes:
        if hasattr(route, 'methods'):
            logger.info(f"  {list(route.methods)} {getattr(route, 'path', 'unknown')}")
        else:
            logger.info(f"  {getattr(route, 'path', 'unknown')}")
    logger.info(f"Total API routes found: {len(api_routes)}")
    logger.info("=" * 60)
    
    # Check hardware acceleration status
    try:
        from .services.llm.cuda_installer import check_cuda_available, check_llama_cuda_support
        cuda_available = check_cuda_available()
        llama_cuda, error = check_llama_cuda_support()
        
        if cuda_available:
            if llama_cuda:
                logger.info("✅ Hardware Acceleration: CUDA detected and llama-cpp-python supports it.")
            else:
                logger.warning("⚠️  PERFORMANCE WARNING: CUDA GPU detected but llama-cpp-python is NOT using it!")
                logger.warning(f"   Reason: {error}")
                logger.warning("   Run 'backend/scripts/install_dependencies.py' to fix this.")
        else:
            logger.info("ℹ️  Hardware Acceleration: No CUDA GPU detected. Running in CPU mode.")
    except Exception as e:
        logger.error(f"Failed to check hardware acceleration: {e}")

    logger.info("Initializing services (this may take a moment)...")
    from .services.service_manager import service_manager
    
    service_start = time.time()
    await service_manager.initialize()
    service_time = time.time() - service_start
    
    total_startup_time = time.time() - startup_start_time
    logger.info("=" * 60)
    logger.info("Services initialized successfully")
    logger.info(f"Service initialization took: {service_time:.2f} seconds")
    logger.info(f"Total startup time: {total_startup_time:.2f} seconds")
    logger.info("=" * 60)
    logger.info("Backend is ready and accepting connections!")
    logger.info(f"Health check: http://{settings.host}:{settings.port}/health")
    logger.info(f"API docs: http://{settings.host}:{settings.port}/docs")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("SHUTDOWN: Initiating graceful shutdown")
    logger.info("=" * 60)
    
    from .services.service_manager import service_manager
    try:
        await service_manager.shutdown()
        logger.info("Services shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)
    finally:
        logger.info("=" * 60)
        logger.info("Shutdown complete")
        logger.info("=" * 60)
