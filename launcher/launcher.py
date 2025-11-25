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
    # Fallback mock for development if manager.py is missing/broken
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

# Configure logging
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

        self.title("Personal Assistant Manager")
        self.geometry("1100x800")
        self.minsize(900, 600)
        
        # Initialize Service Manager
        self.service_manager = ServiceManager()
        self.processes: Dict[str, subprocess.Popen] = {}
        
        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="AI Assistant", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.install_all_btn = ctk.CTkButton(self.sidebar_frame, text="Install All", command=self.install_all_services)
        self.install_all_btn.grid(row=1, column=0, padx=20, pady=10)

        self.start_all_btn = ctk.CTkButton(self.sidebar_frame, text="Start All", command=self.start_all_services, fg_color="green")
        self.start_all_btn.grid(row=2, column=0, padx=20, pady=10)
        
        self.stop_all_btn = ctk.CTkButton(self.sidebar_frame, text="Stop All", command=self.stop_all_services, fg_color="red")
        self.stop_all_btn.grid(row=3, column=0, padx=20, pady=10)

        self.open_web_btn = ctk.CTkButton(self.sidebar_frame, text="Open Web UI", command=self.open_web_ui)
        self.open_web_btn.grid(row=4, column=0, padx=20, pady=10)

        # Service Options - create checkboxes for optional services
        self.options_label = ctk.CTkLabel(self.sidebar_frame, text="Service Options", font=ctk.CTkFont(size=14, weight="bold"))
        self.options_label.grid(row=5, column=0, padx=20, pady=(20, 10))
        
        self.service_vars = {}
        row_idx = 6
        # Dynamically create checkboxes for all services
        for svc_name, svc_info in self.service_manager.services.items():
            is_optional = svc_info.get("optional", False)
            
            var = ctk.BooleanVar(value=True) # Default enabled
            self.service_vars[svc_name] = var
            
            if is_optional:
                chk = ctk.CTkCheckBox(self.sidebar_frame, text=svc_info["name"], variable=var)
                chk.grid(row=row_idx, column=0, padx=20, pady=5, sticky="w")
            else:
                # Core services always enabled and visible but disabled
                chk = ctk.CTkCheckBox(self.sidebar_frame, text=svc_info["name"], variable=var, state="disabled")
                chk.grid(row=row_idx, column=0, padx=20, pady=5, sticky="w")
            
            row_idx += 1

        # Main Content
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Service Status Cards - Scrollable to save space for logs
        self.status_frame = ctk.CTkScrollableFrame(self.main_frame, height=250, label_text="Service Status")
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.status_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.services_ui = {}
        # Get all services from service manager
        services = list(self.service_manager.services.keys())
        
        # Grid layout: 3 columns
        for i, svc in enumerate(services):
            row = i // 3
            col = i % 3
            frame = ctk.CTkFrame(self.status_frame)
            frame.grid(row=row, column=col, padx=10, pady=10, sticky="ew")
            
            # Title
            name_lbl = ctk.CTkLabel(frame, text=svc.upper(), font=ctk.CTkFont(weight="bold"))
            name_lbl.pack(pady=(10, 5))
            
            # Status
            status_lbl = ctk.CTkLabel(frame, text="STOPPED", text_color="red")
            status_lbl.pack(pady=5)
            
            # Controls Frame
            controls = ctk.CTkFrame(frame, fg_color="transparent")
            controls.pack(pady=10, padx=10)
            
            # Start/Stop Button
            btn = ctk.CTkButton(controls, text="Start", width=80, command=lambda s=svc: self.toggle_service(s))
            btn.grid(row=0, column=0, padx=5, pady=5)
            
            # Install Button
            install_btn = ctk.CTkButton(controls, text="Install", width=80, command=lambda s=svc: self.install_service(s))
            install_btn.grid(row=1, column=0, padx=5, pady=5)
            
            self.services_ui[svc] = {
                "status_lbl": status_lbl, 
                "btn": btn, 
                "install_btn": install_btn,
                "frame": frame
            }

        # Console Output with Tabs
        self.console_frame = ctk.CTkFrame(self.main_frame)
        self.console_frame.grid(row=1, column=0, sticky="nsew")
        self.console_frame.grid_columnconfigure(0, weight=1)
        self.console_frame.grid_rowconfigure(0, weight=1)

        self.log_tabview = ctk.CTkTabview(self.console_frame)
        self.log_tabview.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Create tabs for each service + main log
        self.log_tabs = {}
        self.log_tabs["main"] = self.log_tabview.add("Main")
        main_tab = self.log_tabs["main"]
        main_log = ctk.CTkTextbox(main_tab, state="disabled", font=("Consolas", 10))
        main_log.pack(fill="both", expand=True)
        self.log_tabs["main_textbox"] = main_log
        
        for svc_name in services:
            tab = self.log_tabview.add(svc_name.upper())
            textbox = ctk.CTkTextbox(tab, state="disabled", font=("Consolas", 10))
            textbox.pack(fill="both", expand=True)
            self.log_tabs[svc_name] = textbox
        
        # Redirect stdout/stderr to main tab
        sys.stdout = ConsoleRedirector(main_log)
        sys.stderr = ConsoleRedirector(main_log)
        
        print("Welcome to AI Assistant Manager")
        print("Ready to manage services...")

    def install_service(self, service_name):
        def _run():
            self.services_ui[service_name]["install_btn"].configure(state="disabled")
            print(f"\n--- Installing {service_name} ---\n", flush=True)
            try:
                # Get install command from manager
                svc_info = self.service_manager.services.get(service_name)
                if not svc_info:
                    print(f"Unknown service: {service_name}", flush=True)
                    return
                
                cmd = svc_info["install_cmd"]()
                if not cmd:
                    print(f"No install command for {service_name}", flush=True)
                    self.services_ui[service_name]["install_btn"].configure(state="normal")
                    return
                
                cwd = svc_info["dir"]
                
                # Run installation with output capture
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    shell=True if platform.system() == "Windows" else False
                )
                
                # Read and print output line by line
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                for line in iter(process.stdout.readline, ''):
                    clean_line = ansi_escape.sub('', line).strip()
                    if clean_line:
                        # Write to both main log and service-specific log
                        print(clean_line, flush=True)
                        if service_name in self.log_tabs:
                            service_log = self.log_tabs[service_name]
                            service_log.configure(state="normal")
                            service_log.insert("end", clean_line + "\n")
                            service_log.see("end")
                            service_log.configure(state="disabled")
                
                # Wait for completion
                return_code = process.wait()
                
                if return_code == 0:
                    print(f"\n--- {service_name} Installed Successfully ---\n", flush=True)
                else:
                    print(f"\n--- {service_name} Installation Failed (Exit code: {return_code}) ---\n", flush=True)
            except Exception as e:
                print(f"Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                self.services_ui[service_name]["install_btn"].configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def install_all_services(self):
        def _run():
            self.install_all_btn.configure(state="disabled")
            print("\n--- Installing All Enabled Services ---\n")
            
            for svc_name, ui in self.services_ui.items():
                if self.service_vars[svc_name].get():
                    self.install_service(svc_name)
                    # Wait a bit between installs?
                    time.sleep(1)
            
            self.install_all_btn.configure(state="normal")
            print("\n--- All Installations Completed ---\n")
        
        threading.Thread(target=_run, daemon=True).start()

    def start_all_services(self):
        def _run():
            self.start_all_btn.configure(state="disabled")
            for svc_name, ui in self.services_ui.items():
                if self.service_vars[svc_name].get():
                    # Check if already running
                    if self.service_manager.service_status.get(svc_name) != ServiceStatus.RUNNING:
                        self.toggle_service(svc_name)
                        time.sleep(2) # Stagger starts
            self.start_all_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()

    def toggle_service(self, service_name):
        current_text = self.services_ui[service_name]["btn"].cget("text")
        if current_text == "Start":
            self.start_service(service_name)
        else:
            self.stop_service(service_name)

    def start_service(self, service_name):
        def _run():
            print(f"Starting {service_name}...")
            # Use yellow for starting status
            self.update_service_ui(service_name, "STARTING", "#FFD700") # Gold/Yellow
            
            try:
                # Get command from manager
                svc_info = self.service_manager.services.get(service_name)
                if not svc_info:
                    print(f"Unknown service: {service_name}")
                    return

                cmd = svc_info["start_cmd"]()
                cwd = svc_info["dir"]
                
                # Start process
                # We use Popen to keep it running
                # On Windows, we might want creationflags=subprocess.CREATE_NEW_CONSOLE if we want separate windows
                # But user asked for GUI, so maybe keep hidden or pipe output?
                # Let's pipe output to our console
                
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                self.processes[service_name] = process
                
                # Start health check thread
                threading.Thread(target=self.wait_for_service, args=(service_name,), daemon=True).start()
                
                # Read output in a separate thread
                def read_output():
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    for line in iter(process.stdout.readline, ''):
                        clean_line = ansi_escape.sub('', line).strip()
                        if clean_line:
                            # Write to both main log and service-specific log
                            print(f"[{service_name}] {clean_line}")
                            if service_name in self.log_tabs:
                                service_log = self.log_tabs[service_name]
                                service_log.configure(state="normal")
                                service_log.insert("end", clean_line + "\n")
                                service_log.see("end")
                                service_log.configure(state="disabled")
                    process.stdout.close()
                    
                    # If we get here, process died

                    if self.processes.get(service_name) == process:
                        print(f"{service_name} stopped unexpectedly.")
                        self.update_service_ui(service_name, "STOPPED", "red", "Start")
                        del self.processes[service_name]

                threading.Thread(target=read_output, daemon=True).start()
                
            except Exception as e:
                print(f"Error starting {service_name}: {e}")
                self.update_service_ui(service_name, "ERROR", "red", "Start")
        
        threading.Thread(target=_run, daemon=True).start()

    def wait_for_service(self, service_name):
        """Wait for service to become healthy."""
        svc_info = self.service_manager.services.get(service_name)
        if not svc_info:
            return

        url = svc_info.get("url")
        health_endpoint = svc_info.get("health_endpoint")
        
        # Max wait time: 30 seconds
        for _ in range(30):
            # Check if process died
            if service_name not in self.processes or self.processes[service_name].poll() is not None:
                return # read_output will handle UI update
            
            try:
                # If health endpoint exists, check it
                if health_endpoint:
                    check_url = f"{url}{health_endpoint}"
                    with urllib.request.urlopen(check_url, timeout=1) as response:
                        if response.status == 200:
                            self.update_service_ui(service_name, "RUNNING", "green", "Stop")
                            return
                else:
                    # Just check if port is open (for frontend)
                    parsed = urllib.parse.urlparse(url)
                    host = parsed.hostname or "localhost"
                    port = parsed.port or 80
                    with socket.create_connection((host, port), timeout=1):
                        self.update_service_ui(service_name, "RUNNING", "green", "Stop")
                        return
            except (urllib.error.URLError, socket.error, socket.timeout):
                pass
            
            time.sleep(1)
        
        # Timeout - assume running if process is still alive, or keep as STARTING?
        # If it's still starting after 30s, maybe just set to RUNNING with warning?
        # Or leave as STARTING?
        # Let's set to RUNNING if process is alive, user can check logs
        if service_name in self.processes and self.processes[service_name].poll() is None:
             self.update_service_ui(service_name, "RUNNING", "green", "Stop")

    def stop_service(self, service_name):
        print(f"Stopping {service_name}...")
        proc = self.processes.get(service_name)
        if proc:
            # Try graceful terminate first
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            
            if service_name in self.processes:
                del self.processes[service_name]
        
        self.update_service_ui(service_name, "STOPPED", "red", "Start")

    def stop_all_services(self):
        for svc in list(self.processes.keys()):
            self.stop_service(svc)

    def update_service_ui(self, service_name, status, color, btn_text=None):
        self.services_ui[service_name]["status_lbl"].configure(text=status, text_color=color)
        if btn_text:
            self.services_ui[service_name]["btn"].configure(text=btn_text)

    def open_web_ui(self):
        webbrowser.open("http://localhost:3000")

    def on_closing(self):
        self.stop_all_services()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
