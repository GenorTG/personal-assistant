"""Console redirector for capturing stdout/stderr to text widgets."""

try:
    import customtkinter as ctk
except ImportError:
    # Fallback if customtkinter is not available (shouldn't happen in production)
    ctk = None


class ConsoleRedirector:
    """Redirects console output to a CustomTkinter text widget with batching."""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = []
        self.update_pending = False
        self.last_update_time = 0
        self.update_interval = 50  # Update every 50ms instead of 100ms for better responsiveness

    def write(self, str_val):
        # Ensure we handle Unicode/emoji properly
        if isinstance(str_val, bytes):
            # If bytes, decode as UTF-8 with error handling
            try:
                str_val = str_val.decode('utf-8', errors='surrogateescape')
            except Exception:
                str_val = str_val.decode('utf-8', errors='replace')
        # Ensure it's a string (Tkinter text widgets handle Unicode fine)
        if not isinstance(str_val, str):
            str_val = str(str_val)
        self.queue.append(str_val)
        if not self.update_pending:
            self.update_pending = True
            self.text_widget.after(self.update_interval, self.update_widget)

    def flush(self):
        pass

    def update_widget(self):
        if self.queue:
            # Batch all queued messages together
            text = "".join(self.queue)
            self.queue = []
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", text)
            # Only scroll to end if queue is getting large (performance optimization)
            if len(text) > 1000:
                self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        self.update_pending = False


