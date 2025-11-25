"""Process management utilities for graceful shutdown and process detection."""
import os
import sys
import signal
import socket
import logging
from pathlib import Path
from typing import Optional, Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None  # type: ignore

logger = logging.getLogger(__name__)


def check_port_in_use(host: str, port: int) -> bool:
    """Check if a port is in use.
    
    Args:
        host: Host address
        port: Port number
        
    Returns:
        True if port is in use, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def find_process_on_port(port: int) -> Optional[Any]:
    """Find the process using a specific port.
    
    Args:
        port: Port number to check
        
    Returns:
        Process object if found, None otherwise
    """
    if not PSUTIL_AVAILABLE:
        logger.warning("psutil not available, cannot find process by port")
        return None
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                connections = proc.connections()
                for conn in connections:
                    if conn.laddr.port == port:
                        # Check if it's our backend process
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any('start.py' in str(arg) or 'backend.src.main:app' in str(arg) or 'uvicorn' in str(arg).lower() for arg in cmdline):
                            return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.warning(f"Error finding process on port {port}: {e}")
    return None


def kill_process_gracefully(proc, timeout: int = 5) -> bool:
    """Attempt to kill a process gracefully.
    
    Args:
        proc: Process to kill (psutil.Process object)
        timeout: Timeout in seconds before force kill
        
    Returns:
        True if process was killed, False otherwise
    """
    if not PSUTIL_AVAILABLE or proc is None:
        return False
    
    try:
        logger.info(f"Attempting graceful shutdown of process {proc.pid}")
        proc.terminate()  # Send SIGTERM
        
        try:
            proc.wait(timeout=timeout)
            logger.info(f"Process {proc.pid} terminated gracefully")
            return True
        except psutil.TimeoutExpired:
            logger.warning(f"Process {proc.pid} did not terminate, forcing kill")
            proc.kill()  # Force kill
            proc.wait(timeout=2)
            logger.info(f"Process {proc.pid} force killed")
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.warning(f"Could not kill process {proc.pid}: {e}")
        return False


def cleanup_existing_backend(host: str, port: int) -> bool:
    """Check for and cleanup existing backend process.
    
    Args:
        host: Host address
        port: Port number
        
    Returns:
        True if cleanup was attempted, False if no process found
    """
    if not check_port_in_use(host, port):
        return False
    
    logger.info(f"Port {port} is in use, checking for existing backend process...")
    proc = find_process_on_port(port)
    
    if proc:
        logger.info(f"Found existing backend process (PID: {proc.pid})")
        return kill_process_gracefully(proc)
    else:
        logger.warning(f"Port {port} is in use but couldn't identify backend process")
        return False


def setup_signal_handlers(shutdown_callback=None, enable_console_handler=True):
    """Setup signal handlers for graceful shutdown.
    
    Args:
        shutdown_callback: Optional callback function to call on shutdown
        enable_console_handler: If False, don't install Windows console handler (for Uvicorn reload)
    """
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        if shutdown_callback:
            try:
                shutdown_callback()
            except Exception as e:
                logger.error(f"Error in shutdown callback: {e}")
        # Give a moment for cleanup, then exit
        import time
        time.sleep(0.5)
        sys.exit(0)
    
    # Register signal handlers
    if sys.platform != 'win32':
        # Unix signals
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    else:
        # Windows signals
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        # Windows-specific: handle console close
        # Only install if explicitly enabled (disabled for Uvicorn reload mode)
        if enable_console_handler:
            try:
                import win32api
                import win32con
                
                def console_handler(dwCtrlType):
                    # Only handle window close event, not Ctrl+C (Uvicorn handles that)
                    # CTRL_CLOSE_EVENT = 2 (window close button clicked)
                    # CTRL_C_EVENT = 0 (Ctrl+C) - Uvicorn reloader uses this, so ignore it
                    # CTRL_BREAK_EVENT = 1 (Ctrl+Break)
                    
                    # Only handle window close - let Uvicorn handle Ctrl+C for reload
                    if dwCtrlType == win32con.CTRL_CLOSE_EVENT:
                        logger.info(f"Console window close event received (type {dwCtrlType})")
                        signal_handler(signal.SIGTERM, None)
                        return True
                    elif dwCtrlType == win32con.CTRL_BREAK_EVENT:
                        logger.info(f"Ctrl+Break event received (type {dwCtrlType})")
                        signal_handler(signal.SIGTERM, None)
                        return True
                    # Return False for Ctrl+C - let Uvicorn handle it (needed for reload)
                    # This prevents the handler from interfering with Uvicorn's reloader
                    return False
                
                win32api.SetConsoleCtrlHandler(console_handler, True)
                logger.info("Windows console handler installed (will handle window close gracefully)")
            except ImportError:
                # win32api not available, use basic signal handling
                logger.warning("win32api not available, console close may not be handled gracefully")
                logger.warning("Install pywin32 for better Windows console handling: pip install pywin32")
                pass
        else:
            logger.debug("Console handler disabled (running with Uvicorn reload)")

