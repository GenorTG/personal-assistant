"""Logging functionality for the launcher UI."""

try:
    import customtkinter as ctk
except ImportError:
    # Fallback if customtkinter is not available (shouldn't happen in production)
    ctk = None
from typing import Dict


class UILogger:
    """Manages batched logging to UI text widgets with color support."""
    
    def __init__(self, app):
        self.app = app
        self._log_queue_launcher = []
        self._log_queue_services: Dict[str, list] = {}
        self._log_update_pending = False
        self._log_batch_interval = 100  # Batch logs every 100ms
        self._log_batch_size_limit = 50  # Max messages per batch
        
        # Initialize color tags for textboxes (will be set up after textboxes are created)
        self._color_tags_initialized = False
    
    def _get_text_widget(self, textbox):
        """Get the underlying Tkinter Text widget from a CTkTextbox."""
        # CTkTextbox wraps a Tkinter Text widget
        # Try different ways to access it depending on CustomTkinter version
        if hasattr(textbox, 'textbox'):
            return textbox.textbox
        elif hasattr(textbox, '_textbox'):
            return textbox._textbox
        elif hasattr(textbox, 'tk'):
            # If it's already a Tkinter widget, return it
            return textbox
        else:
            # Fallback: try to find Text widget in children
            for child in textbox.winfo_children():
                if hasattr(child, 'tag_config'):
                    return child
            # Last resort: return the textbox itself (might work if it's already a Text widget)
            return textbox
    
    def _initialize_color_tags(self, textbox):
        """Initialize color tags for a textbox if not already done."""
        if not hasattr(textbox, '_color_tags_initialized'):
            text_widget = self._get_text_widget(textbox)
            
            # Blue for info
            text_widget.tag_config("info", foreground="#4A9EFF")
            # Green for status/success
            text_widget.tag_config("status", foreground="#10C469")
            # Red for errors
            text_widget.tag_config("error", foreground="#FF6B6B")
            textbox._color_tags_initialized = True
    
    def _insert_with_tag(self, textbox, text, tag):
        """Insert text with a color tag into a CTkTextbox."""
        text_widget = self._get_text_widget(textbox)
        text_widget.insert("end", text, tag)
    
    def _get_message_tag(self, message: str) -> str:
        """Determine the color tag for a message based on its content."""
        message_lower = message.lower()
        
        # Error keywords
        if any(keyword in message_lower for keyword in [
            'error', 'failed', 'exception', 'traceback', 'fatal', 
            'critical', 'crash', 'stopped unexpectedly', 'died'
        ]):
            return "error"
        
        # Status/success keywords
        if any(keyword in message_lower for keyword in [
            'success', 'started', 'running', 'installed', 'completed',
            'ready', '✓', '●', 'ok', 'done', 'finished'
        ]):
            return "status"
        
        # Default to info (blue)
        return "info"
    
    def log_to_launcher(self, message):
        """Log a message to the launcher tab only (thread-safe, batched)."""
        self._log_queue_launcher.append(message)
        if not self._log_update_pending:
            self._log_update_pending = True
            self.app.after(self._log_batch_interval, self._flush_log_queue)
    
    def log_to_service(self, service_name: str, message: str):
        """Log a message to a service-specific tab (thread-safe, batched)."""
        if service_name not in self._log_queue_services:
            self._log_queue_services[service_name] = []
        self._log_queue_services[service_name].append(message)
        if not self._log_update_pending:
            self._log_update_pending = True
            self.app.after(self._log_batch_interval, self._flush_log_queue)
    
    def _flush_log_queue(self):
        """Flush batched log messages to UI (called from main thread)."""
        # Flush launcher logs
        if self._log_queue_launcher:
            launcher_log = self.app.log_tabs.get("launcher_textbox")
            all_log = self.app.log_tabs.get("all_textbox")
            if launcher_log:
                self._initialize_color_tags(launcher_log)
                launcher_log.configure(state="normal")
                # Batch insert all messages at once with color tags
                messages = self._log_queue_launcher[:self._log_batch_size_limit]
                self._log_queue_launcher = self._log_queue_launcher[self._log_batch_size_limit:]
                
                for msg in messages:
                    tag = self._get_message_tag(msg)
                    self._insert_with_tag(launcher_log, msg + "\n", tag)
                launcher_log.see("end")
                launcher_log.configure(state="disabled")
            # Also add to "all" tab with colors
            if all_log:
                self._initialize_color_tags(all_log)
                all_log.configure(state="normal")
                for msg in messages:
                    tag = self._get_message_tag(msg)
                    self._insert_with_tag(all_log, msg + "\n", tag)
                all_log.see("end")
                all_log.configure(state="disabled")
        
        # Flush service-specific logs
        for service_name, messages in list(self._log_queue_services.items()):
            if messages:
                service_log = self.app.log_tabs.get(service_name)
                all_log = self.app.log_tabs.get("all_textbox")
                if service_log:
                    self._initialize_color_tags(service_log)
                    service_log.configure(state="normal")
                    # Batch insert all messages at once with color tags
                    batch = messages[:self._log_batch_size_limit]
                    self._log_queue_services[service_name] = messages[self._log_batch_size_limit:]
                    
                    for msg in batch:
                        tag = self._get_message_tag(msg)
                        self._insert_with_tag(service_log, msg + "\n", tag)
                    # Only scroll if batch is significant
                    if len(batch) > 5:
                        service_log.see("end")
                    service_log.configure(state="disabled")
                    # Also add to "all" tab with service prefix and colors
                    if all_log:
                        self._initialize_color_tags(all_log)
                        all_log.configure(state="normal")
                        for msg in batch:
                            tag = self._get_message_tag(msg)
                            prefixed_msg = f"[{service_name}] {msg}"
                            self._insert_with_tag(all_log, prefixed_msg + "\n", tag)
                        all_log.see("end")
                        all_log.configure(state="disabled")
                else:
                    # Remove queue if service log doesn't exist
                    del self._log_queue_services[service_name]
        
        # Schedule next flush if there are more messages
        if self._log_queue_launcher or any(self._log_queue_services.values()):
            self.app.after(self._log_batch_interval, self._flush_log_queue)
        else:
            self._log_update_pending = False


