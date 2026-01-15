"""Port checking utilities for Chatterbox service."""

import socket


def check_port_available(port: int) -> bool:
    """Check if the service port is actually accessible."""
    # Try localhost first
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        if result == 0:
            return True
    except Exception:
        pass
        
    # Try 127.0.0.1 explicitly
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        if result == 0:
            return True
    except Exception:
        pass
        
    return False

