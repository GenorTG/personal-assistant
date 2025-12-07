"""
Process watcher that monitors the launcher and kills subprocesses when it dies.

This watcher runs as a separate process and ensures cleanup happens even if:
- The launcher is force-killed
- The launcher crashes
- The launcher is closed normally
"""

import os
import sys
import time
import signal
import platform
import subprocess
import threading
from pathlib import Path
from typing import List, Set

# Try to import psutil for better process management
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Known service ports to clean up
KNOWN_PORTS = [8000, 8001, 8002, 8003, 8004, 8005, 8006, 4123, 8880]


def kill_process_on_port(port: int) -> bool:
    """Kill all processes using a specific port - optimized for speed."""
    try:
        if platform.system() == "Windows":
            # Windows: Use netstat to find PID, then taskkill
            creation_flags = subprocess.CREATE_NO_WINDOW
            
            # Find processes on the port (with shorter timeout for faster cleanup)
            try:
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=2,  # Reduced from 5 to 2 seconds
                    creationflags=creation_flags
                )
                
                pids = set()
                for line in result.stdout.splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            try:
                                pid = int(parts[-1])
                                pids.add(pid)
                            except ValueError:
                                pass
                
                # Kill all processes found (with shorter timeout)
                for pid in pids:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True,
                            timeout=1,  # Reduced from 5 to 1 second
                            creationflags=creation_flags
                        )
                    except Exception:
                        pass
                
                return len(pids) > 0
            except Exception:
                return False
        else:
            # Unix: Use lsof or fuser
            pids = set()
            
            # Try lsof first
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for pid_str in result.stdout.strip().split():
                        try:
                            pids.add(int(pid_str))
                        except ValueError:
                            pass
            except Exception:
                pass
            
            # Try fuser as fallback
            if not pids:
                try:
                    result = subprocess.run(
                        ["fuser", "-k", f"{port}/tcp"],
                        capture_output=True,
                        timeout=5
                    )
                except Exception:
                    pass
            
            # Kill processes using psutil if available
            if HAS_PSUTIL and pids:
                for pid in pids:
                    try:
                        proc = psutil.Process(pid)
                        proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            
            return len(pids) > 0
    except Exception:
        return False


def kill_all_service_processes():
    """Kill all processes on known service ports - optimized for speed."""
    # Use threading to kill ports in parallel for faster cleanup
    def kill_port(port):
        try:
            kill_process_on_port(port)
        except Exception:
            pass
    
    threads = []
    for port in KNOWN_PORTS:
        thread = threading.Thread(target=kill_port, args=(port,), daemon=True)
        thread.start()
        threads.append(thread)
    
    # Wait for all threads to complete (with timeout)
    for thread in threads:
        thread.join(timeout=2)  # Max 2 seconds per port
    
    # Also do a quick sweep to kill any remaining processes on these ports
    # This is a fallback in case parallel cleanup missed something
    for port in KNOWN_PORTS:
        try:
            kill_process_on_port(port)
        except Exception:
            pass
    
    return len(KNOWN_PORTS)  # Return count of ports checked


def find_process_tree(pid: int) -> Set[int]:
    """Find all child processes of a given PID."""
    pids = {pid}
    
    if HAS_PSUTIL:
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                pids.add(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    else:
        # Fallback: Use platform-specific commands
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ["wmic", "process", "where", f"ParentProcessId={pid}", "get", "ProcessId"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                for line in result.stdout.splitlines():
                    try:
                        child_pid = int(line.strip())
                        if child_pid != pid:
                            pids.add(child_pid)
                            # Recursively find grandchildren
                            pids.update(find_process_tree(child_pid))
                    except ValueError:
                        pass
            except Exception:
                pass
        else:
            # Unix: Use pgrep
            try:
                result = subprocess.run(
                    ["pgrep", "-P", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in result.stdout.splitlines():
                    try:
                        child_pid = int(line.strip())
                        pids.add(child_pid)
                        # Recursively find grandchildren
                        pids.update(find_process_tree(child_pid))
                    except ValueError:
                        pass
            except Exception:
                pass
    
    return pids


def kill_process_tree(pid: int) -> bool:
    """Kill a process and all its children."""
    try:
        pids = find_process_tree(pid)
        
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW
            for pid_to_kill in pids:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid_to_kill)],
                        capture_output=True,
                        timeout=5,
                        creationflags=creation_flags
                    )
                except Exception:
                    pass
        else:
            # Unix: Kill parent first, then children
            for pid_to_kill in sorted(pids, reverse=True):  # Kill children first
                try:
                    if HAS_PSUTIL:
                        proc = psutil.Process(pid_to_kill)
                        proc.kill()
                    else:
                        os.kill(pid_to_kill, signal.SIGKILL)
                except (ProcessLookupError, psutil.NoSuchProcess):
                    pass
        
        return True
    except Exception:
        return False


def is_process_alive(pid: int) -> bool:
    """Check if a process is still alive."""
    try:
        if HAS_PSUTIL:
            return psutil.pid_exists(pid)
        else:
            if platform.system() == "Windows":
                # Windows: Use tasklist
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return str(pid) in result.stdout
            else:
                # Unix: Send signal 0 (doesn't kill, just checks)
                os.kill(pid, 0)
                return True
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        return False


def watch_launcher(launcher_pid: int, check_interval: float = 0.1):
    """
    Watch the launcher process and kill subprocesses when it dies.
    
    Args:
        launcher_pid: PID of the launcher process to monitor
        check_interval: How often to check if launcher is alive (seconds)
    """
    # Don't print to stderr - it can keep console windows open
    # print(f"[WATCHER] Monitoring launcher process {launcher_pid}", file=sys.stderr)
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        # Don't print to stderr - it can keep console windows open
        kill_all_service_processes()
        sys.exit(0)
    
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Monitor the launcher process
        while True:
            if not is_process_alive(launcher_pid):
                # Launcher has died - cleanup quickly and exit
                # Don't print to stderr - it can keep console windows open
                
                # Kill all processes on known ports (fast, parallel)
                kill_all_service_processes()
                
                # Also try to kill the launcher's process tree (in case it had children)
                try:
                    kill_process_tree(launcher_pid)
                except Exception:
                    pass
                
                # Exit immediately after cleanup
                sys.exit(0)
            
            time.sleep(check_interval)
    except KeyboardInterrupt:
        # Interrupted - cleanup and exit
        kill_all_service_processes()
        sys.exit(0)
    except Exception as e:
        # Error - cleanup and exit
        kill_all_service_processes()
        sys.exit(1)


def main():
    """Main entry point for the watcher process."""
    if len(sys.argv) < 2:
        # Don't print to stderr - it can keep console windows open
        sys.exit(1)
    
    try:
        launcher_pid = int(sys.argv[1])
    except ValueError:
        # Don't print to stderr - it can keep console windows open
        sys.exit(1)
    
    # Verify the PID exists
    if not is_process_alive(launcher_pid):
        # Launcher already dead - exit immediately
        sys.exit(0)
    
    # Start watching
    watch_launcher(launcher_pid)


if __name__ == "__main__":
    main()

