import psutil
import logging
from typing import Dict, List, Optional, Any
import pynvml

logger = logging.getLogger(__name__)

class SystemMonitor:
    """Monitors system resources (RAM, VRAM) for specific services."""
    
    def __init__(self):
        self.services = {
            "gateway": {"port": 8000, "name": "Gateway Service"},
            "llm": {"port": 8001, "name": "LLM Service"},
            "whisper": {"port": 8003, "name": "Whisper Service"},
            "piper": {"port": 8004, "name": "Piper Service"},
            "chatterbox": {"port": 4123, "name": "Chatterbox Service"},
            "kokoro": {"port": 8880, "name": "Kokoro Service"}
        }
        self._nvml_initialized = False
        self._init_nvml()

    def _init_nvml(self):
        """Initialize NVML for VRAM monitoring."""
        try:
            pynvml.nvmlInit()
            self._nvml_initialized = True
            logger.info("NVML initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize NVML: {e}")
            self._nvml_initialized = False

    def get_service_pids(self) -> Dict[str, int]:
        """Find PIDs for services based on their listening ports."""
        pids = {}
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == 'LISTEN' and conn.laddr.port:
                    port = conn.laddr.port
                    # Check if this port belongs to one of our services
                    for service_id, info in self.services.items():
                        if info["port"] == port:
                            pids[service_id] = conn.pid
        except Exception as e:
            logger.error(f"Error finding service PIDs: {e}")
        return pids

    def get_process_vram(self, pid: int) -> float:
        """Get VRAM usage for a specific PID in GB."""
        if not self._nvml_initialized:
            return 0.0
        
        total_vram = 0.0
        try:
            device_count = pynvml.nvmlDeviceGetCount()
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                try:
                    # Get all processes running on this GPU
                    procs = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
                    # Also check graphics processes just in case
                    graphics_procs = pynvml.nvmlDeviceGetGraphicsRunningProcesses(handle)
                    
                    all_procs = procs + graphics_procs
                    
                    for p in all_procs:
                        if p.pid == pid:
                            # memoryUsed is in bytes
                            total_vram += p.usedGpuMemory / (1024**3)
                except pynvml.NVMLError as e:
                    continue
        except Exception as e:
            logger.debug(f"Error getting VRAM for PID {pid}: {e}")
            
        return total_vram

    def get_status(self) -> Dict[str, Any]:
        """Get current status of all services."""
        service_pids = self.get_service_pids()
        status = []
        
        total_system_ram = psutil.virtual_memory().total / (1024**3)
        
        # Get total VRAM if available
        total_system_vram = 0
        if self._nvml_initialized:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_system_vram = info.total / (1024**3)
            except:
                pass

        for service_id, info in self.services.items():
            pid = service_pids.get(service_id)
            service_data = {
                "id": service_id,
                "name": info["name"],
                "port": info["port"],
                "status": "stopped",
                "pid": None,
                "ram_gb": 0.0,
                "vram_gb": 0.0,
                "cpu_percent": 0.0
            }
            
            if pid:
                try:
                    proc = psutil.Process(pid)
                    # RSS is resident set size (memory actually used)
                    ram_gb = proc.memory_info().rss / (1024**3)
                    vram_gb = self.get_process_vram(pid)
                    cpu_percent = proc.cpu_percent(interval=None)
                    
                    service_data.update({
                        "status": "running",
                        "pid": pid,
                        "ram_gb": round(ram_gb, 2),
                        "vram_gb": round(vram_gb, 2),
                        "cpu_percent": round(cpu_percent, 1)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            status.append(service_data)
            
        return {
            "services": status,
            "system": {
                "total_ram_gb": round(total_system_ram, 2),
                "total_vram_gb": round(total_system_vram, 2),
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "cpu_percent": psutil.cpu_percent()
            }
        }

# Global instance
system_monitor = SystemMonitor()
