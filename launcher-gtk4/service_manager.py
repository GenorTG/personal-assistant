"""Service management for GTK4 launcher."""
import subprocess
import psutil
import signal
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from config import SERVICES

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages service processes."""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.logs: Dict[str, list] = {name: [] for name in SERVICES.keys()}
        # Clean up any hanging processes from previous runs
        self._cleanup_hanging_processes()
    
    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get status of a service."""
        if service_name not in SERVICES:
            return {"status": "unknown", "error": "Service not found"}
        
        config = SERVICES[service_name]
        process = self.processes.get(service_name)
        
        # Check if process is running
        if process and process.poll() is None:
            try:
                proc = psutil.Process(process.pid)
                return {
                    "status": "running",
                    "pid": process.pid,
                    "cpu_percent": proc.cpu_percent(interval=0.1),
                    "memory_mb": proc.memory_info().rss / (1024 * 1024),
                    "port": config["port"]
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process died
                if service_name in self.processes:
                    del self.processes[service_name]
                return {"status": "stopped"}
        else:
            # Check if port is in use (might be started externally)
            if self._check_port(config["port"]):
                return {
                    "status": "running",
                    "port": config["port"],
                    "note": "Process not managed by launcher"
                }
            return {"status": "stopped"}
    
    def start_service(self, service_name: str, dev_mode: bool = False) -> bool:
        """Start a service."""
        if service_name not in SERVICES:
            logger.error(f"Unknown service: {service_name}")
            return False
        
        if service_name in self.processes:
            proc = self.processes[service_name]
            if proc.poll() is None:
                logger.info(f"{service_name} is already running")
                return True
        
        config = SERVICES[service_name]
        
        # Fix NumPy version for gateway before starting (ChromaDB compatibility)
        if service_name == "gateway":
            venv = config.get("venv")
            if venv and venv.exists():
                python = venv / "bin" / "python"
                try:
                    # Check NumPy version
                    result = subprocess.run(
                        [str(python), "-c", "import numpy; print(numpy.__version__)"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        numpy_version = result.stdout.strip()
                        if numpy_version.startswith("2."):
                            logger.warning(f"NumPy {numpy_version} detected, fixing for ChromaDB compatibility...")
                            self.logs[service_name].append(f"⚠️  Fixing NumPy version (downgrading from {numpy_version} to <2.0.0)...")
                            fix_result = subprocess.run(
                                [str(python), "-m", "pip", "install", "numpy>=1.22.0,<2.0.0", "--force-reinstall"],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                            if fix_result.returncode == 0:
                                self.logs[service_name].append("✅ NumPy version fixed successfully")
                                logger.info("NumPy version fixed")
                            else:
                                self.logs[service_name].append(f"❌ Failed to fix NumPy: {fix_result.stderr}")
                                logger.error(f"Failed to fix NumPy: {fix_result.stderr}")
                except Exception as e:
                    logger.warning(f"Could not check/fix NumPy version: {e}")
        
        cmd_info = self._build_start_command(service_name, config, dev_mode=dev_mode)
        
        if not cmd_info:
            logger.error(f"Failed to build start command for {service_name}")
            return False
        
        # Handle both dict (with cwd/env) and list (simple command) formats
        if isinstance(cmd_info, dict):
            cmd = cmd_info["cmd"]
            cwd = cmd_info.get("cwd", str(config["directory"]))
            env_overrides = cmd_info.get("env", {})
            # Merge with existing environment to preserve PATH and other vars
            import os
            env = os.environ.copy()
            env.update(env_overrides)
        else:
            cmd = cmd_info
            cwd = str(config["directory"])
            env = None
        
        try:
            logger.info(f"Starting {service_name}: {cmd} (cwd: {cwd})")
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes[service_name] = process
            
            # Start log reader thread
            import threading
            thread = threading.Thread(
                target=self._read_logs,
                args=(service_name, process),
                daemon=True
            )
            thread.start()
            
            # Check if process exits immediately (syntax error, import error, etc.)
            # Give it a tiny moment to start, then check
            import time
            time.sleep(0.1)
            if process.poll() is not None:
                # Process exited immediately - startup failed
                return_code = process.returncode
                logger.error(f"{service_name} process exited immediately with code {return_code}")
                # Read any error output
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    if stdout:
                        error_output = stdout
                    elif stderr:
                        error_output = stderr
                    else:
                        error_output = "Process exited immediately"
                    # Add to logs
                    for line in error_output.split('\n'):
                        if line.strip():
                            self.logs[service_name].append(line.strip())
                except Exception:
                    pass
                # Remove from processes since it failed
                if service_name in self.processes:
                    del self.processes[service_name]
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to start {service_name}: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a service."""
        config = SERVICES.get(service_name)
        port = config.get("port") if config else None
        
        # If process is in our managed list, stop it
        if service_name in self.processes:
            process = self.processes[service_name]
            try:
                # For frontend, we need to kill the entire process tree (Node.js spawns children)
                if service_name == "frontend":
                    try:
                        proc = psutil.Process(process.pid)
                        # Kill all children first
                        for child in proc.children(recursive=True):
                            try:
                                child.terminate()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        # Wait a bit for children to terminate
                        time.sleep(0.5)
                        # Kill any remaining children
                        for child in proc.children(recursive=True):
                            try:
                                child.kill()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        # Now kill the main process
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        logger.warning(f"Could not kill frontend process tree: {e}")
                        # Fall back to regular termination
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                else:
                    # Regular termination for other services
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                
                del self.processes[service_name]
                logger.info(f"Stopped {service_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to stop {service_name}: {e}")
                # Remove from processes even if stop failed
                if service_name in self.processes:
                    del self.processes[service_name]
                return False
        
        # If process not in our list but port is in use, try to kill by port
        if port and self._check_port(port):
            logger.info(f"Process not in managed list but port {port} is in use, attempting to kill by port...")
            try:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        connections = proc.connections()
                        for conn in connections:
                            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port:
                                cmdline = ' '.join(proc.info['cmdline'] or [])
                                is_our_service = False
                                
                                if service_name == "gateway":
                                    is_our_service = "uvicorn" in cmdline and "src.main:app" in cmdline
                                elif service_name == "frontend":
                                    is_our_service = "next" in cmdline or "node" in cmdline.lower()
                                elif service_name == "chatterbox":
                                    is_our_service = "uvicorn" in cmdline and "main:app" in cmdline
                                
                                if is_our_service:
                                    logger.info(f"Killing {service_name} process (PID {proc.pid}) on port {port}...")
                                    # For frontend, kill entire process tree
                                    if service_name == "frontend":
                                        for child in proc.children(recursive=True):
                                            try:
                                                child.terminate()
                                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                pass
                                        time.sleep(0.5)
                                        for child in proc.children(recursive=True):
                                            try:
                                                child.kill()
                                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                pass
                                    proc.terminate()
                                    try:
                                        proc.wait(timeout=3)
                                    except psutil.TimeoutExpired:
                                        proc.kill()
                                        proc.wait()
                                    logger.info(f"Killed {service_name} process (PID {proc.pid})")
                                    return True
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Error killing process by port {port}: {e}")
        
        return True  # Consider it stopped if not found
    
    def restart_service(self, service_name: str, dev_mode: bool = False) -> bool:
        """Restart a service."""
        self.stop_service(service_name)
        time.sleep(1)
        return self.start_service(service_name, dev_mode=dev_mode)
    
    def _build_start_command(self, service_name: str, config: Dict[str, Any], dev_mode: bool = False) -> Optional[list]:
        """Build start command for a service."""
        if service_name == "gateway":
            venv = config["venv"]
            python = venv / "bin" / "python" if venv else "python3"
            # Disable uvicorn access logs to avoid spamming the launcher logs
            # (the frontend polls several endpoints frequently)
            return [
                str(python),
                "-m",
                "uvicorn",
                "src.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(config["port"]),
                "--no-access-log",
            ]
        
        elif service_name == "frontend":
            if dev_mode:
                # Start in development mode (live reload, no build required)
                logger.info("Starting frontend in development mode (npm run dev)")
                frontend_dir = config["directory"]
                node_modules_bin = frontend_dir / "node_modules" / ".bin"
                import os
                env = os.environ.copy()
                env["PORT"] = str(config["port"])
                # Add node_modules/.bin to PATH so npm can find next
                if node_modules_bin.exists():
                    current_path = env.get("PATH", "")
                    env["PATH"] = f"{node_modules_bin}:{current_path}"
                return {
                    "cmd": ["npm", "run", "dev"],
                    "cwd": str(config["directory"]),
                    "env": env
                }
            else:
                # Start in production mode (only if already built)
                frontend_dir = config["directory"]
                build_dir = frontend_dir / ".next"
                
                # Check if build exists - if not, warn user to reinstall
                if not build_dir.exists():
                    logger.warning("Frontend not built. Please reinstall the frontend service to build it.")
                    self.logs[service_name].append("⚠️ Frontend not built. Please click 'Reinstall' to build it first.")
                    return None
                
                # Start in production mode
                # Check if standalone output is configured
                standalone_server = frontend_dir / ".next" / "standalone" / "server.js"
                if standalone_server.exists():
                    # For standalone mode, we need to ensure static files are accessible
                    # Next.js standalone copies static files to .next/standalone/.next/static
                    # But we also need to ensure the parent .next/static is accessible
                    # Actually, let's just use npm start which handles this correctly
                    # Standalone mode is complex and requires proper static file setup
                    logger.info("Standalone build detected, but using npm start for proper static file serving")
                    return ["npm", "run", "start"]
                else:
                    # Fallback to npm start (requires .next to exist)
                    return ["npm", "run", "start"]
        
        elif service_name == "chatterbox":
            venv = config["venv"]
            # Always use python3.11 for chatterbox, even if venv exists (venv should be created with 3.11)
            if venv and venv.exists():
                python = venv / "bin" / "python"
            else:
                python = Path("python3.11")  # Explicitly use python3.11
            return [str(python), "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(config["port"])]
        
        return None
    
    def _check_port(self, port: int) -> bool:
        """Check if a port is in use."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            return False
    
    def _read_logs(self, service_name: str, process: subprocess.Popen):
        """Read logs from a process."""
        if not process.stdout:
            return
        
        try:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                self.logs[service_name].append(line.rstrip())
                # Keep only last 1000 lines
                if len(self.logs[service_name]) > 1000:
                    self.logs[service_name] = self.logs[service_name][-1000:]
        except Exception as e:
            logger.error(f"Error reading logs for {service_name}: {e}")
    
    def get_logs(self, service_name: str, lines: int = 100) -> list:
        """Get recent logs for a service."""
        logs = self.logs.get(service_name, [])
        return logs[-lines:] if logs else []
    
    def stop_all_services(self):
        """Stop all running services."""
        logger.info("Stopping all services...")
        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)
        logger.info("All services stopped")
    
    def _cleanup_hanging_processes(self):
        """Detect and kill any hanging processes from previous launcher runs."""
        logger.info("Checking for hanging processes...")
        killed_count = 0
        
        for service_name, config in SERVICES.items():
            port = config.get("port")
            if not port:
                continue
            
            # Check if port is in use
            if self._check_port(port):
                # Find process using this port
                try:
                    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                        try:
                            # Check if this process is listening on our port
                            connections = proc.connections()
                            for conn in connections:
                                if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port:
                                    # Check if it's one of our services
                                    cmdline = ' '.join(proc.info['cmdline'] or [])
                                    is_our_service = False
                                    
                                    if service_name == "gateway":
                                        is_our_service = "uvicorn" in cmdline and "src.main:app" in cmdline
                                    elif service_name == "frontend":
                                        is_our_service = "next" in cmdline or ("node" in cmdline.lower() and str(port) in cmdline)
                                    elif service_name == "chatterbox":
                                        is_our_service = "uvicorn" in cmdline and "main:app" in cmdline
                                    
                                    if is_our_service:
                                        logger.warning(f"Found hanging {service_name} process (PID {proc.pid}) on port {port}, killing...")
                                        self.logs[service_name].append(f"🧹 Cleaning up hanging process (PID {proc.pid})...")
                                        try:
                                            # For frontend, kill entire process tree
                                            if service_name == "frontend":
                                                for child in proc.children(recursive=True):
                                                    try:
                                                        child.terminate()
                                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                        pass
                                                time.sleep(0.5)
                                                for child in proc.children(recursive=True):
                                                    try:
                                                        child.kill()
                                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                                        pass
                                            # Try graceful termination first
                                            proc.terminate()
                                            try:
                                                proc.wait(timeout=3)
                                            except psutil.TimeoutExpired:
                                                # Force kill
                                                proc.kill()
                                                proc.wait()
                                            killed_count += 1
                                            logger.info(f"Killed hanging {service_name} process (PID {proc.pid})")
                                            self.logs[service_name].append(f"✅ Killed hanging process (PID {proc.pid})")
                                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                                            logger.warning(f"Could not kill process {proc.pid}: {e}")
                                            self.logs[service_name].append(f"⚠️  Could not kill process {proc.pid}: {e}")
                                    break  # Found the process for this port, move to next service
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            continue
                        except Exception as e:
                            # Skip processes we can't inspect
                            continue
                except Exception as e:
                    logger.warning(f"Error checking for hanging processes on port {port}: {e}")
        
        if killed_count > 0:
            logger.info(f"Cleaned up {killed_count} hanging process(es)")
        else:
            logger.info("No hanging processes found")

