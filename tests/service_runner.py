"""
Service Runner for Tests

Manages starting/stopping services as background processes for testing.
Services run in isolated subprocesses so they don't block the test runner.
"""
import asyncio
import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field
import platform

from .config import SERVICES, ServiceConfig


@dataclass
class ManagedService:
    """A service managed by the test runner."""
    config: ServiceConfig
    process: Optional[subprocess.Popen] = None
    started_by_tests: bool = False
    
    @property
    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None


class ServiceRunner:
    """
    Manages service lifecycle for testing.
    
    - Starts services as background processes
    - Waits for services to be ready
    - Cleans up services after tests
    """
    
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).parent.parent.resolve()
        self.services_dir = self.root_dir / "services"
        self.managed_services: Dict[str, ManagedService] = {}
        self._cleanup_registered = False
        
    def _get_venv_python(self, service_name: str) -> Optional[Path]:
        """Get the Python executable for a service's venv."""
        service_dir = self._get_service_dir(service_name)
        if not service_dir:
            return None
            
        venv_dir = service_dir / ".venv"
        if platform.system() == "Windows":
            python = venv_dir / "Scripts" / "python.exe"
        else:
            python = venv_dir / "bin" / "python"
            
        if python.exists():
            return python
        return None
    
    def _get_service_dir(self, service_name: str) -> Optional[Path]:
        """Get the directory for a service."""
        # Map service names to directories
        service_dirs = {
            "memory": self.services_dir / "memory",
            "tools": self.services_dir / "tools",
            "gateway": self.services_dir / "gateway",
            "llm": self.services_dir / "llm",
            "whisper": self.services_dir / "stt-whisper",
            "piper": self.services_dir / "tts-piper",
            "kokoro": self.services_dir / "tts-kokoro",
        }
        return service_dirs.get(service_name)
    
    def _get_start_command(self, service_name: str) -> Optional[List[str]]:
        """Get the command to start a service."""
        python = self._get_venv_python(service_name)
        if not python:
            return None
            
        config = SERVICES.get(service_name)
        if not config:
            return None
        
        # Map service to uvicorn app module
        app_modules = {
            "memory": "main:app",
            "tools": "main:app",
            "gateway": "main:app",
            "llm": "main:app",
            "whisper": "main:app",
            "piper": "main:app",
            "kokoro": "main:app",
        }
        
        app_module = app_modules.get(service_name)
        if not app_module:
            return None
            
        return [
            str(python), "-m", "uvicorn", app_module,
            "--host", "0.0.0.0",
            "--port", str(config.port)
        ]
    
    async def check_service_ready(self, service_name: str, timeout: float = 30) -> bool:
        """Check if a service is ready by polling its health endpoint."""
        import aiohttp
        
        config = SERVICES.get(service_name)
        if not config:
            return False
            
        url = f"{config.base_url}{config.health_endpoint}"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                        if response.status == 200:
                            return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        
        return False
    
    async def is_service_running(self, service_name: str) -> bool:
        """Quick check if service is already running."""
        import aiohttp
        
        config = SERVICES.get(service_name)
        if not config:
            return False
            
        url = f"{config.base_url}{config.health_endpoint}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    return response.status == 200
        except Exception:
            return False
    
    async def start_service(
        self, 
        service_name: str, 
        wait_ready: bool = True,
        timeout: float = 60
    ) -> bool:
        """
        Start a service as a background process.
        
        Returns True if service is running (either started or already was running).
        """
        # Check if already running
        if await self.is_service_running(service_name):
            print(f"  ℹ️  {service_name} is already running")
            return True
        
        # Get start command
        cmd = self._get_start_command(service_name)
        if not cmd:
            print(f"  ❌ Cannot start {service_name}: no start command")
            return False
        
        service_dir = self._get_service_dir(service_name)
        if not service_dir or not service_dir.exists():
            print(f"  ❌ Cannot start {service_name}: directory not found")
            return False
        
        print(f"  🚀 Starting {service_name}...")
        
        try:
            # Start process in background with output suppressed
            if platform.system() == "Windows":
                # Windows: CREATE_NEW_PROCESS_GROUP for clean termination
                # + CREATE_NO_WINDOW to prevent CMD popup
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                process = subprocess.Popen(
                    cmd,
                    cwd=str(service_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags
                )
            else:
                # Unix: start_new_session for process group management
                process = subprocess.Popen(
                    cmd,
                    cwd=str(service_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            
            config = SERVICES.get(service_name)
            self.managed_services[service_name] = ManagedService(
                config=config,
                process=process,
                started_by_tests=True
            )
            
            # Register cleanup on first service start
            if not self._cleanup_registered:
                import atexit
                atexit.register(self.cleanup_sync)
                self._cleanup_registered = True
            
            if wait_ready:
                print(f"  ⏳ Waiting for {service_name} to be ready...")
                ready = await self.check_service_ready(service_name, timeout=timeout)
                if ready:
                    print(f"  ✅ {service_name} is ready")
                    return True
                else:
                    print(f"  ❌ {service_name} failed to become ready")
                    self.stop_service(service_name)
                    return False
            
            return True
            
        except Exception as e:
            print(f"  ❌ Failed to start {service_name}: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a service that was started by tests."""
        managed = self.managed_services.get(service_name)
        if not managed or not managed.process:
            return True
        
        if not managed.started_by_tests:
            print(f"  ℹ️  {service_name} was not started by tests, not stopping")
            return True
        
        print(f"  🛑 Stopping {service_name}...")
        
        try:
            if platform.system() == "Windows":
                # Windows: terminate process
                managed.process.terminate()
                try:
                    managed.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    managed.process.kill()
            else:
                # Unix: send SIGTERM to process group
                os.killpg(os.getpgid(managed.process.pid), signal.SIGTERM)
                try:
                    managed.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(managed.process.pid), signal.SIGKILL)
            
            print(f"  ✅ {service_name} stopped")
            del self.managed_services[service_name]
            return True
            
        except Exception as e:
            print(f"  ⚠️ Error stopping {service_name}: {e}")
            return False
    
    def stop_all(self) -> None:
        """Stop all services started by tests."""
        print("\n--- Cleaning up test services ---")
        for service_name in list(self.managed_services.keys()):
            self.stop_service(service_name)
    
    def cleanup_sync(self) -> None:
        """Synchronous cleanup for atexit handler."""
        for service_name, managed in list(self.managed_services.items()):
            if managed.process and managed.started_by_tests:
                try:
                    if platform.system() == "Windows":
                        managed.process.terminate()
                    else:
                        os.killpg(os.getpgid(managed.process.pid), signal.SIGTERM)
                except Exception:
                    pass


# Global instance
service_runner = ServiceRunner()

