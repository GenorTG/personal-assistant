"""Process group management for ensuring child processes terminate with parent."""

import platform
import atexit
import subprocess
from typing import Optional

# Windows-specific imports for job objects
if platform.system() == "Windows":
    try:
        import ctypes
        from ctypes import wintypes
        WINDOWS_JOB_AVAILABLE = True
    except ImportError:
        WINDOWS_JOB_AVAILABLE = False
else:
    WINDOWS_JOB_AVAILABLE = False


class ProcessGroupManager:
    """Manages process groups/job objects to ensure child processes die with parent."""
    
    def __init__(self):
        self.job_handle = None
        self._create_process_group()
        atexit.register(self._cleanup_process_group)
    
    def _create_process_group(self):
        """Create a Windows Job Object or ensure Unix process group."""
        if platform.system() == "Windows" and WINDOWS_JOB_AVAILABLE:
            try:
                # Create a job object
                kernel32 = ctypes.windll.kernel32
                
                # Create job object
                self.job_handle = kernel32.CreateJobObjectW(None, None)
                if not self.job_handle:
                    return
                
                # Configure job object to kill all processes when job handle is closed
                info = wintypes.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                
                result = kernel32.SetInformationJobObject(
                    self.job_handle,
                    9,  # JobObjectExtendedLimitInformation
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )
                if not result:
                    kernel32.CloseHandle(self.job_handle)
                    self.job_handle = None
            except Exception:
                self.job_handle = None
    
    def _cleanup_process_group(self):
        """Clean up process group/job object."""
        if platform.system() == "Windows" and self.job_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception:
                pass
            self.job_handle = None
    
    def assign_to_process_group(self, process: subprocess.Popen) -> bool:
        """Assign a process to the job object (Windows) or ensure it's in process group (Unix)."""
        if platform.system() == "Windows" and self.job_handle:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                result = kernel32.AssignProcessToJobObject(self.job_handle, process._handle)
                return bool(result)
            except Exception:
                return False
        # On Unix, processes are already in their own process group if start_new_session=True
        return True


