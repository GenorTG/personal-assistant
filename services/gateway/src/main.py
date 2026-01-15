"""FastAPI application entry point."""
import os
import sys
import logging
import platform
import asyncio

# Configure logger early
import time
logger = logging.getLogger(__name__)
startup_start = time.time()

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
    
    # Also suppress asyncio logger errors for ConnectionResetError
    asyncio_logger = logging.getLogger('asyncio')
    original_error = asyncio_logger.error
    
    def filtered_error(msg, *args, **kwargs):
        # Filter out ConnectionResetError messages
        if 'ConnectionResetError' in str(msg) or 'connection_lost' in str(msg) or 'ProactorBasePipeTransport' in str(msg):
            asyncio_logger.debug(msg, *args, **kwargs)
        else:
            original_error(msg, *args, **kwargs)
    
    asyncio_logger.error = filtered_error
else:
    _connection_error_handler = None

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
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
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

# WebSocket router is included via api.routes

# Create FastAPI app
logger.info("Creating FastAPI app...")
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)
logger.info("FastAPI app created")

# CORS middleware - use a custom implementation for more reliable CORS handling
import os

class CORSMiddlewareCustom(BaseHTTPMiddleware):
    """Custom CORS middleware that ensures headers are always present."""
    
    async def dispatch(self, request: Request, call_next):
        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            return Response(
                content="",
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "600",
                }
            )
        
        try:
            response = await call_next(request)
            # Add CORS headers to ALL responses
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        except Exception as e:
            # On any error, still return response with CORS headers
            logger.error(f"Error in request: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": str(e)},
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "true",
                }
            )

# Add custom CORS middleware FIRST (before other middleware)
app.add_middleware(CORSMiddlewareCustom)

# Also keep the standard CORS middleware as a fallback
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8002,http://localhost:8000").split(",")
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

# Add exception handler to ensure CORS headers on error responses
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with CORS headers and logs."""
    from .utils.request_logger import get_request_log_store
    
    # Get logs if available
    log_store = get_request_log_store()
    logs = log_store.get_logs() if log_store else None
    
    content = {"detail": exc.detail}
    if logs:
        content["logs"] = logs
    
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that includes logs in error responses."""
    from .utils.request_logger import get_request_log_store
    
    # Get logs if available
    log_store = get_request_log_store()
    logs = log_store.get_logs() if log_store else None
    
    import traceback
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    content = {"detail": f"Internal server error: {str(exc)}"}
    if logs:
        content["logs"] = logs
    
    return JSONResponse(
        status_code=500,
        content=content,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

# Add request logging middleware - completely suppress frequent polling endpoints
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    # Endpoints that are polled frequently - completely suppress logging
    QUIET_PATHS = [
        # "/api/settings", # Enable logging for settings to debug issues
        "/api/voice/stt/settings",
        "/api/voice/tts/settings",
        "/api/conversations",
        "/health",
        "/api/downloads",  # Frequently polled by frontend
        "/api/system/status",  # Frequently polled by frontend
        "/api/services/status",  # Frequently polled by frontend
        "/api/models",  # Frequently polled by frontend
    ]
    
    def __init__(self, app, enable_logging: bool = True):
        super().__init__(app)
        self.enable_logging = enable_logging
        self.log_handler = None
        if enable_logging:
            from .utils.request_logger import RequestScopedLogHandler, create_request_log_store, set_request_log_store
            self.RequestScopedLogHandler = RequestScopedLogHandler
            self.create_request_log_store = create_request_log_store
            self.set_request_log_store = set_request_log_store
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Check if client wants logs (via header or query param)
        include_logs = (
            request.headers.get("X-Include-Logs", "").lower() == "true" or
            request.query_params.get("include_logs", "").lower() == "true"
        )
        
        # Set up request-scoped logging if enabled and requested
        log_store = None
        log_handler = None
        if self.enable_logging and include_logs and settings.enable_request_logging:
            log_store = self.create_request_log_store(max_logs=settings.max_logs_per_request)
            self.set_request_log_store(log_store)
            
            # Create and attach log handler
            log_handler = self.RequestScopedLogHandler(max_logs=settings.max_logs_per_request)
            # Set log level based on settings
            if settings.include_debug_logs:
                log_handler.setLevel(logging.DEBUG)
            else:
                log_handler.setLevel(logging.INFO)
            
            # Add handler to root logger to capture all logs
            root_logger = logging.getLogger()
            root_logger.addHandler(log_handler)
        
        # Completely suppress logging for quiet paths
        is_quiet = any(path.startswith(quiet_path) for quiet_path in self.QUIET_PATHS)
        if not is_quiet:
            # For other paths, log normally
            logger = logging.getLogger(__name__)
            logger.info("%s %s", request.method, path)
        
        try:
            response = await call_next(request)
            
            if not is_quiet:
                logger.info("%s %s -> %s", request.method, path, response.status_code)
            
            # Attach logs to response if available
            if log_store and log_store.logs:
                # Add log summary to headers
                summary = log_store.get_summary()
                response.headers["X-Logs-Summary"] = str(summary)
                response.headers["X-Logs-Count"] = str(len(log_store.logs))
            
            return response
        finally:
            # Clean up log handler
            if log_handler:
                root_logger = logging.getLogger()
                root_logger.removeHandler(log_handler)
            # Clear request log store
            if log_store:
                self.set_request_log_store(None)

# Always enable request logging
app.add_middleware(RequestLoggingMiddleware)

# Note: We're not mounting static files since Next.js runs separately
# The NoCacheStaticFiles class is kept for backward compatibility but not used

# Include routers - API routes must be registered first to take precedence
# Routes already have /api/ prefix, so no need to add prefix here
app.include_router(router, tags=["api"])
from .api import upload
app.include_router(upload.router, tags=["voice"])
# WebSocket router is included via api.routes

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
    # Debug logging removed - use standard logger instead
    startup_start_time = time.time()
    
    # Set asyncio exception handler on Windows to suppress connection errors
    if platform.system() == "Windows" and _connection_error_handler:
        try:
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(_connection_error_handler)
            logger.debug("Configured asyncio exception handler for Windows")
        except Exception as e:
            logger.debug(f"Could not set asyncio exception handler: {e}")
    
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
    
    # Note: CUDA detection is handled by the LLM service, not the gateway
    # The gateway just proxies requests to the LLM service

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
    # Debug logging removed - use standard logger instead


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    import logging
    import signal
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

# Register signal handlers for cleanup on SIGTERM/SIGINT
def setup_signal_handlers():
    """Setup signal handlers to cleanup processes on exit."""
    import signal
    import logging
    logger = logging.getLogger(__name__)
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating cleanup...")
        from .services.service_manager import service_manager
        
        # Try to cleanup LLM server process synchronously
        try:
            if service_manager.llm_manager and hasattr(service_manager.llm_manager, 'server_manager'):
                if service_manager.llm_manager.server_manager.process:
                    logger.info("Killing LLM server process...")
                    try:
                        service_manager.llm_manager.server_manager.process.terminate()
                        service_manager.llm_manager.server_manager.process.wait(timeout=2)
                    except Exception:
                        try:
                            service_manager.llm_manager.server_manager.process.kill()
                            service_manager.llm_manager.server_manager.process.wait(timeout=1)
                        except Exception:
                            pass
                    logger.info("✓ LLM server process terminated")
        except Exception as e:
            logger.error(f"Error in signal handler cleanup: {e}", exc_info=True)
        finally:
            # Exit after cleanup
            sys.exit(0)
    
    # Register handlers for SIGTERM and SIGINT (only on Unix-like systems)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, signal_handler)

# Setup signal handlers on module load
try:
    setup_signal_handlers()
except Exception as e:
    logger.warning(f"Could not setup signal handlers: {e}")
