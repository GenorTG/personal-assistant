"""Main window for GTK4 launcher."""
import sys
import webbrowser
from pathlib import Path

# Add launcher directory to path
launcher_dir = Path(__file__).parent.parent
sys.path.insert(0, str(launcher_dir))

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

from config import SERVICES
from service_manager import ServiceManager
from ui.service_row import ServiceRow
from ui.test_dialog import TestDialog
from ui.models_view import ModelsView
from ui.models_view import ModelsView


class MainWindow(Gtk.ApplicationWindow):
    """Main application window."""
    
    def __init__(self, app):
        super().__init__(application=app)
        
        try:
            self.service_manager = ServiceManager()
        except Exception as e:
            print(f"Error initializing service manager: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self.service_manager = None
        
        self.set_title("Personal Assistant Launcher")
        # Calculate window height: services panel + separator + logs + footer + header
        # Services: ~90px per service * 3 = 270px, logs: ~400px, footer: ~50px, header: ~50px
        window_height = 90 * len(SERVICES) + 20 + 400 + 50 + 50  # ~790px minimum
        self.set_default_size(900, max(700, window_height))
        
        # Header bar (replaces default titlebar) - MUST be set before window is realized
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        # Set title using a label widget
        title_label = Gtk.Label(label="Personal Assistant Services")
        header.set_title_widget(title_label)
        self.set_titlebar(header)
        
        # Ensure window is visible
        self.set_visible(True)
        self.present()
        
        # Main container with notebook for tabs
        main_notebook = Gtk.Notebook()
        self.set_child(main_notebook)
        
        # Tab 1: Services
        services_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_notebook.append_page(services_page, Gtk.Label(label="Services"))
        
        # Tab 2: Models
        models_view = ModelsView()
        main_notebook.append_page(models_view, Gtk.Label(label="Models"))
        
        # Main container for services tab
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        services_page.append(main_box)

        # Services panel (top) - ensure enough space for all services
        services_scrolled = Gtk.ScrolledWindow()
        services_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # Calculate minimum height: ~90px per service row + padding
        # Each row has: 8px top margin + content (~60px) + 8px bottom margin + buttons
        min_services_height = 90 * len(SERVICES) + 20  # 90px per row + 20px padding
        services_scrolled.set_size_request(-1, min_services_height)
        services_scrolled.set_vexpand(False)  # Don't expand, use fixed size

        services_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        services_scrolled.set_child(services_box)

        # Add service rows and store references
        self.service_rows = {}
        if self.service_manager:
            for service_name, service_config in SERVICES.items():
                try:
                    row = ServiceRow(service_name, service_config, self.service_manager, main_window=self)
                    services_box.append(row)
                    self.service_rows[service_name] = row
                except Exception as e:
                    print(f"Error creating row for {service_name}: {e}", file=sys.stderr)
                    import traceback
                    traceback.print_exc()

        main_box.append(services_scrolled)

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.append(separator)

        # Logs panel (bottom) - takes remaining space, but doesn't overlap
        logs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        logs_box.set_vexpand(True)
        logs_box.set_hexpand(True)

        # Logs header
        logs_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        logs_header.set_margin_start(12)
        logs_header.set_margin_end(12)
        logs_header.set_margin_top(8)
        logs_header.set_margin_bottom(8)

        logs_label = Gtk.Label(label="Service Logs")
        logs_label.set_xalign(0)
        logs_label.add_css_class("title")
        logs_header.append(logs_label)

        # Clear logs button
        clear_button = Gtk.Button(label="Clear All")
        clear_button.connect("clicked", self._on_clear_logs)
        logs_header.append(clear_button)

        logs_box.append(logs_header)

        # Create notebook (tabs) for different services
        self.logs_notebook = Gtk.Notebook()
        self.logs_notebook.set_vexpand(True)
        self.logs_notebook.set_hexpand(True)
        
        # Service colors for log text
        self.service_colors = {
            "gateway": "#2563EB",      # Bright Blue
            "frontend": "#10B981",      # Bright Green
            "chatterbox": "#EF4444",   # Bright Red
        }
        
        # Create a tab and text view for each service
        self.logs_text_views = {}
        self.logs_buffers = {}
        
        for service_name in SERVICES.keys():
            # Create scrolled window for this service
            service_scrolled = Gtk.ScrolledWindow()
            service_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            service_scrolled.set_vexpand(True)
            service_scrolled.set_hexpand(True)
            
            # Create text view
            service_text = Gtk.TextView()
            service_text.set_editable(False)
            service_text.set_monospace(True)
            service_text.set_wrap_mode(Gtk.WrapMode.WORD)
            service_buffer = service_text.get_buffer()
            
            # Create color tag for this service
            color = self.service_colors.get(service_name, "#000000")
            tag = service_buffer.create_tag(
                f"service_{service_name}",
                foreground=color,
                weight=700  # Bold
            )
            
            service_scrolled.set_child(service_text)
            
            # Create tab label with color
            tab_label = Gtk.Label(label=SERVICES[service_name]["name"])
            tab_label.set_margin_start(8)
            tab_label.set_margin_end(8)
            tab_label.set_margin_top(4)
            tab_label.set_margin_bottom(4)
            
            # Add CSS class for color (we'll style it)
            tab_label.add_css_class(f"log-tab-{service_name}")
            
            # Append tab to notebook
            self.logs_notebook.append_page(service_scrolled, tab_label)
            
            # Store references
            self.logs_text_views[service_name] = service_text
            self.logs_buffers[service_name] = service_buffer
        
        logs_box.append(self.logs_notebook)
        main_box.append(logs_box)
        
        # Footer with global controls
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        footer.set_margin_top(8)
        footer.set_margin_bottom(8)
        
        start_all_button = Gtk.Button(label="Start All")
        start_all_button.connect("clicked", self._on_start_all)
        footer.append(start_all_button)
        
        stop_all_button = Gtk.Button(label="Stop All")
        stop_all_button.connect("clicked", self._on_stop_all)
        footer.append(stop_all_button)
        
        reinstall_all_button = Gtk.Button(label="Reinstall All")
        reinstall_all_button.connect("clicked", self._on_reinstall_all)
        footer.append(reinstall_all_button)
        
        # Test Services button
        test_button = Gtk.Button(label="Test TTS/STT")
        test_button.connect("clicked", self._on_test_services)
        footer.append(test_button)
        
        # Open Frontend button
        self.open_frontend_button = Gtk.Button(label="Open Frontend")
        self.open_frontend_button.connect("clicked", self._on_open_frontend)
        self.open_frontend_button.set_sensitive(False)  # Disabled by default
        footer.append(self.open_frontend_button)
        
        main_box.append(footer)
        
        # Check frontend status periodically
        if self.service_manager:
            GLib.timeout_add_seconds(2, self._check_frontend_status)

        # Connect close handler to cleanup services
        self.connect("close-request", self._on_close_request)
        
        # Start log updates
        if self.service_manager:
            # Track what we've already displayed
            self.displayed_log_counts = {name: 0 for name in SERVICES.keys()}
            GLib.timeout_add_seconds(1, self.update_logs)
            self.update_logs()  # Initial update
    
    def _on_start_all(self, button):
        """Start all services with staggered launch (non-blocking)."""
        import threading
        import time
        
        # Disable all buttons during start
        self._set_buttons_sensitive(False, exclude_button=button)
        
        def start_services_staggered():
            """Start services one by one with delays to prevent lag."""
            service_names = list(SERVICES.keys())
            for i, service_name in enumerate(service_names):
                # Stagger by 1 second between each service
                if i > 0:
                    time.sleep(1)
                # Start service in background (non-blocking)
                self.service_manager.start_service(service_name)
        
        # Run in separate thread to avoid blocking UI
        thread = threading.Thread(target=start_services_staggered, daemon=True)
        thread.start()
        
        # Show status on button
        original_label = button.get_label()
        button.set_label("⏳ Starting All...")
        button.add_css_class("in-progress")
        css_provider = Gtk.CssProvider()
        css = b"button.in-progress { color: #eab308; font-weight: bold; }"
        css_provider.load_from_data(css)
        style_context = button.get_style_context()
        style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        button._progress_css_provider = css_provider
        
        # Check status after delay and show success
        def check_and_update():
            # Check if all services are running
            all_running = all(
                self.service_manager.get_service_status(name).get("status") == "running"
                for name in SERVICES.keys()
            )
            if all_running:
                button.set_label("✓ All Started")
                button.remove_css_class("in-progress")
                style_context.remove_provider(button._progress_css_provider)
                del button._progress_css_provider
                button.add_css_class("success")
                css_provider = Gtk.CssProvider()
                css = b"button.success { color: #22c55e; font-weight: bold; }"
                css_provider.load_from_data(css)
                style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                button._success_css_provider = css_provider
                
                # Re-enable all buttons
                self._set_buttons_sensitive(True)
                
                # Reset after 3 seconds
                def reset_button():
                    button.set_label(original_label)
                    button.remove_css_class("success")
                    if hasattr(button, '_success_css_provider'):
                        style_context.remove_provider(button._success_css_provider)
                        del button._success_css_provider
                    return False
                GLib.timeout_add_seconds(3, reset_button)
            else:
                # Check again in 1 second
                GLib.timeout_add_seconds(1, check_and_update)
            return False
        
        GLib.timeout_add_seconds(2, check_and_update)
    
    def _on_stop_all(self, button):
        """Stop all services."""
        # Disable all buttons during stop
        self._set_buttons_sensitive(False, exclude_button=button)
        
        for service_name in SERVICES.keys():
            self.service_manager.stop_service(service_name)
        
        # Re-enable buttons after a short delay (stop is usually quick)
        def re_enable_buttons():
            self._set_buttons_sensitive(True)
            return False
        GLib.timeout_add_seconds(1, re_enable_buttons)
    
    def _on_reinstall_all(self, button):
        """Reinstall all services."""
        # Track reinstalling state
        if not hasattr(self, '_reinstalling_services'):
            self._reinstalling_services = set()
        
        # Disable all other buttons during reinstall
        self._set_buttons_sensitive(False, exclude_button=button)
        
        # Show loading state (yellow) instead of success (green)
        original_label = button.get_label()
        button.set_label("⏳ Reinstalling All...")
        button.add_css_class("in-progress")
        # Add CSS provider for yellow text
        css_provider = Gtk.CssProvider()
        css = b"button.in-progress { color: #eab308; font-weight: bold; }"
        css_provider.load_from_data(css)
        style_context = button.get_style_context()
        style_context.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        button._progress_css_provider = css_provider
        button._original_label = original_label
        
        # Track which services are being reinstalled
        self._reinstalling_services.clear()
        for service_name in SERVICES.keys():
            if service_name in self.service_rows:
                row = self.service_rows[service_name]
                # Only reinstall if service is installed (has reinstall button)
                if hasattr(row, 'reinstall_button'):
                    self._reinstalling_services.add(service_name)
                    # Call reinstall on each service row
                    row._run_install(force=True)
        
        # If no services to reinstall, reset immediately
        if not self._reinstalling_services:
            self._reset_reinstall_button(button)
            self._set_buttons_sensitive(True)
            return
        
        # Check periodically if all reinstalls are complete
        def check_reinstall_complete():
            # Check if any service row still shows "Reinstalling..." on its button
            still_reinstalling = False
            completed_services = []
            
            for service_name in list(self._reinstalling_services):
                if service_name in self.service_rows:
                    row = self.service_rows[service_name]
                    if hasattr(row, 'reinstall_button'):
                        label = row.reinstall_button.get_label()
                        # Check if reinstall is complete (either by flag or button label)
                        is_complete = (
                            getattr(row, '_reinstall_complete', False) or
                            ("✓" in label and ("Reinstalled" in label or "Installed" in label))
                        )
                        
                        # If button still shows "⏳ Reinstalling..." or "Reinstalling...", it's still in progress
                        # Also check that the completion flag is not set
                        if not is_complete and ("⏳" in label or "Reinstalling" in label or label == "Reinstall"):
                            still_reinstalling = True
                        elif is_complete:
                            # Service completed, mark for removal
                            completed_services.append(service_name)
            
            # Remove completed services from tracking
            for service_name in completed_services:
                self._reinstalling_services.discard(service_name)
            
            if not still_reinstalling and not self._reinstalling_services:
                # All reinstalls complete
                # Show success message
                button.set_label("✓ All Reinstalled")
                button.remove_css_class("in-progress")
                if hasattr(button, '_progress_css_provider'):
                    style_context.remove_provider(button._progress_css_provider)
                    del button._progress_css_provider
                button.add_css_class("success")
                success_css = Gtk.CssProvider()
                success_css_data = b"button.success { color: #22c55e; font-weight: bold; }"
                success_css.load_from_data(success_css_data)
                style_context.add_provider(success_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
                button._success_css_provider = success_css
                
                # Re-enable all buttons
                self._set_buttons_sensitive(True)
                
                # Reset after 3 seconds
                def reset_button():
                    self._reset_reinstall_button(button)
                    return False
                GLib.timeout_add_seconds(3, reset_button)
                return False  # Stop checking
            elif still_reinstalling:
                # Still reinstalling, continue checking (callback will be called again)
                return True  # Continue checking
            else:
                # No services being reinstalled, reset
                self._reset_reinstall_button(button)
                self._set_buttons_sensitive(True)
                return False  # Stop checking
        
        # Start checking after 2 seconds (give time for installs to start), then check every 1 second
        # Use a closure to track the timeout ID so we can cancel it if needed
        timeout_id = [None]
        
        def check_periodically():
            result = check_reinstall_complete()
            if result:
                # Still checking, schedule next check
                timeout_id[0] = GLib.timeout_add_seconds(1, check_periodically)
            return False  # This callback is done
        
        # Start checking after 2 seconds
        timeout_id[0] = GLib.timeout_add_seconds(2, check_periodically)
    
    def _reset_reinstall_button(self, button):
        """Reset reinstall button to original state."""
        if hasattr(button, '_original_label'):
            button.set_label(button._original_label)
            del button._original_label
        button.remove_css_class("in-progress")
        button.remove_css_class("success")
        if hasattr(button, '_progress_css_provider'):
            style_context = button.get_style_context()
            style_context.remove_provider(button._progress_css_provider)
            del button._progress_css_provider
        if hasattr(button, '_success_css_provider'):
            style_context = button.get_style_context()
            style_context.remove_provider(button._success_css_provider)
            del button._success_css_provider
    
    def _set_buttons_sensitive(self, sensitive: bool, exclude_button=None):
        """Enable or disable all footer buttons except the excluded one."""
        # Get footer (last child of main box)
        main_box = self.get_child()
        if main_box:
            footer = main_box.get_last_child()
            if footer:
                # Iterate through all buttons in footer
                child = footer.get_first_child()
                while child:
                    if isinstance(child, Gtk.Button) and child != exclude_button:
                        child.set_sensitive(sensitive)
                    child = child.get_next_sibling()
                
                # Also disable service row buttons
                for service_name in SERVICES.keys():
                    if service_name in self.service_rows:
                        row = self.service_rows[service_name]
                        # Disable/enable all buttons in service row
                        if hasattr(row, 'start_button'):
                            row.start_button.set_sensitive(sensitive)
                        if hasattr(row, 'stop_button'):
                            row.stop_button.set_sensitive(sensitive)
                        if hasattr(row, 'restart_button'):
                            row.restart_button.set_sensitive(sensitive)
                        if hasattr(row, 'install_button'):
                            row.install_button.set_sensitive(sensitive)
                        if hasattr(row, 'reinstall_button') and row.reinstall_button != exclude_button:
                            row.reinstall_button.set_sensitive(sensitive)
                        # Also disable dev mode checkbox during actions
                        if hasattr(row, 'dev_mode_check'):
                            row.dev_mode_check.set_sensitive(sensitive)
    
    def _set_footer_buttons_sensitive(self, sensitive: bool, exclude_button=None):
        """Enable or disable only footer buttons (not service row buttons)."""
        main_box = self.get_child()
        if main_box:
            footer = main_box.get_last_child()
            if footer:
                child = footer.get_first_child()
                while child:
                    if isinstance(child, Gtk.Button) and child != exclude_button:
                        child.set_sensitive(sensitive)
                    child = child.get_next_sibling()
    
    def _set_service_row_buttons_sensitive(self, sensitive: bool, exclude_row=None):
        """Enable or disable all service row buttons except the excluded row."""
        for service_name in SERVICES.keys():
            if service_name in self.service_rows:
                row = self.service_rows[service_name]
                if row == exclude_row:
                    continue
                # Disable/enable all buttons in service row
                if hasattr(row, 'start_button'):
                    row.start_button.set_sensitive(sensitive)
                if hasattr(row, 'stop_button'):
                    row.stop_button.set_sensitive(sensitive)
                if hasattr(row, 'restart_button'):
                    row.restart_button.set_sensitive(sensitive)
                if hasattr(row, 'install_button'):
                    row.install_button.set_sensitive(sensitive)
                if hasattr(row, 'reinstall_button'):
                    row.reinstall_button.set_sensitive(sensitive)
                if hasattr(row, 'dev_mode_check'):
                    row.dev_mode_check.set_sensitive(sensitive)

    def _on_clear_logs(self, button):
        """Clear the logs display for all services."""
        if hasattr(self, 'logs_buffers'):
            for service_name, buffer in self.logs_buffers.items():
                buffer.set_text("")
            # Set displayed counts to current log lengths (don't reset to 0, that causes re-display)
            if hasattr(self, 'displayed_log_counts') and self.service_manager:
                for service_name in SERVICES.keys():
                    current_logs = self.service_manager.get_logs(service_name, lines=2000)
                    self.displayed_log_counts[service_name] = len(current_logs)

    def update_logs(self):
        """Update the logs display - only append NEW lines, never replace."""
        if not hasattr(self, 'logs_buffers') or not hasattr(self, 'logs_text_views'):
            return True

        # Batch all updates to improve performance
        updates = []
        for service_name in SERVICES.keys():
            all_logs = self.service_manager.get_logs(service_name, lines=2000)
            displayed_count = getattr(self, 'displayed_log_counts', {}).get(service_name, 0)
            
            if len(all_logs) > displayed_count:
                # Get new lines
                new_logs = all_logs[displayed_count:]
                
                if new_logs:
                    updates.append((service_name, new_logs, displayed_count == 0))
                    self.displayed_log_counts[service_name] = len(all_logs)

        # Apply all updates in a single batch operation
        if updates:
            for service_name, new_logs, is_first in updates:
                # Get the buffer and text view for this service
                buffer = self.logs_buffers.get(service_name)
                text_view = self.logs_text_views.get(service_name)
                
                if not buffer or not text_view:
                    continue
                
                # Get current scroll position for this service's view
                vadj = text_view.get_vadjustment()
                old_scroll_pos = None
                was_at_bottom = False
                if vadj:
                    old_scroll_pos = vadj.get_value()
                    max_pos = vadj.get_upper() - vadj.get_page_size()
                    was_at_bottom = max_pos > 0 and (max_pos - old_scroll_pos) < 10
                
                service_tag = f"service_{service_name}"
                
                # Freeze updates for better performance
                buffer.begin_user_action()
                try:
                    # Get insertion point
                    end_iter = buffer.get_end_iter()
                    
                    # Add service header if this is first time
                    if is_first:
                        header_start = end_iter.copy()
                        buffer.insert(end_iter, f"=== {SERVICES[service_name]['name'].upper()} LOGS ===\n")
                        header_end = buffer.get_end_iter()
                        # Apply service color tag to header
                        buffer.apply_tag_by_name(service_tag, header_start, header_end)
                        end_iter = header_end
                    
                    # Insert log lines with color
                    for line in new_logs:
                        text_start = end_iter.copy()
                        buffer.insert(end_iter, f"{line}\n")
                        text_end = buffer.get_end_iter()
                        # Apply service color tag to this line
                        buffer.apply_tag_by_name(service_tag, text_start, text_end)
                        end_iter = text_end
                finally:
                    buffer.end_user_action()
                
                # Auto-scroll to bottom if new lines were added and user was at bottom
                if vadj and was_at_bottom:
                    def scroll_to_bottom():
                        if vadj:
                            max_pos = max(0, vadj.get_upper() - vadj.get_page_size())
                            vadj.set_value(max_pos)
                        return False
                    GLib.idle_add(scroll_to_bottom)

        return True  # Continue updating

    def _on_test_services(self, button):
        """Open TTS/STT testing dialog."""
        # Check if gateway is running
        gateway_status = None
        if self.service_manager:
            gateway_status = self.service_manager.get_service_status("gateway")
            if gateway_status.get("status") != "running":
                # Show warning dialog
                dialog = Gtk.MessageDialog(
                    parent=self,
                    modal=True,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Gateway Not Running",
                    secondary_text="The Gateway service must be running to test TTS/STT services.\n\n"
                                 "Please start the Gateway service first using the 'Start' button."
                )
                dialog.connect("response", lambda d, r: d.destroy())
                dialog.show()
                return
        
        dialog = TestDialog(self, service_manager=self.service_manager)
        dialog.present()
    
    def _on_open_frontend(self, button):
        """Open frontend UI in default browser."""
        import subprocess
        import os
        
        url = "http://localhost:8002"
        
        # On Linux, xdg-open is the most reliable way to open default browser
        if os.name == 'posix':
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                print(f"Error with xdg-open: {e}, trying webbrowser module...", file=sys.stderr)
        
        # Fallback to webbrowser module
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Error opening frontend: {e}", file=sys.stderr)
    
    def _check_frontend_status(self):
        """Check if frontend service is running and enable/disable button."""
        if not self.service_manager or not hasattr(self, 'open_frontend_button'):
            return True  # Continue checking
        
        # Check if frontend process is running
        frontend_running = "frontend" in self.service_manager.processes
        self.open_frontend_button.set_sensitive(frontend_running)
        
        return True  # Continue checking
    
    def _on_close_request(self, window):
        """Handle window close request - stop all services before closing."""
        print("Window close requested, stopping all services...", file=sys.stderr)
        if self.service_manager:
            self.service_manager.stop_all_services()
        return False  # Allow close


