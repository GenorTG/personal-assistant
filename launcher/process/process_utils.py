"""Utility functions for process management."""

import platform
import subprocess
import time
from typing import Optional

# Try to import psutil, fallback if not available
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def kill_process_tree(pid: int) -> bool:
    """Kill a process and all its children (cross-platform)."""
    try:
        if platform.system() == "Windows":
            # Windows: Use taskkill to kill process tree - be more aggressive
            # Hide console window
            creation_flags = subprocess.CREATE_NO_WINDOW
            
            # Check if process exists first
            try:
                import psutil
                proc = psutil.Process(pid)
                if not proc.is_running():
                    return True  # Already dead
            except (psutil.NoSuchProcess, ImportError):
                # Process doesn't exist or psutil not available
                pass
            
            # Force kill immediately (skip graceful - we want it dead NOW)
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
                creationflags=creation_flags
            )
            
            # Wait and verify it's actually dead
            time.sleep(0.5)
            
            # Double-check and kill again if still alive
            try:
                import psutil
                proc = psutil.Process(pid)
                if proc.is_running():
                    # Still alive - kill again more aggressively
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        timeout=5,
                        creationflags=creation_flags
                    )
                    time.sleep(0.5)
            except (psutil.NoSuchProcess, ImportError):
                # Process is dead or psutil not available - assume success
                pass
            
            return True  # Assume success if we got here
        else:
            # Unix: Use psutil to kill process tree if available, otherwise use signals
            if HAS_PSUTIL:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try:
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    try:
                        parent.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            else:
                # Fallback: use signals
                import os
                import signal
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    time.sleep(0.5)
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                except (ProcessLookupError, OSError):
                    try:
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(0.5)
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
        return True
    except Exception:
        return False


def kill_process_on_port(port: int) -> bool:
    """Find and kill the process using a specific port."""
    try:
        killed_any = False
        if platform.system() == "Windows":
            # Find process using port - try multiple times to catch all processes
            # Hide console window
            creation_flags = subprocess.CREATE_NO_WINDOW
            seen_pids = set()
            for attempt in range(5):  # More attempts to catch all processes
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=creation_flags
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        # Check for both LISTENING and ESTABLISHED connections on this port
                        if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                            parts = line.split()
                            if len(parts) >= 5:
                                try:
                                    pid = int(parts[-1])
                                    if pid not in seen_pids:
                                        seen_pids.add(pid)
                                    if kill_process_tree(pid):
                                        killed_any = True
                                        # Wait a bit for the process to fully terminate
                                        time.sleep(0.3)
                                except (ValueError, IndexError):
                                    pass
                # Wait before next attempt
                if attempt < 4:
                    time.sleep(0.3)
        else:
            # Unix: Use lsof or fuser
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    pids = [int(pid) for pid in result.stdout.strip().split('\n') if pid.strip()]
                    for pid in pids:
                        if kill_process_tree(pid):
                            killed_any = True
                            time.sleep(0.5)
            except Exception:
                pass
        return killed_any
    except Exception:
        return False


def cleanup_all_service_ports(ports: list[int]) -> dict[int, bool]:
    """Clean up all processes using service ports. Returns dict of port -> success."""
    results = {}
    for port in ports:
        results[port] = kill_process_on_port(port)
    return results


def find_all_processes_on_ports(ports: list[int]) -> dict[int, list[int]]:
    """Find all PIDs using the specified ports. Returns dict of port -> list of PIDs."""
    port_pids = {port: [] for port in ports}
    
    try:
        if platform.system() == "Windows":
            # Get all network connections
            # Hide console window
            creation_flags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creation_flags
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    for port in ports:
                        if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                            parts = line.split()
                            if len(parts) >= 5:
                                try:
                                    pid = int(parts[-1])
                                    if pid not in port_pids[port]:
                                        port_pids[port].append(pid)
                                except (ValueError, IndexError):
                                    pass
        else:
            # Unix: Use lsof
            for port in ports:
                try:
                    result = subprocess.run(
                        ["lsof", "-ti", f":{port}"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        pids = [int(pid) for pid in result.stdout.strip().split('\n') if pid.strip()]
                        port_pids[port] = pids
                except Exception:
                    pass
    except Exception:
        pass
    
    return port_pids

