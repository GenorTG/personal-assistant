"""Service row UI component for GTK4."""
import sys
from pathlib import Path

# Add launcher directory to path
launcher_dir = Path(__file__).parent.parent
sys.path.insert(0, str(launcher_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

from service_manager import ServiceManager


class ServiceRow(Gtk.Box):
    """A row displaying service information and controls."""
    
    def __init__(self, service_name: str, service_config: dict, service_manager: ServiceManager, main_window=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.service_name = service_name
        self.service_config = service_config
        self.service_manager = service_manager
        self.main_window = main_window  # Reference to MainWindow for button control
        self.dev_mode = False  # Dev mode flag (for frontend)
        self._action_in_progress = False  # Track if an action is in progress
        
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        
        # Status indicator
        self.status_indicator = Gtk.DrawingArea()
        self.status_indicator.set_size_request(12, 12)
        self.status_indicator.set_draw_func(self._draw_status)
        self.append(self.status_indicator)
        
        # Service info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        
        name_label = Gtk.Label(label=service_config["name"])
        name_label.set_xalign(0)
        name_label.add_css_class("title")
        info_box.append(name_label)
        
        desc_label = Gtk.Label(label=service_config["description"])
        desc_label.set_xalign(0)
        desc_label.add_css_class("caption")
        desc_label.set_wrap(True)
        info_box.append(desc_label)
        
        port_label = Gtk.Label(label=f"Port: {service_config['port']}")
        port_label.set_xalign(0)
        port_label.add_css_class("caption")
        info_box.append(port_label)
        
        self.append(info_box)
        
        # Control buttons
        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.append(self.button_box)
        
        # Add appropriate buttons based on install status
        self._setup_buttons()
        
        # Update status periodically
        GLib.timeout_add_seconds(2, self._update_status)
        self._update_status()
    
    def _setup_buttons(self):
        """Setup appropriate buttons based on service state."""
        # Clear existing buttons
        while self.button_box.get_first_child():
            self.button_box.remove(self.button_box.get_first_child())
        
        if self._needs_install():
            # Show install button
            self.install_button = Gtk.Button(label="Install")
            self.install_button.connect("clicked", self._on_install_clicked)
            self.button_box.append(self.install_button)
        else:
            # Add dev mode toggle for frontend (on the left)
            if self.service_name == "frontend":
                self.dev_mode_check = Gtk.CheckButton(label="Dev Mode")
                self.dev_mode_check.set_active(self.dev_mode)
                self.dev_mode_check.connect("toggled", self._on_dev_mode_toggled)
                self.dev_mode_check.set_tooltip_text("Start frontend in development mode (npm run dev) for live style editing")
                self.button_box.append(self.dev_mode_check)
            
            # Show control buttons + reinstall
            self.start_button = Gtk.Button(label="Start")
            self.start_button.connect("clicked", self._on_start_clicked)
            self.button_box.append(self.start_button)
            
            self.stop_button = Gtk.Button(label="Stop")
            self.stop_button.connect("clicked", self._on_stop_clicked)
            self.button_box.append(self.stop_button)
            
            self.restart_button = Gtk.Button(label="Restart")
            self.restart_button.connect("clicked", self._on_restart_clicked)
            self.button_box.append(self.restart_button)
            
            # Add reinstall button
            self.reinstall_button = Gtk.Button(label="Reinstall")
            self.reinstall_button.connect("clicked", self._on_reinstall_clicked)
            self.button_box.append(self.reinstall_button)
    
    def _needs_install(self):
        """Check if service needs installation."""
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        
        if self.service_name == "gateway":
            # Check for .core_venv in services directory
            venv_path = project_root / "services" / ".core_venv"
            return not venv_path.exists()
        elif self.service_name == "chatterbox":
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            # Install script creates 'venv', not '.venv'
            venv_path = project_root / "services" / "tts-chatterbox" / "venv"
            return not venv_path.exists()
        elif self.service_name == "frontend":
            from pathlib import Path
            node_modules = Path("../services/frontend/node_modules").resolve()
            return not node_modules.exists()
        return False
    
    def _on_install_clicked(self, button):
        """Handle install button click."""
        if self._action_in_progress:
            return
        self._action_in_progress = True
        
        # Disable all other buttons
        if self.main_window:
            self.main_window._set_footer_buttons_sensitive(False)
            self.main_window._set_service_row_buttons_sensitive(False, exclude_row=self)
        
        # Show in-progress status immediately
        self._show_button_progress("Install", "⏳ Installing...")
        self._run_install(force=False)

    def _on_reinstall_clicked(self, button):
        """Handle reinstall button click."""
        if self._action_in_progress:
            return
        self._action_in_progress = True
        
        # Disable all other buttons
        if self.main_window:
            self.main_window._set_footer_buttons_sensitive(False)
            self.main_window._set_service_row_buttons_sensitive(False, exclude_row=self)
        
        # Reset completion flag
        self._reinstall_complete = False
        # Show in-progress status immediately
        self._show_button_progress("Reinstall", "⏳ Reinstalling...")
        self._run_install(force=True)

    def _run_install(self, force=False):
        """Run installation process."""
        action = "Reinstalling" if force else "Installing"
        # Add log to service manager
        self.service_manager.logs[self.service_name].append(f"{action} {self.service_name}...")

        import subprocess
        from pathlib import Path
        import threading
        launcher_dir = Path(__file__).parent.parent

        try:
            if self.service_name == "gateway":
                install_script = launcher_dir / "install.sh"
                if install_script.exists():
                    def run_install():
                        try:
                            # Reset completion flag at start
                            self._reinstall_complete = False
                            # Check for CUDA and inform user
                            import shutil
                            if shutil.which("nvidia-smi"):
                                self.service_manager.logs[self.service_name].append("🔍 CUDA detected! Installing with GPU support...")
                                self.service_manager.logs[self.service_name].append("⚡ Trying prebuilt CUDA wheels first (fast)...")
                            
                            # Run install and capture output line by line
                            # Explicitly use bash to ensure proper execution
                            process = subprocess.Popen(
                                ["bash", str(install_script)],
                                cwd=str(launcher_dir),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            
                            # Read output line by line and add to logs
                            for line in iter(process.stdout.readline, ''):
                                if not line:
                                    break
                                line = line.rstrip()
                                self.service_manager.logs[self.service_name].append(line)
                                # Keep only last 1000 lines
                                if len(self.service_manager.logs[self.service_name]) > 1000:
                                    self.service_manager.logs[self.service_name] = self.service_manager.logs[self.service_name][-1000:]
                            
                            process.wait()
                            
                            if process.returncode == 0:
                                # Check if CUDA was successfully installed
                                venv_python = Path("../services/.core_venv/bin/python")
                                if venv_python.exists():
                                    try:
                                        check_cuda = subprocess.run(
                                            [str(venv_python), "-c", 
                                             "from llama_cpp import llama_supports_gpu_offload; print('CUDA:', llama_supports_gpu_offload())"],
                                            capture_output=True,
                                            text=True,
                                            timeout=5
                                        )
                                        if check_cuda.returncode == 0:
                                            result = check_cuda.stdout.strip()
                                            if "CUDA: True" in result:
                                                self.service_manager.logs[self.service_name].append("✅ CUDA support verified! Model will use GPU.")
                                            elif "CUDA: False" in result:
                                                self.service_manager.logs[self.service_name].append("⚠️  CUDA not available - model will use CPU.")
                                    except Exception:
                                        pass  # Ignore verification errors
                                
                                self.service_manager.logs[self.service_name].append(f"✅ {action} of {self.service_name} completed successfully")
                                # Mark as complete for reinstall all tracking
                                self._reinstall_complete = True
                                # Show success message on button
                                self._show_button_success("Install", "✓ Installed")
                                # Re-enable buttons
                                self._action_in_progress = False
                                if self.main_window:
                                    self.main_window._set_footer_buttons_sensitive(True)
                                    self.main_window._set_service_row_buttons_sensitive(True)
                                # Force button refresh with delay to ensure venv is detected
                                def refresh_buttons():
                                    self._setup_buttons()
                                    self._update_status()
                                    return False
                                GLib.timeout_add(500, refresh_buttons)  # 500ms delay
                            else:
                                self.service_manager.logs[self.service_name].append(f"❌ {action} failed with code {process.returncode}")
                                # Mark as complete even on failure so reinstall all doesn't hang
                                self._reinstall_complete = True
                                # Re-enable buttons even on failure
                                self._action_in_progress = False
                                if self.main_window:
                                    self.main_window._set_footer_buttons_sensitive(True)
                                    self.main_window._set_service_row_buttons_sensitive(True)
                        except Exception as e:
                            self.service_manager.logs[self.service_name].append(f"❌ Install error: {e}")

                    thread = threading.Thread(target=run_install, daemon=True)
                    thread.start()

            elif self.service_name == "chatterbox":
                chatterbox_dir = Path("../services/tts-chatterbox").resolve()
                install_script = chatterbox_dir / "install.sh"

                def run_chatterbox_install():
                    try:
                        # Reset completion flag at start
                        self._reinstall_complete = False
                        # Log that we're starting
                        self.service_manager.logs[self.service_name].append(f"{action} {self.service_name}...")
                        self.service_manager.logs[self.service_name].append(f"Using install script: {install_script}")
                        
                        if not install_script.exists():
                            self.service_manager.logs[self.service_name].append(f"ERROR: Install script not found at {install_script}")
                            # Fallback: create venv with python3.11 directly
                            venv_path = Path("../services/.chatterbox_venv").resolve()
                            self.service_manager.logs[self.service_name].append("Creating Python 3.11 virtual environment...")
                            
                            # Create venv with python3.11
                            venv_process = subprocess.Popen(
                                ["python3.11", "-m", "venv", str(venv_path)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            
                            for line in iter(venv_process.stdout.readline, ''):
                                if not line:
                                    break
                                self.service_manager.logs[self.service_name].append(line.rstrip())
                            
                            venv_process.wait()
                            
                            if venv_process.returncode == 0:
                                # Install dependencies
                                pip = venv_path / "bin" / "pip"
                                if pip.exists():
                                    self.service_manager.logs[self.service_name].append("Installing dependencies...")
                                    pip_process = subprocess.Popen(
                                        [str(pip), "install", "-r", str(chatterbox_dir / "requirements.txt")],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True,
                                        bufsize=1
                                    )
                                    
                                    for line in iter(pip_process.stdout.readline, ''):
                                        if not line:
                                            break
                                        self.service_manager.logs[self.service_name].append(line.rstrip())
                                    
                                    pip_process.wait()
                                    
                                    if pip_process.returncode == 0:
                                        self.service_manager.logs[self.service_name].append(f"{action} of {self.service_name} completed")
                                        # Mark as complete for reinstall all tracking
                                        self._reinstall_complete = True
                                        # Show success message on button (progress already shown)
                                        self._show_button_success("Install", "✓ Installed")
                                        # Re-enable buttons
                                        self._action_in_progress = False
                                        if self.main_window:
                                            self.main_window._set_footer_buttons_sensitive(True)
                                            self.main_window._set_service_row_buttons_sensitive(True)
                                        def refresh_buttons():
                                            self._setup_buttons()
                                            self._update_status()
                                            return False
                                        GLib.timeout_add(500, refresh_buttons)  # 500ms delay
                                    else:
                                        self.service_manager.logs[self.service_name].append(f"{action} failed: pip install error")
                                        # Mark as complete even on failure so reinstall all doesn't hang
                                        self._reinstall_complete = True
                                else:
                                    self.service_manager.logs[self.service_name].append(f"{action} failed: pip not found in venv")
                                    # Mark as complete even on failure so reinstall all doesn't hang
                                    self._reinstall_complete = True
                                    # Re-enable buttons even on failure
                                    self._action_in_progress = False
                                    if self.main_window:
                                        self.main_window._set_footer_buttons_sensitive(True)
                                        self.main_window._set_service_row_buttons_sensitive(True)
                            else:
                                self.service_manager.logs[self.service_name].append(f"{action} failed: venv creation error")
                                # Mark as complete even on failure so reinstall all doesn't hang
                                self._reinstall_complete = True
                                # Re-enable buttons even on failure
                                self._action_in_progress = False
                                if self.main_window:
                                    self.main_window._set_footer_buttons_sensitive(True)
                                    self.main_window._set_service_row_buttons_sensitive(True)
                            return
                        
                        # Use install script if it exists
                        process = subprocess.Popen(
                            [str(install_script)],
                            cwd=str(chatterbox_dir),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        
                        for line in iter(process.stdout.readline, ''):
                            if not line:
                                break
                            line = line.rstrip()
                            self.service_manager.logs[self.service_name].append(line)
                            if len(self.service_manager.logs[self.service_name]) > 1000:
                                self.service_manager.logs[self.service_name] = self.service_manager.logs[self.service_name][-1000:]
                        
                        process.wait()
                        
                        if process.returncode == 0:
                            self.service_manager.logs[self.service_name].append(f"{action} of {self.service_name} completed")
                            # Mark as complete for reinstall all tracking
                            self._reinstall_complete = True
                            # Show success message on button (progress already shown)
                            self._show_button_success("Reinstall", "✓ Reinstalled")
                            # Re-enable buttons
                            self._action_in_progress = False
                            if self.main_window:
                                self.main_window._set_footer_buttons_sensitive(True)
                                self.main_window._set_service_row_buttons_sensitive(True)
                            def refresh_buttons():
                                self._setup_buttons()
                                self._update_status()
                                return False
                            GLib.timeout_add(500, refresh_buttons)  # 500ms delay
                        else:
                            self.service_manager.logs[self.service_name].append(f"{action} failed with code {process.returncode}")
                            # Mark as complete even on failure so reinstall all doesn't hang
                            self._reinstall_complete = True
                            # Re-enable buttons even on failure
                            self._action_in_progress = False
                            if self.main_window:
                                self.main_window._set_footer_buttons_sensitive(True)
                                self.main_window._set_service_row_buttons_sensitive(True)
                    except Exception as e:
                        self.service_manager.logs[self.service_name].append(f"Install error for {self.service_name}: {e}")

                thread = threading.Thread(target=run_chatterbox_install, daemon=True)
                thread.start()

            elif self.service_name == "frontend":
                frontend_dir = Path("../services/frontend").resolve()

                def run_frontend_install():
                    try:
                        # Reset completion flag at start
                        self._reinstall_complete = False
                        # Just run npm install and npm run build (no deletion)
                        self.service_manager.logs[self.service_name].append("Running npm install...")
                        install_process = subprocess.Popen(
                            ["npm", "install"],
                            cwd=str(frontend_dir),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        
                        for line in iter(install_process.stdout.readline, ''):
                            if not line:
                                break
                            line = line.rstrip()
                            self.service_manager.logs[self.service_name].append(line)
                            if len(self.service_manager.logs[self.service_name]) > 1000:
                                self.service_manager.logs[self.service_name] = self.service_manager.logs[self.service_name][-1000:]
                        
                        install_process.wait()
                        
                        if install_process.returncode == 0:
                            self.service_manager.logs[self.service_name].append("npm install completed, running npm run build...")
                            
                            # Run build
                            build_process = subprocess.Popen(
                                ["npm", "run", "build"],
                                cwd=str(frontend_dir),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            
                            for line in iter(build_process.stdout.readline, ''):
                                if not line:
                                    break
                                line = line.rstrip()
                                self.service_manager.logs[self.service_name].append(line)
                                if len(self.service_manager.logs[self.service_name]) > 1000:
                                    self.service_manager.logs[self.service_name] = self.service_manager.logs[self.service_name][-1000:]
                            
                            build_process.wait()
                            
                            if build_process.returncode == 0:
                                self.service_manager.logs[self.service_name].append(f"{action} of {self.service_name} completed successfully")
                                # Mark as complete for reinstall all tracking
                                self._reinstall_complete = True
                                # Show success message on button
                                self._show_button_success("Reinstall", "✓ Reinstalled")
                                # Re-enable buttons
                                self._action_in_progress = False
                                if self.main_window:
                                    self.main_window._set_footer_buttons_sensitive(True)
                                    self.main_window._set_service_row_buttons_sensitive(True)
                                def refresh_buttons():
                                    self._setup_buttons()
                                    self._update_status()
                                    return False
                                GLib.timeout_add(500, refresh_buttons)  # 500ms delay
                            else:
                                self.service_manager.logs[self.service_name].append(f"Build failed with code {build_process.returncode}")
                                # Mark as complete even on failure so reinstall all doesn't hang
                                self._reinstall_complete = True
                                # Re-enable buttons even on failure
                                self._action_in_progress = False
                                if self.main_window:
                                    self.main_window._set_footer_buttons_sensitive(True)
                                    self.main_window._set_service_row_buttons_sensitive(True)
                        else:
                            self.service_manager.logs[self.service_name].append(f"npm install failed with code {install_process.returncode}")
                            # Mark as complete even on failure so reinstall all doesn't hang
                            self._reinstall_complete = True
                            # Re-enable buttons even on failure
                            self._action_in_progress = False
                            if self.main_window:
                                self.main_window._set_footer_buttons_sensitive(True)
                                self.main_window._set_service_row_buttons_sensitive(True)
                    except Exception as e:
                        self.service_manager.logs[self.service_name].append(f"Install error for {self.service_name}: {e}")
                        # Re-enable buttons on error
                        self._action_in_progress = False
                        if self.main_window:
                            self.main_window._set_footer_buttons_sensitive(True)
                            self.main_window._set_service_row_buttons_sensitive(True)

                thread = threading.Thread(target=run_frontend_install, daemon=True)
                thread.start()

            else:
                print(f"No install logic for {self.service_name}", file=sys.stderr)

        except Exception as e:
            print(f"Install error for {self.service_name}: {e}", file=sys.stderr)
    
    def _draw_status(self, area, cr, width, height):
        """Draw status indicator."""
        status = self.service_manager.get_service_status(self.service_name)
        
        if status.get("status") == "running":
            cr.set_source_rgb(0, 0.8, 0)  # Green
        else:
            cr.set_source_rgb(0.8, 0, 0)  # Red
        
        cr.arc(width / 2, height / 2, min(width, height) / 2 - 1, 0, 2 * 3.14159)
        cr.fill()
    
    def _update_status(self):
        """Update UI based on service status."""
        status = self.service_manager.get_service_status(self.service_name)
        is_running = status.get("status") == "running"
        
        # Only update control buttons if they exist
        if hasattr(self, 'start_button'):
            self.start_button.set_sensitive(not is_running)
            self.stop_button.set_sensitive(is_running)
            self.restart_button.set_sensitive(is_running)
        
        self.status_indicator.queue_draw()
        return True  # Continue timeout
    
    def _show_button_progress(self, button_name: str, progress_text: str):
        """Show in-progress message on a button with yellow text."""
        button = None
        if button_name == "Install" and hasattr(self, 'install_button'):
            button = self.install_button
        elif button_name == "Reinstall" and hasattr(self, 'reinstall_button'):
            button = self.reinstall_button
        elif button_name == "Start" and hasattr(self, 'start_button'):
            button = self.start_button
        elif button_name == "Stop" and hasattr(self, 'stop_button'):
            button = self.stop_button
        elif button_name == "Restart" and hasattr(self, 'restart_button'):
            button = self.restart_button
        
        if button:
            # Store original label if not already stored
            if not hasattr(button, '_original_label'):
                button._original_label = button.get_label()
            button.set_label(progress_text)
            # Set yellow color using CSS class
            button.add_css_class("in-progress")
            # Add CSS provider for yellow text
            css_provider = Gtk.CssProvider()
            css = b"button.in-progress { color: #eab308; font-weight: bold; }"
            css_provider.load_from_data(css)
            style_context = button.get_style_context()
            style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            # Store provider reference
            button._progress_css_provider = css_provider
    
    def _show_button_success(self, button_name: str, success_text: str):
        """Show success message on a button with green text (after progress)."""
        button = None
        if button_name == "Install" and hasattr(self, 'install_button'):
            button = self.install_button
        elif button_name == "Reinstall" and hasattr(self, 'reinstall_button'):
            button = self.reinstall_button
        elif button_name == "Start" and hasattr(self, 'start_button'):
            button = self.start_button
        elif button_name == "Stop" and hasattr(self, 'stop_button'):
            button = self.stop_button
        elif button_name == "Restart" and hasattr(self, 'restart_button'):
            button = self.restart_button
        
        if button:
            # Remove progress styling first
            if hasattr(button, '_progress_css_provider'):
                style_context = button.get_style_context()
                style_context.remove_provider(button._progress_css_provider)
                del button._progress_css_provider
                button.remove_css_class("in-progress")
            
            # Get original label
            original_label = getattr(button, '_original_label', button.get_label())
            if not hasattr(button, '_original_label'):
                button._original_label = original_label
            
            button.set_label(success_text)
            # Set green color using CSS class
            button.add_css_class("success")
            # Add CSS provider for green text
            css_provider = Gtk.CssProvider()
            css = b"button.success { color: #22c55e; font-weight: bold; }"
            css_provider.load_from_data(css)
            style_context = button.get_style_context()
            style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            # Store provider reference to remove it later
            button._success_css_provider = css_provider
            # Reset after 3 seconds
            def reset_button():
                button.set_label(original_label)
                button.remove_css_class("success")
                if hasattr(button, '_success_css_provider'):
                    style_context.remove_provider(button._success_css_provider)
                    del button._success_css_provider
                if hasattr(button, '_original_label'):
                    del button._original_label
                return False
            GLib.timeout_add_seconds(3, reset_button)
    
    def _on_start_clicked(self, button):
        """Handle start button click."""
        if self._action_in_progress:
            return
        self._action_in_progress = True
        
        # Disable all other buttons
        if self.main_window:
            self.main_window._set_footer_buttons_sensitive(False)
            self.main_window._set_service_row_buttons_sensitive(False, exclude_row=self)
        
        # Show in-progress status immediately
        self._show_button_progress("Start", "⏳ Starting...")
        dev_mode = getattr(self, 'dev_mode', False) if self.service_name == "frontend" else False
        self.service_manager.start_service(self.service_name, dev_mode=dev_mode)
        self._update_status()
        
        # Track attempts and timeout
        max_attempts = 30  # 30 seconds timeout
        attempts = [0]  # Use list to allow modification in nested function
        
        # Show success after a short delay (service might take a moment to start)
        def check_success():
            attempts[0] += 1
            status = self.service_manager.get_service_status(self.service_name)
            status_value = status.get("status")
            
            if status_value == "running":
                self._show_button_success("Start", "✓ Started")
                # Re-enable buttons
                self._action_in_progress = False
                if self.main_window:
                    self.main_window._set_footer_buttons_sensitive(True)
                    self.main_window._set_service_row_buttons_sensitive(True)
                return False  # Stop checking
            elif status_value == "stopped":
                # Process exited - check if it was a startup failure
                # Check if process exited immediately (within first few checks)
                process = self.service_manager.processes.get(self.service_name)
                if process and process.poll() is not None:
                    # Process exited - startup failed
                    return_code = process.returncode
                    # Get recent logs to show error
                    logs = self.service_manager.get_logs(self.service_name, lines=10)
                    error_msg = f"✗ Failed (exit code: {return_code})"
                    if logs:
                        # Look for error messages in logs
                        for log_line in reversed(logs):
                            if "error" in log_line.lower() or "exception" in log_line.lower() or "traceback" in log_line.lower():
                                # Extract error message
                                if "SyntaxError" in log_line:
                                    error_msg = "✗ Syntax Error"
                                elif "ImportError" in log_line:
                                    error_msg = "✗ Import Error"
                                elif "ModuleNotFoundError" in log_line:
                                    error_msg = "✗ Module Not Found"
                                break
                    
                    self._show_button_error("Start", error_msg)
                    # Clean up the failed process entry
                    if self.service_name in self.service_manager.processes:
                        del self.service_manager.processes[self.service_name]
                # Re-enable buttons
                self._action_in_progress = False
                if self.main_window:
                    self.main_window._set_footer_buttons_sensitive(True)
                    self.main_window._set_service_row_buttons_sensitive(True)
                return False  # Stop checking
            elif attempts[0] >= max_attempts:
                # Timeout - service failed to start
                self._show_button_error("Start", "✗ Timeout")
                # Re-enable buttons
                self._action_in_progress = False
                if self.main_window:
                    self.main_window._set_footer_buttons_sensitive(True)
                    self.main_window._set_service_row_buttons_sensitive(True)
                return False  # Stop checking
            else:
                # Check again in 1 second if not running yet
                GLib.timeout_add_seconds(1, check_success)
                return False
        GLib.timeout_add_seconds(1, check_success)
    
    def _on_dev_mode_toggled(self, button):
        """Handle dev mode toggle."""
        self.dev_mode = button.get_active()
        # If service is running, restart it to apply dev mode
        if self.service_manager.is_running(self.service_name):
            self.service_manager.logs[self.service_name].append(f"Dev mode {'enabled' if self.dev_mode else 'disabled'}, restarting frontend...")
            # Show in-progress status
            self._show_button_progress("Restart", "⏳ Restarting...")
            self.service_manager.restart_service(self.service_name, dev_mode=self.dev_mode)
            self._update_status()
            
            # Track attempts and timeout
            max_attempts = 30  # 30 seconds timeout
            attempts = [0]  # Use list to allow modification in nested function
            
            # Show success after a short delay
            def check_success():
                attempts[0] += 1
                status = self.service_manager.get_service_status(self.service_name)
                if status.get("status") == "running":
                    self._show_button_success("Restart", "✓ Restarted")
                    return False  # Stop checking
                elif attempts[0] >= max_attempts:
                    # Timeout - service failed to restart
                    self._show_button_error("Restart", "✗ Failed")
                    return False  # Stop checking
                else:
                    # Check again in 1 second if not running yet
                    GLib.timeout_add_seconds(1, check_success)
                    return False
            GLib.timeout_add_seconds(1, check_success)
    
    def _on_stop_clicked(self, button):
        """Handle stop button click."""
        if self._action_in_progress:
            return
        self._action_in_progress = True
        
        # Disable all other buttons
        if self.main_window:
            self.main_window._set_footer_buttons_sensitive(False)
            self.main_window._set_service_row_buttons_sensitive(False, exclude_row=self)
        
        self.service_manager.stop_service(self.service_name)
        self._update_status()
        # Show success immediately (stop is instant)
        self._show_button_success("Stop", "✓ Stopped")
        
        # Re-enable buttons after a short delay
        def re_enable():
            self._action_in_progress = False
            if self.main_window:
                self.main_window._set_footer_buttons_sensitive(True)
                self.main_window._set_service_row_buttons_sensitive(True)
            return False
        GLib.timeout_add_seconds(0.5, re_enable)
    
    def _on_restart_clicked(self, button):
        """Handle restart button click."""
        if self._action_in_progress:
            return
        self._action_in_progress = True
        
        # Disable all other buttons
        if self.main_window:
            self.main_window._set_footer_buttons_sensitive(False)
            self.main_window._set_service_row_buttons_sensitive(False, exclude_row=self)
        
        dev_mode = getattr(self, 'dev_mode', False) if self.service_name == "frontend" else False
        self.service_manager.restart_service(self.service_name, dev_mode=dev_mode)
        self._update_status()
        
        # Track attempts and timeout
        max_attempts = 30  # 30 seconds timeout
        attempts = [0]  # Use list to allow modification in nested function
        
        # Show success after a short delay
        def check_success():
            attempts[0] += 1
            status = self.service_manager.get_service_status(self.service_name)
            if status.get("status") == "running":
                self._show_button_success("Restart", "✓ Restarted")
                # Re-enable buttons
                self._action_in_progress = False
                if self.main_window:
                    self.main_window._set_footer_buttons_sensitive(True)
                    self.main_window._set_service_row_buttons_sensitive(True)
                return False  # Stop checking
            elif attempts[0] >= max_attempts:
                # Timeout - service failed to restart
                self._show_button_error("Restart", "✗ Failed")
                # Re-enable buttons
                self._action_in_progress = False
                if self.main_window:
                    self.main_window._set_footer_buttons_sensitive(True)
                    self.main_window._set_service_row_buttons_sensitive(True)
                return False  # Stop checking
            else:
                # Check again in 1 second if not running yet
                GLib.timeout_add_seconds(1, check_success)
                return False
        GLib.timeout_add_seconds(1, check_success)