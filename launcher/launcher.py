import customtkinter as ctk
import sys
import os
import threading
import time
import subprocess
import platform
import webbrowser
import re
from pathlib import Path
from typing import Optional, Dict
import logging
import urllib.request
import urllib.error
import urllib.parse
import socket

# Add current directory to path to import manager
sys.path.append(str(Path(__file__).parent.resolve()))

try:
    from manager import ServiceManager, ServiceStatus
except ImportError:
    class ServiceManager:
        def __init__(self, root_dir=None):
            self.root_dir = root_dir or Path.cwd()
            self.services = {
                "backend": {"name": "Backend API", "port": 8000, "url": "http://localhost:8000"},
                "frontend": {"name": "Frontend", "port": 3000, "url": "http://localhost:3000"},
                "kokoro": {"name": "Kokoro TTS", "port": 8880, "url": "http://localhost:8880"}
            }
            self.service_status = {k: "stopped" for k in self.services}
        
        def check_dependencies(self):
            return {"venv": True, "backend_deps": True}
            
        def install_dependencies(self, **kwargs):
            time.sleep(2)
            return True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Launcher")

class ConsoleRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = []
        self.update_pending = False

    def write(self, str_val):
        self.queue.append(str_val)
        if not self.update_pending:
            self.update_pending = True
            self.text_widget.after(100, self.update_widget)

    def flush(self):
        pass

    def update_widget(self):
        if self.queue:
            text = "".join(self.queue)
            self.queue = []
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", text)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        self.update_pending = False

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
        # WINDOW SETUP
        # ============================================
        self.title("Personal Assistant Manager")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        
        ctk.set_appearance_mode("Dark")
        self.configure(fg_color=self.colors["bg_main"])
        
        # Initialize
        self.service_manager = ServiceManager()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.services_ui = {}
        self.service_vars = {}
        
        # ============================================
        # MAIN LAYOUT - SIMPLE 3 ROW DESIGN
        # ============================================
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Services row expands
        self.grid_rowconfigure(2, weight=1)  # Console row expands
        
        # ============================================
        # ROW 0: HEADER WITH BUTTONS
        # ============================================
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], height=70, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        
        # Title
        title = ctk.CTkLabel(
            header,
            text="Personal Assistant Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        # Buttons
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=20, pady=15, sticky="e")
        
        self.install_all_btn = ctk.CTkButton(btn_frame, text="Install All", command=self.install_all_services, width=100, height=32)
        self.install_all_btn.grid(row=0, column=0, padx=5)
        
        self.reinstall_all_btn = ctk.CTkButton(btn_frame, text="Reinstall All", command=self.reinstall_all_services, width=100, height=32, fg_color=self.colors["accent_orange"], hover_color="#E67E00")
        self.reinstall_all_btn.grid(row=0, column=1, padx=5)
        
        self.start_all_btn = ctk.CTkButton(btn_frame, text="Start All", command=self.start_all_services, width=100, height=32, fg_color=self.colors["accent_green"], hover_color="#0E6B0E")
        self.start_all_btn.grid(row=0, column=2, padx=5)
        
        self.stop_all_btn = ctk.CTkButton(btn_frame, text="Stop All", command=self.stop_all_services, width=100, height=32, fg_color=self.colors["accent_red"], hover_color="#B02A2E")
        self.stop_all_btn.grid(row=0, column=3, padx=5)
        
        self.open_web_btn = ctk.CTkButton(btn_frame, text="Open Web UI", command=self.open_web_ui, width=100, height=32, fg_color=self.colors["accent_blue"], hover_color="#0063B1")
        self.open_web_btn.grid(row=0, column=4, padx=5)
        
        self.reset_app_btn = ctk.CTkButton(btn_frame, text="Reset State", command=self.reset_app_state, width=100, height=32, fg_color=self.colors["accent_orange"], hover_color="#E67E00")
        self.reset_app_btn.grid(row=0, column=5, padx=5)
        
        # ============================================
        # ROW 1: SERVICES LIST - SIMPLE SCROLLABLE TABLE
        # ============================================
        services_panel = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], corner_radius=0)
        services_panel.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        services_panel.grid_columnconfigure(0, weight=1)
        services_panel.grid_rowconfigure(1, weight=1)
        
        # Services title
        services_title = ctk.CTkLabel(
            services_panel,
            text="Services",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        services_title.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        # Scrollable frame for services
        self.services_frame = ctk.CTkScrollableFrame(
            services_panel,
            fg_color=self.colors["bg_panel"],
            corner_radius=0
        )
        self.services_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Configure columns in scrollable frame - FIXED SIZES, NO WEIGHT
        # Total width: 50 + 300 + 200 + 200 + 900 = 1650px
        self.services_frame.grid_columnconfigure(0, minsize=50, weight=0)   # Checkbox
        self.services_frame.grid_columnconfigure(1, minsize=300, weight=0) # Service name (WIDER)
        self.services_frame.grid_columnconfigure(2, minsize=200, weight=0) # Install status
        self.services_frame.grid_columnconfigure(3, minsize=200, weight=0) # Running status
        self.services_frame.grid_columnconfigure(4, minsize=900, weight=0) # Actions (WIDER)
        
        # Create service rows
        services = list(self.service_manager.services.keys())
        for i, svc in enumerate(services):
            self._create_service_row(svc, i)
        
        # ============================================
        # ROW 2: CONSOLE - CLEAN TABBED INTERFACE
        # ============================================
        console_panel = ctk.CTkFrame(self, fg_color=self.colors["bg_panel"], corner_radius=0)
        console_panel.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        console_panel.grid_columnconfigure(0, weight=1)
        console_panel.grid_rowconfigure(1, weight=1)
        
        # Console title
        console_title = ctk.CTkLabel(
            console_panel,
            text="Console Output",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        console_title.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        # Tabs
        self.log_tabview = ctk.CTkTabview(console_panel, fg_color=self.colors["bg_card"], corner_radius=5)
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
        
        # Service tabs
        for svc_name in services:
            tab = self.log_tabview.add(svc_name.upper())
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
        
        # Redirect output
        sys.stdout = ConsoleRedirector(all_log)
        sys.stderr = ConsoleRedirector(all_log)
        
        # Initial messages
        self.log_to_launcher("Welcome to Personal Assistant Manager")
        self.log_to_launcher("Ready to manage services...")
        print("Welcome to Personal Assistant Manager")
        print("Ready to manage services...")
        
        # Refresh statuses
        self.after(100, self.refresh_all_service_statuses)
        self._start_periodic_status_refresh()
    
    def _create_service_row(self, svc: str, row_index: int):
        """Create a service row with all elements visible and properly sized."""
        svc_info = self.service_manager.services.get(svc)
        is_gateway_managed = (svc == "llm")
        is_installed = self._check_service_installed(svc, svc_info)
        is_running = svc in self.processes and self.processes[svc].poll() is None
        
        # Row frame - let it size naturally
        row = ctk.CTkFrame(
            self.services_frame,
            fg_color=self.colors["bg_card"],
            corner_radius=5
        )
        row.grid(row=row_index, column=0, sticky="ew", padx=5, pady=5)
        
        # Configure columns - EXACTLY match scrollable frame
        row.grid_columnconfigure(0, minsize=50, weight=0)
        row.grid_columnconfigure(1, minsize=300, weight=0)
        row.grid_columnconfigure(2, minsize=200, weight=0)
        row.grid_columnconfigure(3, minsize=200, weight=0)
        row.grid_columnconfigure(4, minsize=900, weight=0)
        
        # Checkbox - Column 0
        var = ctk.BooleanVar(value=True)
        self.service_vars[svc] = var
        checkbox = ctk.CTkCheckBox(row, text="", variable=var)
        checkbox.grid(row=0, column=0, padx=10, pady=15, sticky="w")
        
        # Service name - Column 1 - FULL TEXT VISIBLE
        service_name_text = svc_info.get("name", svc.upper())
        name_label = ctk.CTkLabel(
            row,
            text=service_name_text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.colors["text_primary"],
            anchor="w",
            width=300  # Full column width
        )
        name_label.grid(row=0, column=1, padx=15, pady=15, sticky="w")
        
        # Install status - Column 2
        if is_gateway_managed:
            install_text = "READY"
            install_color = self.colors["accent_green"]
        elif is_installed:
            install_text = "✓ Installed"
            install_color = self.colors["accent_green"]
        else:
            install_text = "✗ Not Installed"
            install_color = self.colors["accent_orange"]
        
        install_label = ctk.CTkLabel(
            row,
            text=install_text,
            font=ctk.CTkFont(size=13),
            text_color=install_color,
            anchor="w",
            width=200
        )
        install_label.grid(row=0, column=2, padx=15, pady=15, sticky="w")
        
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
            font=ctk.CTkFont(size=13),
            text_color=running_color,
            anchor="w",
            width=200
        )
        running_label.grid(row=0, column=3, padx=15, pady=15, sticky="w")
        
        # Actions frame - Column 4 - ALL BUTTONS VISIBLE
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=4, padx=15, pady=15, sticky="w")
        
        # Build button (frontend only)
        build_btn = None
        if svc == "frontend":
            build_btn = ctk.CTkButton(
                actions,
                text="Build",
                width=95,
                height=35,
                font=ctk.CTkFont(size=12),
                fg_color=self.colors["accent_blue"],
                hover_color="#0063B1",
                command=lambda s=svc: self.rebuild_frontend(s)
            )
            build_btn.grid(row=0, column=0, padx=5)
        
        # Reinstall button
        reinstall_btn = ctk.CTkButton(
            actions,
            text="Reinstall",
            width=105,
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=self.colors["accent_orange"],
            hover_color="#E67E00",
            command=lambda s=svc: self.install_service(s, force_reinstall=True)
        )
        reinstall_btn.grid(row=0, column=1, padx=5)
        
        # Install button
        install_btn = ctk.CTkButton(
            actions,
            text="Install",
            width=95,
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=self.colors["accent_blue"],
            hover_color="#0063B1",
            command=lambda s=svc: self.install_service(s, force_reinstall=False)
        )
        install_btn.grid(row=0, column=2, padx=5)
        
        # Start button
        start_btn = ctk.CTkButton(
            actions,
            text="Start",
            width=85,
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=self.colors["accent_green"],
            hover_color="#0E6B0E",
            command=lambda s=svc: self.toggle_service(s),
            state="disabled" if is_gateway_managed else "normal"
        )
        start_btn.grid(row=0, column=3, padx=5)
        
        # Stop button
        stop_btn = ctk.CTkButton(
            actions,
            text="Stop",
            width=85,
            height=35,
            font=ctk.CTkFont(size=12),
            fg_color=self.colors["accent_red"],
            hover_color="#B02A2E",
            command=lambda s=svc: self.stop_service(s),
            state="disabled" if is_gateway_managed else "normal"
        )
        stop_btn.grid(row=0, column=4, padx=5)
        
        # Store UI elements
        self.services_ui[svc] = {
            "install_status": install_label,
            "running_status": running_label,
            "build_btn": build_btn,
            "reinstall_btn": reinstall_btn,
            "install_btn": install_btn,
            "start_btn": start_btn,
            "stop_btn": stop_btn,
            "row_frame": row
        }

    def log_to_launcher(self, message):
        """Log a message to the launcher tab only."""
        launcher_log = self.log_tabs.get("launcher_textbox")
        if launcher_log:
            launcher_log.configure(state="normal")
            launcher_log.insert("end", f"{message}\n")
            launcher_log.see("end")
            launcher_log.configure(state="disabled")
    
    def log_to_service(self, service_name: str, message: str):
        """Log a message to a service-specific tab (thread-safe)."""
        def _update():
            service_log = self.log_tabs.get(service_name)
            if service_log:
                service_log.configure(state="normal")
                service_log.insert("end", message + "\n")
                service_log.see("end")
                service_log.configure(state="disabled")
        self.after(0, _update)

    def install_service(self, service_name, blocking=False, force_reinstall=False):
        """Install a single service."""
        def _run():
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
                
                if not force_reinstall:
                    is_installed = self._check_service_installed(service_name, svc_info)
                    if is_installed:
                        skip_msg = f"{service_name} is already installed. Skipping installation."
                        self.log_to_service(service_name, skip_msg)
                        self.log_to_launcher(f"[INSTALL] SKIP: {service_name} (already installed)")
                        return (True, f"{service_name} already installed")
                else:
                    self.log_to_service(service_name, f"Force reinstalling {service_name}...")
                    self.log_to_launcher(f"[INSTALL] FORCE REINSTALL: {service_name}")
                
                if force_reinstall and service_name != "frontend":
                    import shutil
                    venv_path = svc_info.get("venv")
                    if venv_path and venv_path.exists():
                        self.log_to_service(service_name, "Removing existing venv for force reinstall...")
                        self.log_to_launcher(f"[INSTALL] Removing venv for {service_name}...")
                        try:
                            shutil.rmtree(str(venv_path), ignore_errors=True)
                            time.sleep(1)
                        except Exception as e:
                            self.log_to_service(service_name, f"Warning: Could not remove venv: {e}")
                
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
                
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    shell=use_shell,
                    creationflags=creation_flags
                )
                
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                for line in iter(process.stdout.readline, ''):
                    if not line:
                        break
                    clean_line = ansi_escape.sub('', line).rstrip()
                    if clean_line:
                        self.log_to_service(service_name, clean_line)
                        if any(keyword in clean_line.lower() for keyword in ['error', 'warning', 'success', 'installing', 'upgrading', 'creating', 'removing']):
                            self.log_to_launcher(f"[{service_name}] {clean_line}")
                
                return_code = process.wait()
                
                if return_code == 0:
                    success = True
                    result_msg = f"{service_name} installed successfully"
                    msg = f"\n--- {service_name} Installed Successfully ---\n"
                    self.log_to_service(service_name, msg)
                    self.log_to_launcher(f"[INSTALL] SUCCESS: {service_name}")
                    self.after(0, lambda: self._update_install_status(service_name))
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
                rebuild_btn = self.services_ui[service_name].get("rebuild_btn")
                if rebuild_btn:
                    rebuild_btn.configure(state="normal")
            
            return (success, result_msg)
        
        if blocking:
            return _run()
        else:
            threading.Thread(target=_run, daemon=True).start()
            return None
    
    def rebuild_frontend(self, service_name: str = "frontend"):
        """Force rebuild the frontend service."""
        def _run():
            self.log_to_launcher(f"\n--- Rebuilding {service_name} (Force Reinstall) ---")
            
            if service_name in self.services_ui:
                rebuild_btn = self.services_ui[service_name].get("rebuild_btn")
                if rebuild_btn:
                    rebuild_btn.configure(state="disabled")
            
            if service_name in self.processes:
                self.log_to_launcher(f"[REBUILD] Stopping {service_name} before rebuild...")
                self.stop_service(service_name)
                time.sleep(2)
            
            self.log_to_launcher(f"[REBUILD] Force rebuilding {service_name}...")
            result = self.install_service(service_name, blocking=True, force_reinstall=True)
            
            if result:
                success, msg = result
                if success:
                    self.log_to_launcher(f"[REBUILD] SUCCESS: {service_name} rebuilt successfully")
                    self.after(0, lambda: self._update_install_status(service_name))
                else:
                    self.log_to_launcher(f"[REBUILD] FAILED: {service_name} - {msg}")
            else:
                self.log_to_launcher(f"[REBUILD] FAILED: {service_name} - installation returned None")
        
        threading.Thread(target=_run, daemon=True).start()

    def install_all_services(self):
        """Install all enabled services."""
        def _run():
            self.install_all_btn.configure(state="disabled")
            
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
            
            results = {"success": [], "failed": [], "skipped": []}
            
            for idx, svc_name in enumerate(services_to_install, 1):
                progress_msg = f"\n[{idx}/{len(services_to_install)}] Installing {svc_name}..."
                print(progress_msg)
                self.log_to_launcher(progress_msg)
                
                try:
                    result = self.install_service(svc_name, blocking=True, force_reinstall=False)
                    if result:
                        success, msg = result
                        if success:
                            results["success"].append(svc_name)
                        else:
                            results["failed"].append((svc_name, msg))
                    else:
                        results["skipped"].append(svc_name)
                except Exception as e:
                    results["failed"].append((svc_name, str(e)))
            
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
            
            self.install_all_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def reinstall_all_services(self):
        """Force reinstall all enabled services."""
        def _run():
            self.reinstall_all_btn.configure(state="disabled")
            
            header = "\n" + "="*60 + "\n"
            header += "       REINSTALLING ALL ENABLED SERVICES\n"
            header += "="*60 + "\n"
            print(header)
            self.log_to_launcher(header)
            
            services_to_reinstall = []
            for svc_name in self.services_ui.keys():
                if self.service_vars.get(svc_name, ctk.BooleanVar(value=False)).get():
                    services_to_reinstall.append(svc_name)
            
            self.log_to_launcher(f"Services to reinstall: {', '.join(services_to_reinstall)}")
            
            results = {"success": [], "failed": []}
            
            for idx, svc_name in enumerate(services_to_reinstall, 1):
                progress_msg = f"\n[{idx}/{len(services_to_reinstall)}] Reinstalling {svc_name}..."
                print(progress_msg)
                self.log_to_launcher(progress_msg)
                
                if svc_name in self.processes:
                    self.log_to_launcher(f"[REINSTALL] Stopping {svc_name} before reinstall...")
                    self.stop_service(svc_name)
                    time.sleep(2)
                
                try:
                    result = self.install_service(svc_name, blocking=True, force_reinstall=True)
                    if result:
                        success, msg = result
                        if success:
                            results["success"].append(svc_name)
                        else:
                            results["failed"].append((svc_name, msg))
                    else:
                        results["failed"].append((svc_name, "Installation returned None"))
                except Exception as e:
                    results["failed"].append((svc_name, str(e)))
            
            summary = "\n" + "="*60 + "\n"
            summary += "       REINSTALLATION SUMMARY\n"
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
            
            total = len(services_to_reinstall)
            success_count = len(results["success"])
            failed_count = len(results["failed"])
            
            if failed_count == 0:
                summary += f"✓ All {success_count} services reinstalled successfully!\n"
            else:
                summary += f"⚠ {success_count}/{total} services reinstalled, {failed_count} failed\n"
            
            summary += "="*60 + "\n"
            
            print(summary)
            self.log_to_launcher(summary)
            
            self.reinstall_all_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def start_all_services(self):
        def _run():
            self.start_all_btn.configure(state="disabled")
            
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
                self.start_all_btn.configure(state="normal")
                return
            
            started_count = 0
            skipped_count = 0
            
            for svc_name in enabled_services:
                is_gateway_managed = (svc_name == "llm")
                if is_gateway_managed:
                    self.log_to_launcher(f"{svc_name} is managed by Gateway (skipping)")
                    skipped_count += 1
                    continue
                
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
            self.start_all_btn.configure(state="normal")
        
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

                cmd = svc_info["start_cmd"]()
                cwd = svc_info["dir"]
                
                is_installed = self._check_service_installed(service_name, svc_info)
                if not is_installed:
                    needs_reinstall = self._check_if_needs_reinstall(service_name)
                    if needs_reinstall:
                        msg = f"{service_name} has missing dependencies. Click 'Reinstall' to repair."
                    else:
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
                if platform.system() == "Windows":
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    universal_newlines=True,
                    creationflags=creation_flags
                )
                
                self.processes[service_name] = process
                
                threading.Thread(target=self.wait_for_service, args=(service_name,), daemon=True).start()
                
                def read_output():
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    for line in iter(process.stdout.readline, ''):
                        clean_line = ansi_escape.sub('', line).strip()
                        if clean_line:
                            print(f"[{service_name}] {clean_line}")
                            self.log_to_service(service_name, clean_line)
                    process.stdout.close()
                    
                    if self.processes.get(service_name) == process:
                        needs_reinstall = self._check_if_needs_reinstall(service_name)
                        msg = f"{service_name} stopped unexpectedly."
                        if needs_reinstall:
                            msg += " Missing dependencies detected - click 'Reinstall' to repair."
                        print(msg)
                        self.log_to_service(service_name, msg)
                        self.log_to_launcher(f"[{service_name}] {msg}")
                        self._update_running_status(service_name)
                        del self.processes[service_name]

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
                            self.after(0, lambda: self._update_running_status(service_name))
                            self.log_to_launcher(f"[{service_name}] Service is now RUNNING")
                            return
                else:
                    parsed = urllib.parse.urlparse(url)
                    host = parsed.hostname or "localhost"
                    port = parsed.port or 80
                    with socket.create_connection((host, port), timeout=1):
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
        
        if proc:
            try:
                if platform.system() == "Windows":
                    print(f"  Sending shutdown signal to {service_name}...")
                    proc.terminate()
                else:
                    import signal
                    print(f"  Sending SIGINT to {service_name}...")
                    proc.send_signal(signal.SIGINT)
                
                print(f"  Waiting for {service_name} to shut down gracefully...")
                try:
                    proc.wait(timeout=10)
                    print(f"  {service_name} shut down gracefully")
                except subprocess.TimeoutExpired:
                    print(f"  {service_name} did not shut down gracefully, force killing...")
                    proc.kill()
                    try:
                        proc.wait(timeout=3)
                        msg = f"{service_name} force killed"
                        print(f"  {msg}")
                        self.log_to_launcher(f"[{service_name}] {msg}")
                    except subprocess.TimeoutExpired:
                        print(f"  Warning: {service_name} process may still be running")
            except Exception as e:
                print(f"  Error during shutdown: {e}")
            
            if service_name in self.processes:
                del self.processes[service_name]
        
        self.after(0, lambda: self._update_running_status(service_name))
        self.log_to_launcher(f"[{service_name}] Service stopped")

    def stop_all_services(self):
        def _run():
            self.stop_all_btn.configure(state="disabled")
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
            self.stop_all_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def _check_service_installed(self, service_name: str, svc_info: Optional[Dict]) -> bool:
        """Check if a service is properly installed."""
        if not svc_info:
            return False
        
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
        
        try:
            result = subprocess.run(
                [str(python_exe), "--version"],
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            return result.returncode == 0
        except Exception:
            return True
    
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
        for service_name in self.services_ui.keys():
            self._update_install_status(service_name)
            self._update_running_status(service_name)
    
    def _start_periodic_status_refresh(self):
        """Start periodic status refresh."""
        for service_name in self.services_ui.keys():
            self._update_running_status(service_name)
        
        self.after(2000, self._start_periodic_status_refresh)
    
    def _update_install_status(self, service_name):
        """Update service UI status based on installation state."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            return
        
        is_gateway_managed = False
        if service_name == "llm":
            is_gateway_managed = True
        
        install_label = self.services_ui[service_name].get("install_status")
        if not install_label:
            return
        
        if is_gateway_managed:
            install_label.configure(text="READY", text_color=self.colors["accent_green"])
        else:
            is_installed = self._check_service_installed(service_name, svc_info)
            if is_installed:
                install_label.configure(text="✓ Installed", text_color=self.colors["accent_green"])
            else:
                install_label.configure(text="✗ Not Installed", text_color=self.colors["accent_orange"])
    
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
                url = svc_info.get("url")
                health_endpoint = svc_info.get("health_endpoint")
                
                def check_health():
                    try:
                        is_healthy = False
                        if health_endpoint:
                            check_url = f"{url}{health_endpoint}"
                            with urllib.request.urlopen(check_url, timeout=0.5) as response:
                                if response.status == 200:
                                    is_healthy = True
                        else:
                            parsed = urllib.parse.urlparse(url)
                            host = parsed.hostname or "localhost"
                            port = parsed.port or 80
                            with socket.create_connection((host, port), timeout=0.5):
                                is_healthy = True
                        
                        if is_healthy:
                            self.after(0, lambda lbl=running_label: lbl.configure(text="● Running", text_color=self.colors["accent_green"]))
                            if start_btn and stop_btn:
                                self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                        else:
                            self.after(0, lambda lbl=running_label: lbl.configure(text="⏳ Starting", text_color=self.colors["accent_orange"]))
                            if start_btn and stop_btn:
                                self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                    except (urllib.error.URLError, socket.error, socket.timeout, Exception):
                        self.after(0, lambda lbl=running_label: lbl.configure(text="⏳ Starting", text_color=self.colors["accent_orange"]))
                        if start_btn and stop_btn:
                            self.after(0, lambda sb=start_btn, stb=stop_btn: (sb.configure(state="disabled", text="Start"), stb.configure(state="normal")))
                
                threading.Thread(target=check_health, daemon=True).start()
                running_label.configure(text="⏳ Starting", text_color=self.colors["accent_orange"])
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
        webbrowser.open("http://localhost:3000")
    
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

    def on_closing(self):
        """Handle window closing - close immediately, cleanup in background."""
        # Close window immediately - don't block UI
        self.destroy()
        
        # Do cleanup in background thread (non-blocking)
        def cleanup():
            try:
                # Kill managed processes quickly
                for service_name, proc in list(self.processes.items()):
                    try:
                        if proc.poll() is None:
                            proc.kill()
                            # Don't wait - just kill and move on
                    except Exception:
                        pass
                
                self.processes.clear()
            except Exception:
                pass
        
        # Start cleanup in background and exit
        threading.Thread(target=cleanup, daemon=True).start()
        sys.exit(0)

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
