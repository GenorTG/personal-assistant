import customtkinter as ctk
import sys
import os
import threading
import time
import subprocess
import platform
import webbrowser
import re
import json
from pathlib import Path
from typing import Optional, Dict
import logging
import multiprocessing
import urllib.request
import urllib.error
import urllib.parse
import socket
import atexit

# Configure Windows console for UTF-8/emoji support
if platform.system() == "Windows":
    try:
        # Set console code page to UTF-8 (65001) to support emojis
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Get current console handle
        if hasattr(sys.stdout, 'fileno'):
            stdout_handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            if stdout_handle:
                # Set console output code page to UTF-8
                kernel32.SetConsoleOutputCP(65001)
        # Also set the input code page
        kernel32.SetConsoleCP(65001)
        # Set environment variable for subprocesses
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    except Exception:
        # If setting console code page fails, just set the env var
        os.environ['PYTHONIOENCODING'] = 'utf-8'

# Add current directory to path to import manager and modules
launcher_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(launcher_dir))

# Import new modular components
try:
    from ui.console import ConsoleRedirector
    from ui.logging import UILogger
    from ui.tts_test import TTSTestPanel
    from process.process_group import ProcessGroupManager
    from process.process_utils import kill_process_tree, kill_process_on_port, cleanup_all_service_ports, find_all_processes_on_ports
    from install.chatterbox_cuda import ChatterboxCudaInstaller
    # Note: watcher.py is run as a separate process, not imported as a module
except (ImportError, ModuleNotFoundError) as e:
    import traceback
    error_msg = f"Failed to import launcher modules: {e}\n\nTraceback:\n{traceback.format_exc()}\n\nLauncher directory: {launcher_dir}\nPython path (first 5): {sys.path[:5]}"
    # Write error to log file (pythonw doesn't show console)
    try:
        error_log = launcher_dir / "launcher_import_error.log"
        with open(error_log, "w", encoding="utf-8") as f:
            f.write(error_msg)
        print(f"Error written to: {error_log}", file=sys.stderr)
    except Exception as log_error:
        print(f"Failed to write error log: {log_error}", file=sys.stderr)
    # Don't show messagebox - it spawns notepad on Windows
    # Error is already written to log file
    sys.exit(1)

try:
    from manager import ServiceManager, ServiceStatus
except ImportError:
    class ServiceManager:
        def __init__(self, root_dir=None):
            self.root_dir = root_dir or Path.cwd()
            self.services = {
                "backend": {"name": "Backend API", "port": 8000, "url": "http://localhost:8000"},
                "frontend": {"name": "Frontend", "port": 8002, "url": "http://localhost:8002"},
                "kokoro": {"name": "Kokoro TTS", "port": 8880, "url": "http://localhost:8880"}
            }
            self.service_status = {k: "stopped" for k in self.services}
        
        def check_dependencies(self):
            return {"venv": True, "backend_deps": True}
            
        def install_dependencies(self, **kwargs):
            time.sleep(2)
            return True

# Configure logging with safe stream handling for GUI applications
# In GUI apps (especially with pythonw.exe), stdout/stderr may be None
# Don't use basicConfig with a potentially None stream - configure manually

# Get logger and configure it to handle None streams gracefully
logger = logging.getLogger("Launcher")

# Add a custom handler that safely handles None streams
class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that safely handles None streams."""
    def emit(self, record):
        try:
            if self.stream is None:
                # If stream is None, don't try to write
                return
            # Check if stream has write method
            if not hasattr(self.stream, 'write'):
                return
            msg = self.format(record)
            stream = self.stream
            # Check if stream is still valid
            if stream is None:
                return
            stream.write(msg + self.terminator)
            self.flush()
        except (AttributeError, ValueError, OSError):
            # Silently ignore errors when stream is None or closed
            self.handleError(record)

# Replace default handlers with safe handler
for handler in list(logger.handlers):
    logger.removeHandler(handler)

# Add safe handler only if stdout/stderr are available
if sys.stdout and hasattr(sys.stdout, 'write'):
    safe_handler = SafeStreamHandler(sys.stdout)
    safe_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(safe_handler)
elif sys.stderr and hasattr(sys.stderr, 'write'):
    safe_handler = SafeStreamHandler(sys.stderr)
    safe_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(safe_handler)
else:
    # Fallback to NullHandler if no streams are available
    logger.addHandler(logging.NullHandler())

# Prevent propagation to root logger to avoid duplicate logs
logger.propagate = False

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ============================================
        # DESIGN SYSTEM - CLEAN AND SIMPLE
        # ============================================
        self.colors = {
            "bg_main": "#1E1E1E",
            "bg_panel": "#2D2D2D",
            "bg_card": "#3A3A3A",
            "text_primary": "#FFFFFF",
            "text_secondary": "#CCCCCC",
            "accent_blue": "#0078D4",
            "accent_green": "#107C10",
            "accent_red": "#D13438",
            "accent_orange": "#FF8C00",
            "border": "#404040",
        }
        
        # ============================================
        # WINDOW SETUP - SCREEN-AWARE SIZING
        # ============================================
        self.version = "2.0.0"  # Major.Minor.Patch
        self.title(f"Personal Assistant Manager v{self.version}")
        
        # Get screen resolution and calculate appropriate window size
        # Use 70% of screen size, but never exceed 1400x900 (reasonable max)
        # Also ensure minimum usable size
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Calculate window size (70% of screen, capped at reasonable max)
        target_width = min(int(screen_width * 0.7), 1400)
        target_height = min(int(screen_height * 0.7), 900)
        
        # Ensure minimum usable size
        target_width = max(target_width, 800)
        target_height = max(target_height, 600)
        
        # Center window on screen
        x = (screen_width - target_width) // 2
        y = (screen_height - target_height) // 2
        
        self.geometry(f"{target_width}x{target_height}+{x}+{y}")
        
        # Remove minimum size constraints - allow user to resize freely
        self.minsize(400, 300)  # Very small minimum to allow maximum flexibility
        
        # Make window resizable
        self.resizable(True, True)
        
        # Track splitter position for services/console split (50% each by default)
        self._services_height_ratio = 0.5  # 50% for services, 50% for console
        
        ctk.set_appearance_mode("Dark")
        self.configure(fg_color=self.colors["bg_main"])
        
        # Initialize ServiceManager (lightweight, just sets up data structures)
        # Heavy operations like loading external service metadata are deferred
        self.service_manager = ServiceManager()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.service_start_times: Dict[str, float] = {}  # Track when services were started
        self.service_status_confirmed: Dict[str, bool] = {}  # Track if "Running" status was confirmed
        self.services_ui = {}
        self.service_vars = {}
        
        # Load Chatterbox settings from config file
        self.config_file = launcher_dir / "launcher_config.json"
        self.chatterbox_settings = self._load_chatterbox_settings()
        
        # Cache for service installation status to avoid repeated file I/O
        self._install_status_cache: Dict[str, bool] = {}
        self._install_status_cache_time: Dict[str, float] = {}
        self._cache_ttl = 5.0  # Cache TTL in seconds
        
        # Initialize UI logger (handles batched logging to UI)
        self.ui_logger = UILogger(self)
        
        # Performance optimization: pause status updates during heavy operations
        self._heavy_operation_active = False
        self._status_update_queue = set()  # Queue of services that need status updates
        self._status_update_pending = False
        
        # Initialize process group manager (handles Windows Job Objects/Unix process groups)
        # This ensures all child processes die when the launcher exits
        # DEFER: Initialize in background to avoid blocking UI
        self.process_group_manager = None
        
        # Initialize Chatterbox CUDA installer
        # DEFER: Initialize in background to avoid blocking UI
        self.chatterbox_cuda_installer = None
        
        # Start watcher process to monitor launcher and kill subprocesses if launcher dies
        # DEFER: Start in background to avoid blocking UI
        self._watcher_process: Optional[subprocess.Popen] = None
        
        # Flag to ensure cleanup only runs once
        self._cleanup_done = False
        
        # ============================================
        # MAIN LAYOUT - RESIZABLE WITH SPLITTER
        # ============================================
        self.grid_columnconfigure(0, weight=1)
        # Row 0: Header (fixed height)
        # Row 1: Services (resizable)
        # Row 2: Splitter (draggable)
        # Row 3: Console (resizable)
        # Set initial weights for 50/50 split
        self.grid_rowconfigure(1, weight=1, minsize=100)  # Services row - minimum 100px
        self.grid_rowconfigure(2, weight=0, minsize=5)     # Splitter row - 5px (fixed)
        self.grid_rowconfigure(3, weight=1, minsize=100)  # Console row - minimum 100px
        
        # ============================================
        # ROW 0: HEADER WITH BUTTONS - COMPACT
        # ============================================
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], height=55, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        
        # Title - smaller font
        title = ctk.CTkLabel(
            header,
            text=f"Personal Assistant Manager v{self.version}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title.grid(row=0, column=0, padx=15, pady=12, sticky="w")
        
        # Buttons - smaller and more compact
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=15, pady=10, sticky="e")
        
        # Smaller buttons: width 85, height 28, smaller padding
        self.install_all_btn = ctk.CTkButton(btn_frame, text="Install All", command=self.install_all_services, width=85, height=28, font=ctk.CTkFont(size=11))
        self.install_all_btn.grid(row=0, column=0, padx=3)
        
        self.start_all_btn = ctk.CTkButton(btn_frame, text="Start All", command=self.start_all_services, width=85, height=28, font=ctk.CTkFont(size=11), fg_color=self.colors["accent_green"], hover_color="#0E6B0E")
        self.start_all_btn.grid(row=0, column=1, padx=3)
        
        self.stop_all_btn = ctk.CTkButton(btn_frame, text="Stop All", command=self.stop_all_services, width=85, height=28, font=ctk.CTkFont(size=11), fg_color=self.colors["accent_red"], hover_color="#B02A2E")
        self.stop_all_btn.grid(row=0, column=2, padx=3)
        
        self.open_web_btn = ctk.CTkButton(btn_frame, text="Open Web UI", command=self.open_web_ui, width=85, height=28, font=ctk.CTkFont(size=11), fg_color=self.colors["accent_blue"], hover_color="#0063B1")
        self.open_web_btn.grid(row=0, column=3, padx=3)
        
        self.reset_app_btn = ctk.CTkButton(btn_frame, text="Reset State", command=self.reset_app_state, width=85, height=28, font=ctk.CTkFont(size=11), fg_color=self.colors["accent_orange"], hover_color="#E67E00")
        self.reset_app_btn.grid(row=0, column=4, padx=3)
        
        # ============================================
        # ROW 1: SERVICES LIST - RESIZABLE
        # ============================================
        self.services_panel = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], corner_radius=0)
        self.services_panel.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 0))
        self.services_panel.grid_columnconfigure(0, weight=1)
        self.services_panel.grid_rowconfigure(1, weight=1)
        
        # Services title - smaller
        services_title = ctk.CTkLabel(
            self.services_panel,
            text="Services",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        services_title.grid(row=0, column=0, padx=12, pady=8, sticky="w")
        
        # Scrollable frame for services
        self.services_frame = ctk.CTkScrollableFrame(
            self.services_panel,
            fg_color=self.colors["bg_panel"],
            corner_radius=0
        )
        self.services_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Configure columns in scrollable frame - RESIZABLE WITH WEIGHTS - more compact
        self.services_frame.grid_columnconfigure(0, minsize=40, weight=0)   # Checkbox
        self.services_frame.grid_columnconfigure(1, minsize=200, weight=2) # Service name (RESIZABLE)
        self.services_frame.grid_columnconfigure(2, minsize=120, weight=1) # Install status (RESIZABLE)
        self.services_frame.grid_columnconfigure(3, minsize=120, weight=1) # Running status (RESIZABLE)
        self.services_frame.grid_columnconfigure(4, minsize=350, weight=3) # Actions (RESIZABLE)
        
        # Create service rows
        # Track actual row position to account for expandable settings frames
        services = list(self.service_manager.services.keys())
        actual_row = 0
        for svc in services:
            self._create_service_row(svc, actual_row)
            actual_row += 1
            # If this service has a settings frame, account for it in the next row
            if svc == "chatterbox":
                actual_row += 1  # Settings frame will be at actual_row
        
        # ============================================
        # ROW 2: DRAGGABLE SPLITTER
        # ============================================
        self.splitter = ctk.CTkFrame(self, fg_color=self.colors["border"], height=5, corner_radius=0)
        self.splitter.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self.splitter.grid_propagate(False)
        
        # Make splitter draggable
        self._splitter_dragging = False
        self.splitter.bind("<Button-1>", self._on_splitter_press)
        self.splitter.bind("<B1-Motion>", self._on_splitter_drag)
        self.splitter.bind("<ButtonRelease-1>", self._on_splitter_release)
        # Change cursor on hover
        self.splitter.bind("<Enter>", lambda e: self.splitter.configure(cursor="sb_v_double_arrow"))
        self.splitter.bind("<Leave>", lambda e: self.splitter.configure(cursor=""))
        
        # ============================================
        # ROW 3: CONSOLE - CLEAN TABBED INTERFACE
        # ============================================
        self.console_panel = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], corner_radius=0)
        self.console_panel.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 5))
        self.console_panel.grid_columnconfigure(0, weight=1)
        self.console_panel.grid_rowconfigure(1, weight=1)
        
        # Console title - smaller
        console_title = ctk.CTkLabel(
            self.console_panel,
            text="Console Output",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        console_title.grid(row=0, column=0, padx=12, pady=8, sticky="w")
        
        # Tabs
        self.log_tabview = ctk.CTkTabview(self.console_panel, fg_color=self.colors["bg_card"], corner_radius=5)
        self.log_tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        self.log_tabs = {}
        
        # Launcher tab
        self.log_tabs["launcher"] = self.log_tabview.add("Launcher")
        launcher_log = ctk.CTkTextbox(
            self.log_tabs["launcher"],
            state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.colors["bg_main"],
            text_color=self.colors["text_primary"],
            corner_radius=5
        )
        launcher_log.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_tabs["launcher_textbox"] = launcher_log
        
        # All tab
        self.log_tabs["all"] = self.log_tabview.add("All")
        all_log = ctk.CTkTextbox(
            self.log_tabs["all"],
            state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.colors["bg_main"],
            text_color=self.colors["text_primary"],
            corner_radius=5
        )
        all_log.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_tabs["all_textbox"] = all_log
        
        # Service tabs (exclude "llm" since we'll create a special LLM tab)
        for svc_name in services:
            if svc_name.lower() == "llm":
                continue  # Skip llm, we'll create a special tab for it
            tab_name = svc_name.upper()
            # Check if tab already exists (shouldn't happen, but be safe)
            try:
                tab = self.log_tabview.add(tab_name)
            except ValueError:
                # Tab already exists, skip it
                continue
            textbox = ctk.CTkTextbox(
                tab,
                state="disabled",
                font=ctk.CTkFont(family="Consolas", size=11),
                fg_color=self.colors["bg_main"],
                text_color=self.colors["text_primary"],
                corner_radius=5
            )
            textbox.pack(fill="both", expand=True, padx=5, pady=5)
            self.log_tabs[svc_name] = textbox
        
        # LLM tab (separate from gateway, even though LLM is managed by gateway)
        # Check if it already exists before creating
        try:
            llm_tab = self.log_tabview.add("LLM")
            llm_textbox = ctk.CTkTextbox(
                llm_tab,
                state="disabled",
                font=ctk.CTkFont(family="Consolas", size=11),
                fg_color=self.colors["bg_main"],
                text_color=self.colors["text_primary"],
                corner_radius=5
            )
            llm_textbox.pack(fill="both", expand=True, padx=5, pady=5)
            self.log_tabs["llm"] = llm_textbox
        except ValueError:
            # LLM tab already exists (shouldn't happen, but handle gracefully)
            # Try to get existing tab from tabview's internal dict
            try:
                llm_tab = self.log_tabview._tab_dict.get("LLM")
                if llm_tab:
                    # Find existing textbox in the tab (should be the only child)
                    for child in llm_tab.winfo_children():
                        if isinstance(child, ctk.CTkTextbox):
                            self.log_tabs["llm"] = child
                            break
            except Exception:
                # If we can't get the existing tab, create a dummy entry
                # This shouldn't happen, but prevents crashes
                pass
        
        # TTS Test tab
        tts_test_tab = self.log_tabview.add("TTS Test")
        self.tts_test_panel = TTSTestPanel(
            tts_test_tab,
            self.colors,
            self.log_to_launcher
        )
        self.tts_test_panel.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Redirect output
        sys.stdout = ConsoleRedirector(all_log)
        sys.stderr = ConsoleRedirector(all_log)
        
        # Initial messages
        self.log_to_launcher(f"Welcome to Personal Assistant Manager v{self.version}")
        self.log_to_launcher("Ready to manage services...")
        print(f"Welcome to Personal Assistant Manager v{self.version}")
        print("Ready to manage services...")
        
        # CRITICAL: Show window FIRST, then do heavy work in background
        # This prevents UI freezing during startup
        # Force immediate render of the window
        self.update_idletasks()  # Process all pending idle tasks
        self.update()  # Force initial render
        
        # Defer ALL heavy operations to background threads AFTER window is shown
        # This ensures UI appears immediately and is responsive
        def _deferred_init():
            """Initialize heavy components in background after UI is shown."""
            try:
                # Initialize process group manager
                self.process_group_manager = ProcessGroupManager()
                
                # Initialize Chatterbox CUDA installer
                self.chatterbox_cuda_installer = ChatterboxCudaInstaller(self, self.service_manager)
                
                # Start watcher process
                self._start_watcher()
                
                # Clean up orphaned processes (can be slow, do in background)
                if not self._cleanup_done:
                    self._cleanup_done = True
                    self._cleanup_orphaned_processes()
                
                # Now refresh statuses after everything is initialized
                # Delay status refresh to ensure UI is fully rendered
                self.after(500, self.refresh_all_service_statuses)
                self.after(1000, self._start_periodic_status_refresh)
            except Exception as e:
                logger.error(f"Error in deferred initialization: {e}")
                # Still show UI even if background init fails
                self.after(100, self.refresh_all_service_statuses)
        
        # Run deferred init in background thread (non-blocking)
        threading.Thread(target=_deferred_init, daemon=True).start()
    
    def _create_service_row(self, svc: str, row_index: int):
        """Create a service row with all elements visible and properly sized."""
        svc_info = self.service_manager.services.get(svc)
        is_gateway_managed = (svc == "llm")
        # Defer installation check - show "Checking..." initially, update in background
        # This speeds up startup by avoiding synchronous file I/O during UI creation
        is_installed = False  # Will be updated by refresh_all_service_statuses
        is_running = svc in self.processes and self.processes[svc].poll() is None
        
        # Row frame - let it size naturally
        row = ctk.CTkFrame(
            self.services_frame,
            fg_color=self.colors["bg_card"],
            corner_radius=5
        )
        row.grid(row=row_index, column=0, sticky="ew", padx=5, pady=5)
        
        # Configure columns - RESIZABLE to match scrollable frame - more compact
        row.grid_columnconfigure(0, minsize=40, weight=0)
        row.grid_columnconfigure(1, minsize=200, weight=2)
        row.grid_columnconfigure(2, minsize=120, weight=1)
        row.grid_columnconfigure(3, minsize=120, weight=1)
        row.grid_columnconfigure(4, minsize=350, weight=3)
        
        # Checkbox - Column 0 - smaller
        var = ctk.BooleanVar(value=True)
        self.service_vars[svc] = var
        checkbox = ctk.CTkCheckBox(row, text="", variable=var)
        checkbox.grid(row=0, column=0, padx=8, pady=10, sticky="w")
        
        # Service name - Column 1 - smaller font
        service_name_text = svc_info.get("name", svc.upper())
        name_label = ctk.CTkLabel(
            row,
            text=service_name_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["text_primary"],
            anchor="w",
            width=300  # Full column width
        )
        name_label.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        
        # Install status - Column 2
        # LLM still needs to be installed (uses shared venv), just managed by Gateway for starting
        if is_installed:
            install_text = "✓ Installed"
            install_color = self.colors["accent_green"]
        else:
            install_text = "✗ Not Installed"
            install_color = self.colors["accent_orange"]
        
        install_label = ctk.CTkLabel(
            row,
            text=install_text,
            font=ctk.CTkFont(size=11),
            text_color=install_color,
            anchor="w",
            width=200
        )
        install_label.grid(row=0, column=2, padx=10, pady=10, sticky="w")
        
        # Running status - Column 3
        if is_gateway_managed:
            running_text = "N/A"
            running_color = self.colors["text_secondary"]
        elif is_running:
            running_text = "● Running"
            running_color = self.colors["accent_green"]
        else:
            running_text = "○ Stopped"
            running_color = self.colors["accent_red"]
        
        running_label = ctk.CTkLabel(
            row,
            text=running_text,
            font=ctk.CTkFont(size=11),
            text_color=running_color,
            anchor="w",
            width=200
        )
        running_label.grid(row=0, column=3, padx=10, pady=10, sticky="w")
        
        # Actions frame - Column 4 - ALL BUTTONS VISIBLE - COMPACT
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=4, padx=10, pady=10, sticky="w")
        
        # Reinstall CUDA button (Chatterbox only) - fallback option
        install_cuda_btn = None
        if svc == "chatterbox":
            install_cuda_btn = ctk.CTkButton(
                actions,
                text="Fix CUDA",
                width=95,
                height=35,
                font=ctk.CTkFont(size=12),
                fg_color="#9B59B6",  # Purple color for CUDA
                hover_color="#7D3C98",
                command=lambda: self.install_chatterbox_cuda()
            )
            install_cuda_btn.grid(row=0, column=0, padx=3)
        
        # Install button - smaller
        install_btn = ctk.CTkButton(
            actions,
            text="Install",
            width=75,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color=self.colors["accent_blue"],
            hover_color="#0063B1",
            command=lambda s=svc: self.install_service(s)
        )
        install_btn.grid(row=0, column=1 if svc == "chatterbox" else 0, padx=3)
        
        # Start button - smaller
        start_btn = ctk.CTkButton(
            actions,
            text="Start",
            width=70,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color=self.colors["accent_green"],
            hover_color="#0E6B0E",
            command=lambda s=svc: self.toggle_service(s),
            state="disabled" if is_gateway_managed else "normal"
        )
        start_btn.grid(row=0, column=2 if svc == "chatterbox" else 1, padx=3)
        
        # Stop button - smaller
        stop_btn = ctk.CTkButton(
            actions,
            text="Stop",
            width=70,
            height=28,
            font=ctk.CTkFont(size=10),
            fg_color=self.colors["accent_red"],
            hover_color="#B02A2E",
            command=lambda s=svc: self.stop_service(s),
            state="disabled" if is_gateway_managed else "normal"
        )
        stop_btn.grid(row=0, column=3 if svc == "chatterbox" else 2, padx=3)
        
        # Chatterbox optimization settings (collapsible section)
        settings_frame = None
        settings_toggle_btn = None
        if svc == "chatterbox":
            # Create collapsible settings section below the row
            settings_frame = ctk.CTkFrame(
                self.services_frame,
                fg_color=self.colors["bg_card"],
                corner_radius=5
            )
            # Place settings frame right after the service row
            settings_frame.grid(row=row_index + 1, column=0, sticky="ew", padx=5, pady=(0, 5))
            settings_frame.grid_columnconfigure(0, weight=1)
            
            # Settings container (will be shown/hidden)
            settings_container = ctk.CTkFrame(settings_frame, fg_color="transparent")
            settings_container.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
            settings_container.grid_columnconfigure(0, weight=1)
            settings_container.grid_columnconfigure(1, weight=1)
            
            # Settings title with toggle button
            settings_header = ctk.CTkFrame(settings_frame, fg_color="transparent")
            settings_header.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
            settings_header.grid_columnconfigure(0, weight=1)
            
            settings_title = ctk.CTkLabel(
                settings_header,
                text="⚙️ Optimization Settings",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.colors["text_primary"]
            )
            settings_title.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            
            # Toggle button (collapsed by default)
            settings_expanded = ctk.BooleanVar(value=False)
            settings_toggle_btn = ctk.CTkButton(
                settings_header,
                text="▼ Show",
                width=80,
                height=24,
                font=ctk.CTkFont(size=10),
                fg_color=self.colors["bg_panel"],
                hover_color=self.colors["border"],
                command=lambda: self._toggle_settings(settings_frame, settings_container, settings_toggle_btn, settings_expanded)
            )
            settings_toggle_btn.grid(row=0, column=1, padx=10, pady=5, sticky="e")
            
            # Settings content frame (hidden by default)
            settings_content = ctk.CTkFrame(settings_container, fg_color="transparent")
            settings_content.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 15))
            settings_content.grid_columnconfigure(0, weight=1)
            settings_content.grid_columnconfigure(1, weight=1)
            
            # Pre-warm checkbox (auto-ticked)
            prewarm_check = ctk.CTkCheckBox(
                settings_content,
                text="Enable Model Pre-warming",
                variable=self.chatterbox_settings["enable_prewarm"],
                font=ctk.CTkFont(size=11),
                text_color=self.colors["text_primary"],
                command=lambda: self._save_chatterbox_settings()  # Save on change
            )
            prewarm_check.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            
            # Tooltip for pre-warm
            prewarm_info = ctk.CTkLabel(
                settings_content,
                text="(Initializes CUDA kernels on startup for faster first request)",
                font=ctk.CTkFont(size=9),
                text_color=self.colors["text_secondary"]
            )
            prewarm_info.grid(row=1, column=0, padx=(30, 10), pady=(0, 10), sticky="w")
            
            # Note about when settings apply
            settings_note = ctk.CTkLabel(
                settings_content,
                text="⚠ Settings are saved automatically and apply on next service start",
                font=ctk.CTkFont(size=9, slant="italic"),
                text_color=self.colors["accent_orange"]
            )
            settings_note.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="w")
            
            # Hide settings content by default
            settings_container.grid_remove()
        
        # Store UI elements
        self.services_ui[svc] = {
            "install_status": install_label,
            "running_status": running_label,
            "install_cuda_btn": install_cuda_btn,
            "install_btn": install_btn,
            "start_btn": start_btn,
            "stop_btn": stop_btn,
            "row_frame": row,
            "settings_frame": settings_frame,
            "settings_toggle_btn": settings_toggle_btn
        }

    def log_to_launcher(self, message):
        """Log a message to the launcher tab only (thread-safe, batched)."""
        self.ui_logger.log_to_launcher(message)
    
    def log_to_service(self, service_name: str, message: str):
        """Log a message to a service-specific tab (thread-safe, batched)."""
        self.ui_logger.log_to_service(service_name, message)

    def install_service(self, service_name, blocking=False):
        """Install a single service. Always runs full install process."""
        def _run():
            # Mark heavy operation as active to reduce status update frequency
            self._heavy_operation_active = True
            try:
                self.services_ui[service_name]["install_btn"].configure(state="disabled")
                start_msg = f"\n--- Installing {service_name} ---\n"
                self.log_to_service(service_name, start_msg)
                self.log_to_launcher(f"[INSTALL] Starting installation of {service_name}...")
                
                success = False
                result_msg = ""
                
                try:
                    svc_info = self.service_manager.services.get(service_name)
                    if not svc_info:
                        result_msg = f"Unknown service: {service_name}"
                        self.log_to_service(service_name, result_msg)
                        return (False, result_msg)
                    
                    self.log_to_service(service_name, f"Installing {service_name} requirements...")
                    if service_name == "frontend":
                        self.log_to_service(service_name, f"Note: This will run npm install, npm update, and build")
                    else:
                        self.log_to_service(service_name, f"Note: This will always run pip install -r requirements.txt")
                        self.log_to_service(service_name, f"  - Already installed packages will be skipped")
                        self.log_to_service(service_name, f"  - New dependencies will be installed automatically")
                    self.log_to_launcher(f"[INSTALL] Installing {service_name} (always runs full install process)...")
                    
                    # Get install command (no force_reinstall flag needed)
                    cmd = svc_info["install_cmd"]()
                    
                    if not cmd:
                        result_msg = f"No install command for {service_name}"
                        self.log_to_service(service_name, result_msg)
                        self.services_ui[service_name]["install_btn"].configure(state="normal")
                        return (False, result_msg)
                    
                    cwd = svc_info["dir"]
                    
                    creation_flags = 0
                    if platform.system() == "Windows":
                        creation_flags = subprocess.CREATE_NO_WINDOW
                    
                    cmd_str = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
                    use_shell = False
                    if platform.system() == "Windows" and (cmd_str.endswith('.bat') or cmd_str.endswith('.cmd')):
                        use_shell = True
                    
                    start_new_session = False if platform.system() == "Windows" else True
                    # Set environment variables for UTF-8/emoji support
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    if platform.system() == "Windows":
                        env["PYTHONUTF8"] = "1"  # Python 3.7+ UTF-8 mode
                    # Suppress pkg_resources deprecation warnings from pip
                    env["PYTHONWARNINGS"] = "ignore::DeprecationWarning:pkg_resources"
                    
                    process = subprocess.Popen(
                        cmd,
                        cwd=str(cwd),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='surrogateescape',  # Better handling of invalid UTF-8 sequences
                        bufsize=1,
                        shell=use_shell,
                        creationflags=creation_flags,
                        start_new_session=start_new_session,
                        env=env
                    )
                    # Assign process to job object (Windows) or ensure it's in process group (Unix)
                    self._assign_to_process_group(process)
                    
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    for line in iter(process.stdout.readline, ''):
                        if not line:
                            break
                        clean_line = ansi_escape.sub('', line).rstrip()
                        # Filter out pkg_resources deprecation warnings
                        if 'pkg_resources' in clean_line and ('deprecated' in clean_line.lower() or 'setuptools.pypa.io' in clean_line.lower()):
                            continue
                        if clean_line:
                            # Log ALL installation output to service-specific tab
                            self.log_to_service(service_name, clean_line)
                            # Only log important messages to launcher tab (summary)
                            if any(keyword in clean_line.lower() for keyword in ['error', 'warning', 'success', 'installing', 'upgrading', 'creating', 'removing', 'downloading', 'building', 'completed', 'failed']):
                                self.log_to_launcher(f"[{service_name}] {clean_line}")
                    
                    return_code = process.wait()
                    
                    if return_code == 0:
                        success = True
                        result_msg = f"{service_name} installed successfully"
                        msg = f"\n--- {service_name} Installed Successfully ---\n"
                        self.log_to_service(service_name, msg)
                        self.log_to_launcher(f"[INSTALL] SUCCESS: {service_name}")
                        # Clear install status cache to force refresh
                        self._install_status_cache.pop(service_name, None)
                        self._install_status_cache_time.pop(service_name, None)
                        # Refresh install status UI immediately (bypass cache)
                        self.after(100, lambda sn=service_name: self._update_install_status(sn))
                    else:
                        success = False
                        result_msg = f"{service_name} failed (exit code: {return_code})"
                        msg = f"\n--- {service_name} Installation Failed (Exit code: {return_code}) ---\n"
                        self.log_to_service(service_name, msg)
                        self.log_to_launcher(f"[INSTALL] FAILED: {service_name} (exit code: {return_code})")
                        
                except Exception as e:
                    import traceback
                    success = False
                    result_msg = f"{service_name} error: {str(e)}"
                    err_msg = f"Error: {e}\n{traceback.format_exc()}"
                    self.log_to_service(service_name, err_msg)
                    self.log_to_launcher(f"[INSTALL] ERROR: {service_name} - {str(e)}")
                finally:
                    self.services_ui[service_name]["install_btn"].configure(state="normal")
                
                return (success, result_msg)
            finally:
                # Mark heavy operation as inactive after installation completes
                self._heavy_operation_active = False
        
        if blocking:
            return _run()
        else:
            threading.Thread(target=_run, daemon=True).start()
            return None
    
    def install_chatterbox_cuda(self):
        """Install PyTorch with CUDA support for Chatterbox TTS."""
        self.chatterbox_cuda_installer.install()

    def _disable_all_operation_buttons(self):
        """Disable Install All, Start All, and Stop All buttons."""
        self.install_all_btn.configure(state="disabled")
        self.start_all_btn.configure(state="disabled")
        self.stop_all_btn.configure(state="disabled")
    
    def _enable_all_operation_buttons(self):
        """Enable Install All, Start All, and Stop All buttons."""
        self.install_all_btn.configure(state="normal")
        self.start_all_btn.configure(state="normal")
        self.stop_all_btn.configure(state="normal")
    
    def install_all_services(self):
        """Install all enabled services simultaneously."""
        def _run():
            # Mark heavy operation as active
            self._heavy_operation_active = True
            try:
                self._disable_all_operation_buttons()
                
                header = "\n" + "="*60 + "\n"
                header += "       INSTALLING ALL ENABLED SERVICES\n"
                header += "="*60 + "\n"
                print(header)
                self.log_to_launcher(header)
                
                services_to_install = []
                for svc_name in self.services_ui.keys():
                    if self.service_vars.get(svc_name, ctk.BooleanVar(value=False)).get():
                        services_to_install.append(svc_name)
                
                self.log_to_launcher(f"Services to install: {', '.join(services_to_install)}")
                if "frontend" in services_to_install:
                    self.log_to_launcher(f"Installing {len(services_to_install)} services (frontend in parallel, others sequentially)...\n")
                else:
                    self.log_to_launcher(f"Installing {len(services_to_install)} services sequentially (one by one)...\n")
                
                # Results dictionary
                results = {"success": [], "failed": [], "skipped": []}
                
                # Separate frontend from other services to run in parallel
                frontend_services = [s for s in services_to_install if s == "frontend"]
                other_services = [s for s in services_to_install if s != "frontend"]
                
                # Function to install a service and update results
                def install_and_record(svc_name):
                    try:
                        self.log_to_launcher(f"[{svc_name}] Starting installation...")
                        result = self.install_service(svc_name, blocking=True)
                        if result:
                            success, msg = result
                            if success:
                                results["success"].append(svc_name)
                                self.log_to_launcher(f"[{svc_name}] ✓ Installation completed")
                                # Clear install status cache to force refresh
                                if svc_name in self._install_status_cache:
                                    del self._install_status_cache[svc_name]
                                if svc_name in self._install_status_cache_time:
                                    del self._install_status_cache_time[svc_name]
                                # Refresh install status UI
                                self.after(0, lambda sn=svc_name: self._update_install_status(sn))
                            else:
                                results["failed"].append((svc_name, msg))
                                self.log_to_launcher(f"[{svc_name}] ✗ Installation failed: {msg}")
                        else:
                            results["skipped"].append(svc_name)
                            self.log_to_launcher(f"[{svc_name}] ○ Installation skipped")
                    except Exception as e:
                        results["failed"].append((svc_name, str(e)))
                        self.log_to_launcher(f"[{svc_name}] ✗ Installation error: {str(e)}")
                
                # Start frontend installation in a separate thread if it's in the list
                frontend_thread = None
                if frontend_services:
                    frontend_thread = threading.Thread(
                        target=lambda: install_and_record("frontend"),
                        daemon=False
                    )
                    frontend_thread.start()
                    self.log_to_launcher(f"[frontend] Starting installation in parallel...")
                
                # Install other services sequentially (to avoid resource exhaustion)
                for svc_name in other_services:
                    install_and_record(svc_name)
                
                # Wait for frontend installation to complete if it was started
                if frontend_thread:
                    self.log_to_launcher(f"[frontend] Waiting for frontend installation to complete...")
                    frontend_thread.join()
                    self.log_to_launcher(f"[frontend] Frontend installation thread finished")
                
                summary = "\n" + "="*60 + "\n"
                summary += "       INSTALLATION SUMMARY\n"
                summary += "="*60 + "\n\n"
                
                if results["success"]:
                    summary += f"✓ SUCCESS ({len(results['success'])}):\n"
                    for svc in results["success"]:
                        summary += f"   • {svc}\n"
                    summary += "\n"
                
                if results["failed"]:
                    summary += f"✗ FAILED ({len(results['failed'])}):\n"
                    for svc, msg in results["failed"]:
                        summary += f"   • {svc}: {msg}\n"
                    summary += "\n"
                
                if results["skipped"]:
                    summary += f"○ SKIPPED ({len(results['skipped'])}):\n"
                    for svc in results["skipped"]:
                        summary += f"   • {svc}\n"
                    summary += "\n"
                
                total = len(services_to_install)
                success_count = len(results["success"])
                failed_count = len(results["failed"])
                
                if failed_count == 0:
                    summary += f"✓ All {success_count} services installed successfully!\n"
                else:
                    summary += f"⚠ {success_count}/{total} services installed, {failed_count} failed\n"
                
                summary += "="*60 + "\n"
                
                print(summary)
                self.log_to_launcher(summary)
                
                self._enable_all_operation_buttons()
                # Mark heavy operation as inactive after all installations complete
                self._heavy_operation_active = False
            except Exception:
                # Ensure flag is reset and buttons are re-enabled even on error
                self._enable_all_operation_buttons()
                self._heavy_operation_active = False
                raise
        
        threading.Thread(target=_run, daemon=True).start()

    def start_all_services(self):
        def _run():
            self._disable_all_operation_buttons()
            
            enabled_services = []
            for svc_name in self.service_manager.services.keys():
                if svc_name in self.service_vars and self.service_vars[svc_name].get():
                    enabled_services.append(svc_name)
            
            self.log_to_launcher("\n" + "="*60)
            self.log_to_launcher(f"--- Starting All Checked Services ({len(enabled_services)} enabled) ---")
            if enabled_services:
                self.log_to_launcher(f"Services to start: {', '.join(enabled_services)}")
            else:
                self.log_to_launcher("No services are checked/enabled!")
                self._enable_all_operation_buttons()
                return
            
            # Separate core services from other services
            core_services = getattr(self.service_manager, 'core_services', ["memory", "tools", "gateway", "llm"])
            core_to_start = [s for s in enabled_services if s in core_services]
            other_to_start = [s for s in enabled_services if s not in core_services]
            
            started_count = 0
            skipped_count = 0
            
            # Start core services simultaneously
            if core_to_start:
                self.log_to_launcher(f"Starting core services simultaneously: {', '.join(core_to_start)}")
                core_threads = []
                for svc_name in core_to_start:
                    is_gateway_managed = (svc_name == "llm")
                    if is_gateway_managed:
                        self.log_to_launcher(f"{svc_name} is managed by Gateway (skipping)")
                        skipped_count += 1
                        continue  # Skip LLM, it's managed by Gateway
                
                    is_running = svc_name in self.processes and self.processes[svc_name].poll() is None
                    if not is_running:
                        self.log_to_launcher(f"Starting {svc_name}...")
                        thread = threading.Thread(target=self.toggle_service, args=(svc_name,), daemon=True)
                        thread.start()
                        core_threads.append(thread)
                        started_count += 1
                    else:
                        self.log_to_launcher(f"{svc_name} is already running (skipping)")
                        skipped_count += 1
                
                # Wait a moment for core services to start
                time.sleep(0.5)
            
            # Start other services
            for svc_name in other_to_start:
                is_running = svc_name in self.processes and self.processes[svc_name].poll() is None
                if not is_running:
                    self.log_to_launcher(f"Starting {svc_name}...")
                    thread = threading.Thread(target=self.toggle_service, args=(svc_name,), daemon=True)
                    thread.start()
                    started_count += 1
                else:
                    self.log_to_launcher(f"{svc_name} is already running (skipping)")
                    skipped_count += 1
            
            self.log_to_launcher(f"--- Initiated start for {started_count} service(s), {skipped_count} skipped ---\n")
            self._enable_all_operation_buttons()
        
        threading.Thread(target=_run, daemon=True).start()

    def toggle_service(self, service_name):
        """Toggle service start/stop based on current running status."""
        is_running = service_name in self.processes and self.processes[service_name].poll() is None
        
        if is_running:
            self.stop_service(service_name)
        else:
            self.start_service(service_name)

    def start_service(self, service_name):
        def _run():
            start_msg = f"Starting {service_name}..."
            print(start_msg)
            self.log_to_service(service_name, start_msg)
            self.log_to_launcher(f"[{service_name}] {start_msg}")
            self.after(0, lambda: self._update_running_status(service_name))
            
            try:
                svc_info = self.service_manager.services.get(service_name)
                if not svc_info:
                    err_msg = f"Unknown service: {service_name}"
                    print(err_msg)
                    self.log_to_service(service_name, err_msg)
                    return

                # Check for port conflicts and optionally kill stuck processes
                port = svc_info.get("port")
                if port:
                    try:
                        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_socket.settimeout(1)
                        result = test_socket.connect_ex(('localhost', port))
                        test_socket.close()
                        if result == 0:
                            # Port is in use - try to kill the stuck process
                            self.log_to_launcher(f"[{service_name}] Port {port} is in use, attempting to kill stuck process...")
                            self._kill_process_on_port(port)
                            # Wait longer and retry multiple times
                            max_retries = 5
                            port_freed = False
                            for retry in range(max_retries):
                                time.sleep(2)  # Wait 2 seconds between retries
                                test_socket2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                test_socket2.settimeout(1)
                                result2 = test_socket2.connect_ex(('localhost', port))
                                test_socket2.close()
                                if result2 != 0:
                                    # Port is now free
                                    port_freed = True
                                    self.log_to_launcher(f"[{service_name}] Successfully cleared port {port} after {retry + 1} attempt(s)")
                                    break
                                else:
                                    # Still in use, try killing again
                                    if retry < max_retries - 1:
                                        self.log_to_launcher(f"[{service_name}] Port {port} still in use, retrying kill (attempt {retry + 2}/{max_retries})...")
                                        self._kill_process_on_port(port)
                            
                            if not port_freed:
                                # Still in use after all retries
                                err_msg = f"Port {port} is still in use after {max_retries} kill attempts.\nPlease manually stop the process using port {port}."
                                print(err_msg)
                                self.log_to_service(service_name, err_msg)
                                self.log_to_launcher(f"[{service_name}] ERROR: Port {port} still in use after {max_retries} attempts")
                                return
                    except Exception:
                        # Socket check failed, but continue anyway
                        pass

                cmd = svc_info["start_cmd"]()
                cwd = svc_info["dir"]
                
                is_installed = self._check_service_installed(service_name, svc_info)
                if not is_installed:
                    msg = f"{service_name} is not installed. Please install it first using the Install button."
                    print(msg)
                    self.log_to_service(service_name, msg)
                    self.log_to_launcher(f"[{service_name}] NOT INSTALLED - run Install first")
                    return
                
                if not cmd:
                    if service_name == "llm":
                        msg = f"{service_name} is managed by the Gateway service.\nStart the Gateway first, then load a model via the frontend."
                        print(msg)
                        self.log_to_service(service_name, msg)
                        self._update_install_status(service_name)
                        return
                    else:
                        msg = f"{service_name} is not installed. Please install it first using the Install button."
                        print(msg)
                        self.log_to_service(service_name, msg)
                        self.log_to_launcher(f"[{service_name}] NOT INSTALLED - run Install first")
                        self._update_install_status(service_name)
                        return
                
                creation_flags = 0
                start_new_session = False
                if platform.system() == "Windows":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                else:
                    # On Unix, use start_new_session to create a new process group
                    # This ensures children die when parent dies
                    start_new_session = True
                
                # Set environment variables
                env = os.environ.copy()
                
                # For Chatterbox: Check if CUDA PyTorch is available and set DEVICE accordingly
                if service_name == "chatterbox":
                    venv_python = svc_info.get("venv") / ("Scripts" if platform.system() == "Windows" else "bin") / "python"
                    if platform.system() == "Windows":
                        venv_python = venv_python.with_suffix(".exe")
                    
                    if venv_python.exists():
                        try:
                            # Check if CUDA PyTorch is available
                            check_cuda_cmd = [str(venv_python), "-c", "import torch; print('CUDA_AVAILABLE:', torch.cuda.is_available()); print('CUDA_BUILT:', torch.version.cuda if hasattr(torch.version, 'cuda') and torch.version.cuda else 'None')"]
                            cuda_check = subprocess.run(
                                check_cuda_cmd,
                                capture_output=True,
                                text=True,
                                timeout=10,
                                creationflags=creation_flags if platform.system() == "Windows" else 0
                            )
                            if cuda_check.returncode == 0:
                                if "CUDA_AVAILABLE: True" in cuda_check.stdout and "CUDA_BUILT: None" not in cuda_check.stdout:
                                    env["DEVICE"] = "cuda"
                                    self.log_to_service(service_name, "[CUDA] CUDA PyTorch detected - setting DEVICE=cuda")
                                    self.log_to_launcher(f"[{service_name}] CUDA PyTorch detected - using GPU")
                                else:
                                    env["DEVICE"] = "cpu"
                                    self.log_to_service(service_name, "[CUDA] CUDA not available - using CPU")
                                    self.log_to_launcher(f"[{service_name}] CUDA not available - using CPU")
                        except Exception as e:
                            # If check fails, default to auto (let Chatterbox decide)
                            env["DEVICE"] = "auto"
                            self.log_to_service(service_name, f"[CUDA] Could not check CUDA availability: {e}")
                
                # Ensure UTF-8 encoding for all services (allows emojis to display properly)
                env["PYTHONIOENCODING"] = "utf-8"
                if platform.system() == "Windows":
                    # Set console code page to UTF-8 for subprocess
                    env["PYTHONUTF8"] = "1"  # Python 3.7+ UTF-8 mode
                
                # Suppress pkg_resources deprecation warnings from all services
                env["PYTHONWARNINGS"] = "ignore::DeprecationWarning:pkg_resources,ignore::UserWarning:pkg_resources"
                
                # Chatterbox optimization settings
                if service_name == "chatterbox":
                    env["ENABLE_MODEL_PREWARM"] = "true" if self.chatterbox_settings["enable_prewarm"].get() else "false"
                    self.log_to_service(service_name, f"[OPTIMIZATION] Pre-warm: {env['ENABLE_MODEL_PREWARM']}")
                
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='surrogateescape',  # Better handling of invalid UTF-8 sequences (allows emojis)
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=creation_flags,
                    env=env,
                    start_new_session=start_new_session
                )
                
                # Assign process to job object (Windows) or ensure it's in process group (Unix)
                self._assign_to_process_group(process)
                
                self.processes[service_name] = process
                self.service_start_times[service_name] = time.time()  # Track when service started
                self.service_status_confirmed[service_name] = False  # Reset confirmed status
                
                threading.Thread(target=self.wait_for_service, args=(service_name,), daemon=True).start()
                
                def read_output():
                    """Capture ALL stdout/stderr from the service subprocess and log to service tab."""
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    try:
                        for line in iter(process.stdout.readline, ''):
                            if not line:
                                break
                            clean_line = ansi_escape.sub('', line).strip()
                            if clean_line:
                                # Check if this is an LLM-related log from gateway
                                # Gateway logs LLM messages with "[LLM]" prefix or similar patterns
                                is_llm_log = (
                                    service_name == "gateway" and (
                                        "[LLM]" in clean_line or
                                        "llm_server" in clean_line.lower() or
                                        "llama-cpp" in clean_line.lower() or
                                        "llm server" in clean_line.lower() or
                                        "llm_server_service" in clean_line.lower()
                                    )
                                )
                                
                                if is_llm_log:
                                    # Route to LLM tab
                                    self.log_to_service("llm", clean_line)
                                else:
                                    # Log ALL output to service-specific tab
                                    self.log_to_service(service_name, clean_line)
                                
                                # Also log important messages to launcher tab (summary)
                                line_lower = clean_line.lower()
                                if any(keyword in line_lower for keyword in ['error', 'warning', 'exception', 'traceback', 'failed', 'fatal', 'critical', 'stopped', 'crashed']):
                                    self.log_to_launcher(f"[{service_name}] {clean_line}")
                    except Exception as e:
                        error_msg = f"Error reading output from {service_name}: {e}"
                        self.log_to_service(service_name, error_msg)
                        self.log_to_launcher(f"[{service_name}] ERROR: {error_msg}")
                    finally:
                        try:
                            process.stdout.close()
                        except:
                            pass
                    
                    # Check if process exited unexpectedly
                    if self.processes.get(service_name) == process:
                        msg = f"{service_name} stopped unexpectedly. Try reinstalling if the problem persists."
                        self.log_to_service(service_name, msg)
                        self.log_to_launcher(f"[{service_name}] {msg}")
                        self._update_running_status(service_name)
                        if service_name in self.processes:
                            del self.processes[service_name]
                        if service_name in self.service_start_times:
                            del self.service_start_times[service_name]
                        if service_name in self.service_status_confirmed:
                            del self.service_status_confirmed[service_name]

                threading.Thread(target=read_output, daemon=True).start()
                
            except Exception as e:
                err_msg = f"Error starting {service_name}: {e}"
                print(err_msg)
                self.log_to_service(service_name, err_msg)
                self.log_to_launcher(f"[{service_name}] ERROR: {err_msg}")
                self._update_running_status(service_name)
        
        threading.Thread(target=_run, daemon=True).start()

    def wait_for_service(self, service_name):
        """Wait for service to become healthy."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            return

        url = svc_info.get("url")
        health_endpoint = svc_info.get("health_endpoint")
        
        for _ in range(30):
            if service_name not in self.processes or self.processes[service_name].poll() is not None:
                return
            
            try:
                if health_endpoint:
                    check_url = f"{url}{health_endpoint}"
                    with urllib.request.urlopen(check_url, timeout=1) as response:
                        if response.status == 200:
                            self.service_status_confirmed[service_name] = True  # Mark as confirmed running
                            self.after(0, lambda: self._update_running_status(service_name))
                            self.log_to_launcher(f"[{service_name}] Service is now RUNNING")
                            return
                else:
                    parsed = urllib.parse.urlparse(url)
                    host = parsed.hostname or "localhost"
                    port = parsed.port or 80
                    with socket.create_connection((host, port), timeout=1):
                        self.service_status_confirmed[service_name] = True  # Mark as confirmed running
                        self.after(0, lambda: self._update_running_status(service_name))
                        self.log_to_launcher(f"[{service_name}] Service is now RUNNING")
                        return
            except (urllib.error.URLError, socket.error, socket.timeout):
                pass
            
            time.sleep(1)
        
        if service_name in self.processes and self.processes[service_name].poll() is None:
             self.after(0, lambda: self._update_running_status(service_name))
             self.log_to_launcher(f"[{service_name}] Service is RUNNING (health check timeout, but process is alive)")

    def stop_service(self, service_name):
        stop_msg = f"Stopping {service_name}..."
        print(stop_msg)
        self.log_to_launcher(f"[{service_name}] {stop_msg}")
        proc = self.processes.get(service_name)
        
        # Get service port for cleanup
        svc_info = self.service_manager.services.get(service_name)
        service_port = svc_info.get("port") if svc_info else None
        
        if proc:
            try:
                if proc.poll() is None:
                    # Try graceful shutdown first
                    if platform.system() == "Windows":
                        print(f"  Sending shutdown signal to {service_name}...")
                        proc.terminate()
                    else:
                        import signal
                        print(f"  Sending SIGINT to {service_name}...")
                        proc.send_signal(signal.SIGINT)
                    
                    # Wait briefly for graceful shutdown (shorter timeout for faster response)
                    try:
                        proc.wait(timeout=3)
                        print(f"  {service_name} shut down gracefully")
                        self.log_to_launcher(f"[{service_name}] Shut down gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill using process tree to ensure all children are killed
                        print(f"  {service_name} did not shut down gracefully, force killing process tree...")
                        self.log_to_launcher(f"[{service_name}] Force killing process tree...")
                        kill_process_tree(proc.pid)
                        try:
                            proc.wait(timeout=2)
                            msg = f"{service_name} force killed"
                            print(f"  {msg}")
                            self.log_to_launcher(f"[{service_name}] {msg}")
                        except subprocess.TimeoutExpired:
                            print(f"  Warning: {service_name} process may still be running")
                            self.log_to_launcher(f"[{service_name}] Warning: Process may still be running")
            except Exception as e:
                print(f"  Error during shutdown: {e}")
                self.log_to_launcher(f"[{service_name}] Error during shutdown: {e}")
                # Fallback: try to kill process tree
                try:
                    if proc.poll() is None:
                        kill_process_tree(proc.pid)
                        self.log_to_launcher(f"[{service_name}] Force killed via fallback")
                except Exception as kill_error:
                    self.log_to_launcher(f"[{service_name}] Fallback kill failed: {kill_error}")
            
            if service_name in self.processes:
                del self.processes[service_name]
        
        # Also kill any processes on the service port (handles child processes that weren't tracked)
        if service_port:
            try:
                print(f"  Checking for processes on port {service_port}...")
                if kill_process_on_port(service_port):
                    self.log_to_launcher(f"[{service_name}] Killed processes on port {service_port}")
                    print(f"  Killed processes on port {service_port}")
            except Exception as e:
                print(f"  Warning: Could not check port {service_port}: {e}")
        
        # Clear tracking data when service stops
        if service_name in self.service_start_times:
            del self.service_start_times[service_name]
        if service_name in self.service_status_confirmed:
            del self.service_status_confirmed[service_name]
        
        self.after(0, lambda: self._update_running_status(service_name))
        self.log_to_launcher(f"[{service_name}] Service stopped")

    def stop_all_services(self):
        def _run():
            self._disable_all_operation_buttons()
            self.log_to_launcher("\n--- Stopping All Enabled Services ---")
            
            enabled_services = []
            for svc_name in self.service_manager.services.keys():
                if svc_name in self.service_vars and self.service_vars[svc_name].get():
                    enabled_services.append(svc_name)
            
            stopped_count = 0
            for svc_name in enabled_services:
                is_running = svc_name in self.processes and self.processes[svc_name].poll() is None
                if is_running:
                    self.log_to_launcher(f"Stopping {svc_name}...")
                    self.stop_service(svc_name)
                    time.sleep(1)
                    stopped_count += 1
                else:
                    self.log_to_launcher(f"{svc_name} is not running (skipping)")
            
            self.log_to_launcher(f"--- Stopped {stopped_count} service(s) ---\n")
            self._enable_all_operation_buttons()
        
        threading.Thread(target=_run, daemon=True).start()

    def _check_service_installed(self, service_name: str, svc_info: Optional[Dict], use_cache: bool = True) -> bool:
        """Check if a service is properly installed. Uses cache to avoid repeated file I/O."""
        if not svc_info:
            return False
        
        # Check cache first
        if use_cache:
            cache_time = self._install_status_cache_time.get(service_name, 0)
            if time.time() - cache_time < self._cache_ttl:
                return self._install_status_cache.get(service_name, False)
        
        if service_name == "frontend":
            frontend_dir = svc_info.get("dir")
            if not frontend_dir:
                return False
            node_modules = frontend_dir / "node_modules"
            package_json = frontend_dir / "package.json"
            return node_modules.exists() and package_json.exists()
        
        venv_path = svc_info.get("venv")
        if not venv_path:
            return False
        
        if not venv_path.exists():
            return False
        
        if platform.system() == "Windows":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if not python_exe.exists():
            return False
        
        # Verify Python works
        try:
            result = subprocess.run(
                [str(python_exe), "--version"],
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            if result.returncode != 0:
                result_value = False
                if use_cache:
                    self._install_status_cache[service_name] = result_value
                    self._install_status_cache_time[service_name] = time.time()
                return result_value
        except Exception:
            result_value = False
            if use_cache:
                self._install_status_cache[service_name] = result_value
                self._install_status_cache_time[service_name] = time.time()
            return result_value
    
        # For core services sharing a venv, check if this service's specific requirements are installed
        is_core = svc_info.get("is_core", False)
        if is_core:
            key_packages = {
                "memory": "chromadb",
                "tools": "Pillow",         # Tools usually needs Pillow or similar
                "gateway": "aiohttp",      # Gateway uses aiohttp
                "llm": "llama-cpp-python"  # LLM definitely needs this
            }
            
            pkg_name = key_packages.get(service_name)
            if pkg_name:
                try:
                    # Use pip show which is much faster than pip list --format=json
                    # It returns exit code 0 if found, 1 if not found
                    cmd = [str(python_exe), "-m", "pip", "show", pkg_name]
                    
                    # Set environment variable to suppress warnings
                    env = os.environ.copy()
                    env["PYTHONWARNINGS"] = "ignore"
                    
                    if sys.platform == 'win32':
                        creationflags = subprocess.CREATE_NO_WINDOW
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            creationflags=creationflags,
                            env=env,
                            timeout=5
                        )
                    else:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=5
                        )
                    
                    if result.returncode != 0:
                        # Package not found
                        if use_cache:
                            self._install_status_cache[service_name] = False
                            self._install_status_cache_time[service_name] = time.time()
                        return False
                        
                except Exception as e:
                    # If check fails, we can't be sure
                    if use_cache:
                        self._install_status_cache[service_name] = False
                        self._install_status_cache_time[service_name] = time.time()
                    return False
        
        result_value = True
        # Cache the result
        if use_cache:
            self._install_status_cache[service_name] = result_value
            self._install_status_cache_time[service_name] = time.time()
        return result_value
    
    def _check_if_needs_reinstall(self, service_name: str) -> bool:
        """Check if a service needs to be reinstalled due to missing dependencies."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            return False
        
        if service_name == "frontend":
            return False
        
        venv_path = svc_info.get("venv")
        if not venv_path or not venv_path.exists():
            return True
        
        if platform.system() == "Windows":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if not python_exe.exists():
            return True
        
        try:
            result = subprocess.run(
                [str(python_exe), "-c", "import uvicorn"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            if result.returncode != 0:
                return True
        except Exception:
            return True
        
        return False
    
    def refresh_all_service_statuses(self):
        """Refresh installation and running status for all services."""
        def _run():
            """Run status checks in background thread to avoid blocking UI."""
            for service_name in self.services_ui.keys():
                # Schedule UI updates on main thread
                self.after(0, lambda sn=service_name: self._update_install_status(sn))
                self.after(0, lambda sn=service_name: self._update_running_status(sn))
        
        # Run in background thread to avoid blocking UI
        threading.Thread(target=_run, daemon=True).start()
    
    def _start_periodic_status_refresh(self):
        """Start periodic status refresh."""
        # Skip status updates during heavy operations (installations, etc.)
        if not self._heavy_operation_active:
            for service_name in self.services_ui.keys():
                self._update_running_status(service_name)
        # Increase interval during heavy operations to reduce load
        interval = 5000 if self._heavy_operation_active else 2000
        self.after(interval, self._start_periodic_status_refresh)
    
    def _update_install_status(self, service_name):
        """Update service UI status based on installation state."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            return
        
        install_label = self.services_ui[service_name].get("install_status")
        if not install_label:
            return
        
        # Show "Checking..." initially for better UX
        install_label.configure(text="⏳ Checking...", text_color=self.colors["text_secondary"])
        
        def _check():
            """Check installation status in background thread with timeout."""
            is_installed = False
            check_success = False
            try:
                # Use threading with timeout to prevent hanging
                import queue
                result_queue = queue.Queue()
                
                def _do_check():
                    try:
                        result = self._check_service_installed(service_name, svc_info, use_cache=True)
                        result_queue.put(("success", result))
                    except Exception as e:
                        result_queue.put(("error", e))
                
                check_thread = threading.Thread(target=_do_check, daemon=True)
                check_thread.start()
                check_thread.join(timeout=15)  # 15 second timeout
                
                if check_thread.is_alive():
                    logger.warning(f"Install status check for {service_name} timed out after 15 seconds")
                    is_installed = False
                    check_success = False
                else:
                    try:
                        status, value = result_queue.get_nowait()
                        if status == "success":
                            is_installed = value
                            check_success = True
                        else:
                            raise value
                    except queue.Empty:
                        logger.warning(f"Install status check for {service_name} completed but no result")
                        is_installed = False
                        check_success = False
            except Exception as e:
                logger.error(f"Error checking install status for {service_name}: {e}", exc_info=True)
                is_installed = False
                check_success = False
            
            # Update UI on main thread - capture install_label in closure
            def update_ui():
                try:
                    if not check_success:
                        install_label.configure(
                            text="✗ Error",
                            text_color=self.colors.get("accent_red", "#ef4444")
                        )
                    else:
                        install_label.configure(
                            text="✓ Installed" if is_installed else "✗ Not Installed",
                            text_color=self.colors["accent_green"] if is_installed else self.colors["accent_orange"]
                        )
                except Exception as e:
                    logger.debug(f"Error updating install status UI for {service_name}: {e}")
            
            self.after(0, update_ui)
        
        # Run check in background thread to avoid blocking UI
        threading.Thread(target=_check, daemon=True).start()
    
    def _update_running_status(self, service_name):
        """Update the running status indicator for a service."""
        if service_name not in self.services_ui:
            return
        
        is_gateway_managed = (service_name == "llm")
        
        running_label = self.services_ui[service_name].get("running_status")
        if not running_label:
            return
        
        start_btn = self.services_ui[service_name].get("start_btn")
        stop_btn = self.services_ui[service_name].get("stop_btn")
        
        if is_gateway_managed:
            running_label.configure(text="N/A", text_color=self.colors["text_secondary"])
            if start_btn and stop_btn:
                start_btn.configure(state="disabled")
                stop_btn.configure(state="disabled")
            return
        
        is_running = service_name in self.processes and self.processes[service_name].poll() is None
        
        if is_running:
            svc_info = self.service_manager.services.get(service_name)
            if svc_info:
                # Check if status was already confirmed as "Running"
                if self.service_status_confirmed.get(service_name, False):
                    # Status confirmed - show Running and don't check again
                    running_label.configure(text="● Running", text_color=self.colors["accent_green"])
                    if start_btn and stop_btn:
                        start_btn.configure(state="disabled", text="Start")
                        stop_btn.configure(state="normal")
                    return
                
                url = svc_info.get("url")
                health_endpoint = svc_info.get("health_endpoint")
                start_time = self.service_start_times.get(service_name, 0)
                time_since_start = time.time() - start_time if start_time > 0 else 999
                
                def check_health():
                    try:
                        is_healthy = False
                        if health_endpoint:
                            check_url = f"{url}{health_endpoint}"
                            with urllib.request.urlopen(check_url, timeout=1.0) as response:
                                if response.status == 200:
                                    is_healthy = True
                        else:
                            parsed = urllib.parse.urlparse(url)
                            host = parsed.hostname or "localhost"
                            port = parsed.port or 80
                            with socket.create_connection((host, port), timeout=1.0):
                                is_healthy = True
                        
                        if is_healthy:
                            # Health check succeeded - confirm as running
                            self.service_status_confirmed[service_name] = True
                            self.after(0, lambda lbl=running_label: lbl.configure(text="● Running", text_color=self.colors["accent_green"]))
                            if start_btn and stop_btn:
                                self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                        else:
                            # Health check failed - only show "Starting" if recently started (< 10 seconds)
                            if time_since_start < 10:
                                self.after(0, lambda lbl=running_label: lbl.configure(text="⏳ Starting", text_color=self.colors["accent_orange"]))
                            else:
                                # Service has been running for a while but health check fails - show as running anyway
                                self.after(0, lambda lbl=running_label: lbl.configure(text="● Running", text_color=self.colors["accent_green"]))
                            if start_btn and stop_btn:
                                self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                    except (urllib.error.URLError, socket.error, socket.timeout, Exception):
                        # Health check exception - only show "Starting" if recently started (< 10 seconds)
                        if time_since_start < 10:
                            self.after(0, lambda lbl=running_label: lbl.configure(text="⏳ Starting", text_color=self.colors["accent_orange"]))
                        else:
                            # Service has been running for a while - show as running anyway
                            self.after(0, lambda lbl=running_label: lbl.configure(text="● Running", text_color=self.colors["accent_green"]))
                        if start_btn and stop_btn:
                            self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                
                threading.Thread(target=check_health, daemon=True).start()
                # Show "Starting" initially if service just started, otherwise show current status
                if time_since_start < 10:
                    running_label.configure(text="⏳ Starting", text_color=self.colors["accent_orange"])
                else:
                    running_label.configure(text="● Running", text_color=self.colors["accent_green"])
                if start_btn and stop_btn:
                    start_btn.configure(state="disabled", text="Start")
                    stop_btn.configure(state="normal")
            else:
                running_label.configure(text="● Running", text_color=self.colors["accent_green"])
                if start_btn and stop_btn:
                    start_btn.configure(state="disabled", text="Start")
                    stop_btn.configure(state="normal")
        else:
            running_label.configure(text="○ Stopped", text_color=self.colors["accent_red"])
            if start_btn and stop_btn:
                start_btn.configure(state="normal", text="Start")
                stop_btn.configure(state="disabled")

    def open_web_ui(self):
        webbrowser.open("http://localhost:8002")

    def reset_app_state(self):
        """Reset all app state (conversations, settings, vector store) but keep models."""
        import tkinter.messagebox as messagebox
        import requests
        
        result = messagebox.askyesno(
            "Reset App State",
            "This will delete:\n"
            "- All conversations\n"
            "- All settings\n"
            "- Vector store data\n\n"
            "Models will be kept.\n\n"
            "Are you sure you want to continue?",
            icon="warning"
        )
        
        if not result:
            return
        
        def _run():
            self.reset_app_btn.configure(state="disabled")
            
            header = "\n" + "="*60 + "\n"
            header += "       RESETTING APP STATE\n"
            header += "="*60 + "\n"
            print(header)
            self.log_to_launcher(header)
            
            try:
                self.log_to_launcher("Calling reset API endpoint...")
                response = requests.post("http://localhost:8000/api/reset?keep_models=true", timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    self.log_to_launcher(f"✓ Reset successful!")
                    self.log_to_launcher(f"  - Deleted {result.get('conversations_deleted', 0)} conversations")
                    self.log_to_launcher(f"  - Settings cleared: {result.get('settings_cleared', False)}")
                    self.log_to_launcher(f"  - Vector store cleared: {result.get('vector_store_cleared', False)}")
                    self.log_to_launcher("\nApp state has been reset. Models are preserved.")
                    messagebox.showinfo("Reset Complete", "App state has been reset successfully!\n\nModels are preserved.")
                else:
                    error_msg = response.json().get("detail", "Unknown error")
                    self.log_to_launcher(f"✗ Reset failed: {error_msg}")
                    messagebox.showerror("Reset Failed", f"Failed to reset app state:\n{error_msg}")
            except requests.exceptions.ConnectionError:
                self.log_to_launcher("✗ Cannot connect to gateway service. Is it running?")
                messagebox.showerror("Connection Error", "Cannot connect to gateway service.\n\nPlease ensure the gateway service is running.")
            except Exception as e:
                self.log_to_launcher(f"✗ Error resetting app state: {e}")
                messagebox.showerror("Error", f"Error resetting app state:\n{str(e)}")
            finally:
                self.reset_app_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def _start_watcher(self):
        """Start a watcher process that monitors the launcher and kills subprocesses if it dies."""
        try:
            # Get the current process ID
            launcher_pid = os.getpid()
            
            # Get the watcher script path
            watcher_script = launcher_dir / "process" / "watcher.py"
            
            if not watcher_script.exists():
                logger.warning(f"Watcher script not found at {watcher_script}, skipping watcher startup")
                return
            
            # Get Python executable
            python_exe = sys.executable
            
            # Start watcher as a separate process
            # Use CREATE_NO_WINDOW on Windows to hide the console
            creation_flags = 0
            if platform.system() == "Windows":
                creation_flags = subprocess.CREATE_NO_WINDOW
            
            # Start watcher process (detached, won't die with parent)
            # On Windows, use DETACHED_PROCESS flag
            # On Unix, use start_new_session
            start_new_session = platform.system() != "Windows"
            if platform.system() == "Windows":
                creation_flags |= subprocess.DETACHED_PROCESS
            
            self._watcher_process = subprocess.Popen(
                [python_exe, str(watcher_script), str(launcher_pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
                start_new_session=start_new_session
            )
            
            logger.info(f"Started watcher process (PID: {self._watcher_process.pid}) to monitor launcher (PID: {launcher_pid})")
        except Exception as e:
            logger.warning(f"Failed to start watcher process: {e}")
            # Don't fail launcher startup if watcher fails
    
    def _stop_watcher(self):
        """Stop the watcher process."""
        if self._watcher_process:
            try:
                if self._watcher_process.poll() is None:
                    self._watcher_process.terminate()
                    try:
                        self._watcher_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._watcher_process.kill()
                        self._watcher_process.wait()
            except Exception:
                pass
            self._watcher_process = None
    
    def _kill_process_on_port(self, port: int) -> bool:
        """Wrapper for kill_process_on_port from process_utils."""
        return kill_process_on_port(port)
    
    def _cleanup_orphaned_processes(self):
        """Clean up orphaned processes - runs in background thread to avoid blocking UI."""
        """Clean up any orphaned processes from previous launcher sessions. Runs only once."""
        def _run():
            try:
                # Get all service ports
                known_ports = []
                for svc_name, svc_info in self.service_manager.services.items():
                    port = svc_info.get("port")
                    if port:
                        known_ports.append(port)
                
                if not known_ports:
                    return
                
                self.log_to_launcher("🔍 Checking for orphaned processes...")
                
                # Find all processes on service ports (only once)
                port_pids = find_all_processes_on_ports(known_ports)
                total_found = sum(len(pids) for pids in port_pids.values())
                
                if total_found == 0:
                    self.log_to_launcher("✓ No orphaned processes found")
                    return
                
                # Log what we found
                self.log_to_launcher(f"⚠ Found {total_found} orphaned process(es) on service ports:")
                for port, pids in port_pids.items():
                    if pids:
                        self.log_to_launcher(f"  - Port {port}: {len(pids)} process(es) (PIDs: {', '.join(map(str, pids))})")
                
                # Kill all processes (only once, no retry loop)
                self.log_to_launcher("🧹 Cleaning up orphaned processes...")
                cleanup_all_service_ports(known_ports)
                
                # Wait a bit for processes to fully terminate
                time.sleep(1)
                
                # Verify cleanup (only once, no loop)
                port_pids_after = find_all_processes_on_ports(known_ports)
                total_remaining = sum(len(pids) for pids in port_pids_after.values())
                
                if total_remaining == 0:
                    self.log_to_launcher(f"✓ Successfully cleaned up {total_found} orphaned process(es)")
                else:
                    self.log_to_launcher(f"⚠ Warning: {total_remaining} process(es) still remain after cleanup")
                    for port, pids in port_pids_after.items():
                        if pids:
                            self.log_to_launcher(f"  - Port {port}: {len(pids)} process(es) still running (PIDs: {', '.join(map(str, pids))})")
            except Exception as e:
                # Silently fail - don't spam errors
                pass
        
        # Run cleanup in background thread to not block UI startup (only once)
        threading.Thread(target=_run, daemon=True).start()
    
    def _assign_to_process_group(self, process):
        """Assign a process to the job object/process group."""
        # Handle deferred initialization - process group manager might not be ready yet
        if self.process_group_manager is not None:
            try:
                self.process_group_manager.assign_to_process_group(process)
            except Exception as e:
                logger.warning(f"Failed to assign process to process group: {e}")
        # If not initialized yet, it's okay - process will still run
        
    def on_closing(self):
        """Handle window closing - fast cleanup and exit."""
        # Disable the close button to prevent multiple clicks
        try:
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        except:
            pass
        
        # Hide window immediately for better UX
        try:
            self.withdraw()
            self.update()  # Force immediate UI update
        except:
            pass
        
        # Cleanup TTS test panel (fast)
        if hasattr(self, 'tts_test_panel'):
            try:
                self.tts_test_panel.cleanup()
            except Exception:
                pass
        
        # Don't stop the watcher - let it continue running to detect launcher exit
        # and clean up any remaining processes. The watcher will exit automatically
        # after detecting the launcher has died and cleaning up.
        
        # Kill all managed processes immediately (fast, synchronous but quick)
        known_ports = [8000, 8001, 8002, 8003, 8004, 8005, 8006, 4123, 8880]
        
        # Kill managed processes - send kill signal but don't wait
        for service_name, proc in list(self.processes.items()):
            try:
                if proc.poll() is None:
                    # Try graceful termination first (very fast)
                    try:
                        proc.terminate()
                    except:
                        pass
                    # Also kill process tree immediately (non-blocking)
                    try:
                        kill_process_tree(proc.pid)
                    except:
                        pass
            except Exception:
                pass
        
        self.processes.clear()
        
        # Kill processes on ports - do it quickly without waiting
        for port in known_ports:
            try:
                # Just send kill signal, don't wait for verification
                self._kill_process_on_port(port)
            except Exception:
                pass
        
        # Cleanup process group (fast)
        try:
            if hasattr(self, 'process_group_manager') and self.process_group_manager:
                self.process_group_manager.cleanup()
        except Exception:
            pass
        
        # Close window and exit immediately
        # The watcher process will handle any remaining cleanup
        try:
            self.destroy()
        except:
            pass
        
        # Exit immediately - no waiting for processes
        # If processes don't die, the watcher will clean them up
        sys.exit(0)
    
    def _toggle_settings(self, settings_frame, settings_container, toggle_btn, expanded_var):
        """Toggle visibility of settings frame."""
        if expanded_var.get():
            # Hide settings
            settings_container.grid_remove()
            toggle_btn.configure(text="▼ Show")
            expanded_var.set(False)
        else:
            # Show settings
            settings_container.grid()
            toggle_btn.configure(text="▲ Hide")
            expanded_var.set(True)
        # Force layout update
        self.services_frame.update_idletasks()
    
    def _on_splitter_press(self, event):
        """Handle splitter mouse press."""
        self._splitter_dragging = True
        self._splitter_start_y = event.y_root
    
    def _on_splitter_drag(self, event):
        """Handle splitter drag - resize services and console panels."""
        if not self._splitter_dragging:
            return
        
        try:
            # Get window dimensions
            window_height = self.winfo_height()
            window_y = self.winfo_y()
            header_height = 55  # Header is fixed at 55px (reduced from 70)
            splitter_height = 5  # Splitter is 5px
            available_height = window_height - header_height - splitter_height
            
            if available_height <= 100:  # Need at least 100px for both panels
                return
            
            # Calculate mouse position relative to window
            mouse_y = event.y_root - window_y
            
            # Calculate new ratio based on mouse position
            # Mouse position relative to available space (excluding header)
            relative_y = mouse_y - header_height
            
            # Convert to ratio (0.0 = all services, 1.0 = all console)
            new_ratio = relative_y / available_height
            
            # Clamp between 0.1 and 0.9 to keep both panels visible
            new_ratio = max(0.1, min(0.9, new_ratio))
            
            # Only update if significant change (avoid jitter)
            if abs(new_ratio - self._services_height_ratio) > 0.02:
                self._services_height_ratio = new_ratio
                
                # Update row weights to reflect new ratio
                services_weight = self._services_height_ratio
                console_weight = 1.0 - self._services_height_ratio
                
                self.grid_rowconfigure(1, weight=services_weight, minsize=100)
                self.grid_rowconfigure(3, weight=console_weight, minsize=100)
                
                # Force layout update
                self.update_idletasks()
        except Exception as e:
            # Silently handle any errors during drag
            logger.debug(f"Splitter drag error: {e}")
    
    def _on_splitter_release(self, event):
        """Handle splitter mouse release."""
        self._splitter_dragging = False
    
    def _load_chatterbox_settings(self) -> Dict[str, ctk.BooleanVar]:
        """Load Chatterbox settings from config file."""
        default_settings = {
            "enable_prewarm": True
        }
        
        config_file = launcher_dir / "launcher_config.json"
        if config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    chatterbox_config = config.get("chatterbox", {})
                    # Only load enable_prewarm, ignore torch_compile if present
                    if "enable_prewarm" in chatterbox_config:
                        default_settings["enable_prewarm"] = chatterbox_config["enable_prewarm"]
            except Exception as e:
                logger.warning(f"Failed to load launcher config: {e}, using defaults")
        
        return {
            "enable_prewarm": ctk.BooleanVar(value=default_settings.get("enable_prewarm", True))
        }
    
    def _save_chatterbox_settings(self):
        """Save Chatterbox settings to config file."""
        try:
            # Load existing config or create new
            config = {}
            if self.config_file.exists():
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    config = {}
            
            # Update Chatterbox settings
            config["chatterbox"] = {
                "enable_prewarm": self.chatterbox_settings["enable_prewarm"].get()
            }
            
            # Save to file
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save launcher config: {e}")

if __name__ == "__main__":
    # Standard single-instance check using a named mutex (Windows) or lock file (Unix)
    import tempfile
    
    lock_file_path = launcher_dir / ".launcher.lock"
    lock_file = None
    
    def cleanup_lock():
        """Clean up lock file on exit."""
        try:
            if lock_file and not lock_file.closed:
                lock_file.close()
            if lock_file_path.exists():
                lock_file_path.unlink()
        except:
            pass
    
    # Single-instance check
    if platform.system() == "Windows":
        # Windows: Use msvcrt file locking (standard approach)
        try:
            import msvcrt
            lock_file = open(lock_file_path, "w")
            try:
                # Try to acquire exclusive lock (non-blocking)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                # Lock acquired - write PID
                lock_file.write(str(os.getpid()))
                lock_file.flush()
            except IOError:
                # Lock failed - another instance is running
                lock_file.close()
                sys.exit(0)
        except Exception:
            # Fallback: Check if process from lock file is still running
            if lock_file_path.exists():
                try:
                    with open(lock_file_path, "r") as f:
                        pid = int(f.read().strip())
                    # Check if process exists
                    os.kill(pid, 0)
                    # Process exists - exit
                    sys.exit(0)
                except (OSError, ProcessLookupError, ValueError):
                    # Process doesn't exist or invalid PID - remove stale lock
                    try:
                        lock_file_path.unlink()
                    except:
                        pass
            # Create new lock file
            try:
                lock_file = open(lock_file_path, "w")
                lock_file.write(str(os.getpid()))
                lock_file.flush()
            except:
                pass
    else:
        # Unix/Linux: Use fcntl file locking (standard approach)
        try:
            import fcntl
            lock_file = open(lock_file_path, "w")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_file.write(str(os.getpid()))
                lock_file.flush()
            except IOError:
                # Another instance is running
                lock_file.close()
                sys.exit(0)
        except (ImportError, IOError):
            # Fallback: simple file existence check
            if lock_file_path.exists():
                try:
                    with open(lock_file_path, "r") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 0)
                    sys.exit(0)
                except (OSError, ProcessLookupError, ValueError):
                    try:
                        lock_file_path.unlink()
                    except:
                        pass
            try:
                lock_file = open(lock_file_path, "w")
                lock_file.write(str(os.getpid()))
                lock_file.flush()
            except:
                pass
    
    # Register cleanup on exit
    atexit.register(cleanup_lock)
    
    # Main application
    try:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        app = App()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
        
        cleanup_lock()
    except Exception as e:
        import traceback
        error_msg = f"Failed to start launcher: {e}\n\nTraceback:\n{traceback.format_exc()}\n\nLauncher directory: {launcher_dir}\nPID: {os.getpid()}"
        
        # Write error to log file
        try:
            error_log = launcher_dir / "launcher_error.log"
            with open(error_log, "w", encoding="utf-8") as f:
                f.write(error_msg)
        except:
            # Fallback to temp directory
            try:
                temp_log = Path(tempfile.gettempdir()) / "launcher_error.log"
                with open(temp_log, "w", encoding="utf-8") as f:
                    f.write(f"{error_msg}\n\nOriginal log path: {launcher_dir / 'launcher_error.log'}")
            except:
                pass
        
        cleanup_lock()
        sys.exit(1)
