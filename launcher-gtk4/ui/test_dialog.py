"""TTS/STT Testing Dialog for GTK4 launcher."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Adw
import threading
import tempfile
import subprocess
import os
from pathlib import Path
import logging

# Try to import httpx, fallback to urllib if not available
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    try:
        import urllib.request
        import urllib.parse
        import json
    except ImportError:
        pass

logger = logging.getLogger(__name__)


class TestDialog(Gtk.Dialog):
    """Dialog for testing TTS and STT services."""
    
    def __init__(self, parent, gateway_url="http://localhost:8000", service_manager=None):
        super().__init__(title="TTS/STT Service Testing")
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 700)
        self.gateway_url = gateway_url
        self.service_manager = service_manager  # Store reference to check gateway status
        
        # Create main content
        content_area = self.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)
        
        # Notebook for tabs
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        content_area.append(notebook)
        
        # TTS Tab
        tts_page = self._create_tts_page()
        notebook.append_page(tts_page, Gtk.Label(label="TTS Testing"))
        
        # STT Tab
        stt_page = self._create_stt_page()
        notebook.append_page(stt_page, Gtk.Label(label="STT Testing"))
        
        # Status Tab
        status_page = self._create_status_page()
        notebook.append_page(status_page, Gtk.Label(label="Service Status"))
        
        # Close button
        self.add_button("Close", Gtk.ResponseType.CLOSE)
    
    def _create_tts_page(self):
        """Create TTS testing page."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Title
        title = Gtk.Label(label="Text-to-Speech Testing")
        title.add_css_class("title-2")
        box.append(title)
        
        # Info label
        info_label = Gtk.Label(
            label="Note: TTS is integrated into the Gateway service.\n"
                  "Make sure Gateway is running before testing."
        )
        info_label.add_css_class("caption")
        info_label.set_wrap(True)
        info_label.set_margin_bottom(8)
        box.append(info_label)
        
        # Backend selection
        backend_frame = Gtk.Frame(label="TTS Backend")
        backend_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        backend_frame.set_child(backend_box)
        backend_frame.set_margin_bottom(12)
        
        self.tts_backend_combo = Gtk.ComboBoxText()
        self.tts_backend_combo.append_text("piper")
        self.tts_backend_combo.append_text("kokoro")
        self.tts_backend_combo.append_text("chatterbox")
        self.tts_backend_combo.append_text("pyttsx3")
        self.tts_backend_combo.set_active(0)
        backend_box.append(self.tts_backend_combo)
        box.append(backend_frame)
        
        # Text input
        text_frame = Gtk.Frame(label="Text to Synthesize")
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        text_frame.set_child(text_box)
        text_frame.set_margin_bottom(12)
        
        self.tts_text_buffer = Gtk.TextBuffer()
        self.tts_text_view = Gtk.TextView(buffer=self.tts_text_buffer)
        self.tts_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.tts_text_view.set_size_request(-1, 150)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.tts_text_view)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_box.append(scrolled)
        
        # Default text
        self.tts_text_buffer.set_text("Hello! This is a test of the text-to-speech service.")
        box.append(text_frame)
        
        # Synthesize button
        synthesize_btn = Gtk.Button(label="Synthesize & Play")
        synthesize_btn.add_css_class("suggested-action")
        synthesize_btn.connect("clicked", self._on_tts_synthesize)
        box.append(synthesize_btn)
        
        # Status label
        self.tts_status_label = Gtk.Label()
        self.tts_status_label.set_markup('<span size="medium">Ready</span>')
        self.tts_status_label.add_css_class("caption")
        # Make error messages more readable
        self.tts_status_label.set_margin_top(4)
        self.tts_status_label.set_margin_bottom(4)
        self.tts_status_label.set_wrap(True)
        box.append(self.tts_status_label)
        
        # Add spacer
        box.append(Gtk.Label())  # Spacer
        
        return box
    
    def _create_stt_page(self):
        """Create STT testing page."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Title
        title = Gtk.Label(label="Speech-to-Text Testing")
        title.add_css_class("title-2")
        box.append(title)
        
        # Info label
        info_label = Gtk.Label(
            label="Note: STT is integrated into the Gateway service.\n"
                  "Make sure Gateway is running before testing."
        )
        info_label.add_css_class("caption")
        info_label.set_wrap(True)
        info_label.set_margin_bottom(8)
        box.append(info_label)
        
        # Instructions
        instructions = Gtk.Label(
            label="Record audio using your system's audio recorder,\n"
                  "then select the file to transcribe."
        )
        instructions.set_wrap(True)
        instructions.add_css_class("caption")
        box.append(instructions)
        
        # File selection
        file_frame = Gtk.Frame(label="Audio File")
        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        file_frame.set_child(file_box)
        file_frame.set_margin_bottom(12)
        
        file_box_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.stt_file_label = Gtk.Label(label="No file selected")
        self.stt_file_label.set_hexpand(True)
        self.stt_file_label.set_halign(Gtk.Align.START)
        file_box_inner.append(self.stt_file_label)
        
        file_btn = Gtk.Button(label="Select File")
        file_btn.connect("clicked", self._on_stt_select_file)
        file_box_inner.append(file_btn)
        file_box.append(file_box_inner)
        box.append(file_frame)
        
        # Transcribe button
        transcribe_btn = Gtk.Button(label="Transcribe")
        transcribe_btn.add_css_class("suggested-action")
        transcribe_btn.connect("clicked", self._on_stt_transcribe)
        box.append(transcribe_btn)
        
        # Status label
        self.stt_status_label = Gtk.Label()
        self.stt_status_label.set_markup('<span size="medium">Ready</span>')
        self.stt_status_label.add_css_class("caption")
        # Make error messages more readable
        self.stt_status_label.set_margin_top(4)
        self.stt_status_label.set_margin_bottom(4)
        self.stt_status_label.set_wrap(True)
        box.append(self.stt_status_label)
        
        # Result display
        result_frame = Gtk.Frame(label="Transcription Result")
        result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        result_frame.set_child(result_box)
        result_frame.set_margin_top(12)
        
        self.stt_result_buffer = Gtk.TextBuffer()
        self.stt_result_view = Gtk.TextView(buffer=self.stt_result_buffer)
        self.stt_result_view.set_editable(False)
        self.stt_result_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.stt_result_view.set_size_request(-1, 200)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.stt_result_view)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        result_box.append(scrolled)
        box.append(result_frame)
        
        self.stt_file_path = None
        
        return box
    
    def _create_status_page(self):
        """Create service status page."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Title
        title = Gtk.Label(label="Service Status")
        title.add_css_class("title-2")
        box.append(title)
        
        # Refresh button
        refresh_btn = Gtk.Button(label="Refresh Status")
        refresh_btn.connect("clicked", self._on_refresh_status)
        box.append(refresh_btn)
        
        # Status display
        self.status_buffer = Gtk.TextBuffer()
        self.status_view = Gtk.TextView(buffer=self.status_buffer)
        self.status_view.set_editable(False)
        self.status_view.set_monospace(True)
        self.status_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.status_view)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(-1, 400)
        box.append(scrolled)
        
        # Initial status load
        self._on_refresh_status(None)
        
        return box
    
    def _on_tts_synthesize(self, button):
        """Handle TTS synthesize button click."""
        button.set_sensitive(False)
        self.tts_status_label.set_text("Checking gateway...")
        
        def synthesize():
            try:
                # First check if gateway is available
                if HAS_HTTPX:
                    try:
                        with httpx.Client(timeout=5.0) as client:
                            health_response = client.get(f"{self.gateway_url}/health")
                            if health_response.status_code != 200:
                                GLib.idle_add(self._tts_update_status, "Error: Gateway not responding", True)
                                GLib.idle_add(lambda: button.set_sensitive(True))
                                return
                    except Exception as e:
                        GLib.idle_add(self._tts_update_status, f"Error: Gateway not reachable - {str(e)}", True)
                        GLib.idle_add(lambda: button.set_sensitive(True))
                        return
                else:
                    import urllib.request
                    try:
                        with urllib.request.urlopen(f"{self.gateway_url}/health", timeout=5) as response:
                            if response.getcode() != 200:
                                GLib.idle_add(self._tts_update_status, "Error: Gateway not responding", True)
                                GLib.idle_add(lambda: button.set_sensitive(True))
                                return
                    except Exception as e:
                        GLib.idle_add(self._tts_update_status, f"Error: Gateway not reachable - {str(e)}", True)
                        GLib.idle_add(lambda: button.set_sensitive(True))
                        return
                
                GLib.idle_add(self._tts_update_status, "Synthesizing...", False)
                    # Get text and backend
                start_iter = self.tts_text_buffer.get_start_iter()
                end_iter = self.tts_text_buffer.get_end_iter()
                text = self.tts_text_buffer.get_text(start_iter, end_iter, False).strip()
                
                if not text:
                    GLib.idle_add(self._tts_update_status, "Error: No text entered", True)
                    GLib.idle_add(lambda: button.set_sensitive(True))
                    return
                
                backend = self.tts_backend_combo.get_active_text()
                
                # First switch to the selected backend if needed
                if HAS_HTTPX:
                    with httpx.Client(timeout=30.0) as client:
                        # Switch backend
                        try:
                            switch_response = client.post(
                                f"{self.gateway_url}/api/voice/tts/backends/{backend}/switch"
                            )
                            if switch_response.status_code != 200:
                                GLib.idle_add(self._tts_update_status, f"Warning: Could not switch to {backend}", True)
                        except Exception:
                            pass  # Continue even if switch fails
                        
                        # Now synthesize
                        response = client.post(
                            f"{self.gateway_url}/api/voice/tts",
                            json={"text": text, "voice": None},
                            headers={"Content-Type": "application/json"}
                        )
                        status_code = response.status_code
                        audio_data = response.content
                        response_text = response.text if hasattr(response, 'text') else ""
                else:
                    # Fallback using urllib
                    import urllib.request
                    import json
                    
                    # Switch backend
                    try:
                        switch_data = json.dumps({}).encode('utf-8')
                        switch_req = urllib.request.Request(
                            f"{self.gateway_url}/api/voice/tts/backends/{backend}/switch",
                            data=switch_data,
                            headers={"Content-Type": "application/json"},
                            method="POST"
                        )
                        with urllib.request.urlopen(switch_req, timeout=10) as switch_resp:
                            if switch_resp.getcode() != 200:
                                GLib.idle_add(self._tts_update_status, f"Warning: Could not switch to {backend}", True)
                    except Exception:
                        pass  # Continue even if switch fails
                    
                    # Synthesize
                    data = json.dumps({"text": text, "voice": None}).encode('utf-8')
                    req = urllib.request.Request(
                        f"{self.gateway_url}/api/voice/tts",
                        data=data,
                        headers={"Content-Type": "application/json"}
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=30) as response:
                            status_code = response.getcode()
                            audio_data = response.read()
                            response_text = ""
                    except urllib.error.HTTPError as e:
                        status_code = e.code
                        audio_data = e.read()
                        response_text = audio_data.decode('utf-8', errors='ignore')[:100]
                
                if status_code == 200:
                    # Save to temp file and play
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(audio_data)
                        temp_path = f.name
                    
                    # Play audio using system player
                    try:
                        subprocess.Popen(
                            ["paplay", temp_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        GLib.idle_add(self._tts_update_status, f"✓ Synthesized and playing ({backend})", False)
                    except FileNotFoundError:
                        # Try alternative players
                        for player in ["aplay", "ffplay", "mpv", "vlc"]:
                            try:
                                subprocess.Popen(
                                    [player, temp_path],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                                GLib.idle_add(self._tts_update_status, f"✓ Synthesized and playing ({backend})", False)
                                break
                            except FileNotFoundError:
                                continue
                        else:
                            GLib.idle_add(self._tts_update_status, f"✓ Synthesized (saved to {temp_path})", False)
                else:
                    # Try to parse error response
                    error_msg = f"Error {status_code}"
                    try:
                        if HAS_HTTPX:
                            error_json = response.json() if hasattr(response, 'json') else None
                            if error_json and 'detail' in error_json:
                                error_msg = f"Error: {error_json['detail']}"
                            elif response_text:
                                # Try to parse as JSON
                                import json
                                try:
                                    error_json = json.loads(response_text)
                                    if 'detail' in error_json:
                                        error_msg = f"Error: {error_json['detail']}"
                                    else:
                                        error_msg = f"Error: {response_text[:200]}"
                                except:
                                    error_msg = f"Error: {response_text[:200]}"
                        else:
                            # urllib fallback
                            import json
                            try:
                                error_json = json.loads(response_text)
                                if 'detail' in error_json:
                                    error_msg = f"Error: {error_json['detail']}"
                                else:
                                    error_msg = f"Error: {response_text[:200]}"
                            except:
                                error_msg = f"Error {status_code}: {response_text[:200]}"
                    except Exception as parse_error:
                        error_msg = f"Error {status_code}: {str(parse_error)}"
                    
                    GLib.idle_add(self._tts_update_status, error_msg, True)
            except Exception as e:
                GLib.idle_add(self._tts_update_status, f"Error: {str(e)}", True)
            finally:
                GLib.idle_add(lambda: button.set_sensitive(True))
        
        threading.Thread(target=synthesize, daemon=True).start()
    
    def _tts_update_status(self, message, is_error=False):
        """Update TTS status label."""
        self.tts_status_label.set_text(message)
        # Remove all error-related classes first
        self.tts_status_label.remove_css_class("error")
        self.tts_status_label.remove_css_class("error-text")
        
        if is_error and ("Error" in message or "error" in message.lower()):
            # Use a more readable error style - larger font, better contrast
            self.tts_status_label.add_css_class("error-text")
            # Set larger font size for errors
            self.tts_status_label.set_markup(f'<span size="large" weight="bold" foreground="#ff4444">{message}</span>')
        else:
            # Normal text - remove markup
            self.tts_status_label.set_markup(f'<span size="medium">{message}</span>')
        return False
    
    def _on_stt_select_file(self, button):
        """Handle STT file selection."""
        # Use GTK4's FileDialog API (recommended for GTK4)
        try:
            from gi.repository import Gio
            
            dialog = Gtk.FileDialog()
            dialog.set_title("Select Audio File")
            dialog.set_modal(True)
            
            # Create file filter for audio files
            audio_filter = Gtk.FileFilter()
            audio_filter.set_name("Audio Files")
            # Add MIME types
            audio_filter.add_mime_type("audio/wav")
            audio_filter.add_mime_type("audio/x-wav")
            audio_filter.add_mime_type("audio/mpeg")
            audio_filter.add_mime_type("audio/mp3")
            audio_filter.add_mime_type("audio/ogg")
            audio_filter.add_mime_type("audio/flac")
            audio_filter.add_mime_type("audio/x-flac")
            # Add file patterns (more reliable than MIME types)
            audio_filter.add_pattern("*.wav")
            audio_filter.add_pattern("*.WAV")
            audio_filter.add_pattern("*.mp3")
            audio_filter.add_pattern("*.MP3")
            audio_filter.add_pattern("*.ogg")
            audio_filter.add_pattern("*.OGG")
            audio_filter.add_pattern("*.flac")
            audio_filter.add_pattern("*.FLAC")
            
            # Also add an "All Files" filter so user can see everything
            all_filter = Gtk.FileFilter()
            all_filter.set_name("All Files")
            all_filter.add_pattern("*")
            
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(audio_filter)
            filters.append(all_filter)
            dialog.set_filters(filters)
            dialog.set_default_filter(audio_filter)
            
            def on_file_selected(dialog, result):
                try:
                    file = dialog.open_finish(result)
                    if file:
                        # Get file path
                        file_path = file.get_path()
                        if not file_path:
                            # Try to get URI and convert to path
                            uri = file.get_uri()
                            if uri:
                                from gi.repository import GLib
                                file_path = GLib.filename_from_uri(uri)[0]
                        
                        if file_path and os.path.exists(file_path):
                            self.stt_file_path = file_path
                            self.stt_file_label.set_text(Path(file_path).name)
                            self.stt_status_label.set_markup('<span size="medium">File selected</span>')
                        else:
                            self.stt_status_label.set_markup('<span size="medium" foreground="#ff4444">Error: Could not access selected file</span>')
                except Exception as e:
                    # User cancelled or error occurred
                    if "dismissed" not in str(e).lower() and "cancelled" not in str(e).lower():
                        logger.error(f"Error selecting file: {e}")
                        self.stt_status_label.set_markup(f'<span size="medium" foreground="#ff4444">Error: {str(e)}</span>')
            
            # Open dialog asynchronously
            dialog.open(self, None, on_file_selected)
        except Exception as e:
            # Fallback to FileChooserDialog if FileDialog fails
            logger.warning(f"FileDialog failed, using FileChooserDialog: {e}")
            dialog = Gtk.FileChooserDialog(
                title="Select Audio File",
                parent=self,
                action=Gtk.FileChooserAction.OPEN
            )
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Open", Gtk.ResponseType.ACCEPT)
            
            # Add audio file filters
            audio_filter = Gtk.FileFilter()
            audio_filter.set_name("Audio Files")
            # Add MIME types
            audio_filter.add_mime_type("audio/wav")
            audio_filter.add_mime_type("audio/x-wav")
            audio_filter.add_mime_type("audio/mpeg")
            audio_filter.add_mime_type("audio/mp3")
            audio_filter.add_mime_type("audio/ogg")
            audio_filter.add_mime_type("audio/flac")
            audio_filter.add_mime_type("audio/x-flac")
            # Add file patterns (more reliable than MIME types)
            audio_filter.add_pattern("*.wav")
            audio_filter.add_pattern("*.WAV")
            audio_filter.add_pattern("*.mp3")
            audio_filter.add_pattern("*.MP3")
            audio_filter.add_pattern("*.ogg")
            audio_filter.add_pattern("*.OGG")
            audio_filter.add_pattern("*.flac")
            audio_filter.add_pattern("*.FLAC")
            dialog.add_filter(audio_filter)
            
            # Also add an "All Files" filter
            all_filter = Gtk.FileFilter()
            all_filter.set_name("All Files")
            all_filter.add_pattern("*")
            dialog.add_filter(all_filter)
            
            def on_response(dialog, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    try:
                        file = dialog.get_file()
                        if file:
                            # Handle both local files and Gio.File objects
                            file_path = file.get_path()
                            if not file_path:
                                # Try to get URI and convert to path
                                uri = file.get_uri()
                                if uri:
                                    from gi.repository import GLib
                                    file_path = GLib.filename_from_uri(uri)[0]
                            
                            if file_path and os.path.exists(file_path):
                                self.stt_file_path = file_path
                                self.stt_file_label.set_text(Path(file_path).name)
                                self.stt_status_label.set_markup('<span size="medium">File selected</span>')
                            else:
                                self.stt_status_label.set_markup('<span size="medium" foreground="#ff4444">Error: Could not access selected file</span>')
                    except Exception as e:
                        logger.error(f"Error selecting file: {e}")
                        self.stt_status_label.set_markup(f'<span size="medium" foreground="#ff4444">Error: {str(e)}</span>')
                dialog.destroy()
            
            dialog.connect("response", on_response)
            dialog.show()
    
    def _on_stt_transcribe(self, button):
        """Handle STT transcribe button click."""
        if not self.stt_file_path or not os.path.exists(self.stt_file_path):
            self.stt_status_label.set_text("Error: No file selected")
            return
        
        button.set_sensitive(False)
        self.stt_status_label.set_text("Checking gateway...")
        self.stt_result_buffer.set_text("")
        
        def transcribe():
            try:
                # First check if gateway is available
                if HAS_HTTPX:
                    try:
                        with httpx.Client(timeout=5.0) as client:
                            health_response = client.get(f"{self.gateway_url}/health")
                            if health_response.status_code != 200:
                                GLib.idle_add(self._stt_update_status, "Error: Gateway not responding", True)
                                GLib.idle_add(lambda: button.set_sensitive(True))
                                return
                    except Exception as e:
                        GLib.idle_add(self._stt_update_status, f"Error: Gateway not reachable - {str(e)}", True)
                        GLib.idle_add(lambda: button.set_sensitive(True))
                        return
                else:
                    import urllib.request
                    try:
                        with urllib.request.urlopen(f"{self.gateway_url}/health", timeout=5) as response:
                            if response.getcode() != 200:
                                GLib.idle_add(self._stt_update_status, "Error: Gateway not responding", True)
                                GLib.idle_add(lambda: button.set_sensitive(True))
                                return
                    except Exception as e:
                        GLib.idle_add(self._stt_update_status, f"Error: Gateway not reachable - {str(e)}", True)
                        GLib.idle_add(lambda: button.set_sensitive(True))
                        return
                
                GLib.idle_add(self._stt_update_status, "Transcribing...", False)
                
                try:
                    if HAS_HTTPX:
                        with open(self.stt_file_path, "rb") as f:
                            files = {"audio": (os.path.basename(self.stt_file_path), f, "audio/wav")}
                            
                            with httpx.Client(timeout=60.0) as client:
                                response = client.post(
                                    f"{self.gateway_url}/api/voice/stt",
                                    files=files
                                )
                                
                                if response.status_code == 200:
                                    result = response.json()
                                    text = result.get("text", "No transcription available")
                                    GLib.idle_add(self._stt_update_result, text, True)
                                    GLib.idle_add(self._stt_update_status, "✓ Transcription complete", True)
                                else:
                                    error_msg = f"Error: {response.status_code} - {response.text[:100]}"
                                    GLib.idle_add(self._stt_update_status, error_msg, True)
                    else:
                        # Fallback using urllib with multipart/form-data
                        import urllib.request
                        import json
                        import mimetypes
                        
                        # Read file
                        with open(self.stt_file_path, "rb") as f:
                            file_data = f.read()
                        
                        # Create multipart form data
                        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
                        body = []
                        body.append(f"--{boundary}".encode())
                        body.append(f'Content-Disposition: form-data; name="audio"; filename="{os.path.basename(self.stt_file_path)}"'.encode())
                        body.append(f"Content-Type: audio/wav".encode())
                        body.append(b"")
                        body.append(file_data)
                        body.append(f"--{boundary}--".encode())
                        body_data = b"\r\n".join(body)
                        
                        req = urllib.request.Request(
                            f"{self.gateway_url}/api/voice/stt",
                            data=body_data,
                            headers={
                                "Content-Type": f"multipart/form-data; boundary={boundary}",
                                "Content-Length": str(len(body_data))
                            }
                        )
                        
                        try:
                            with urllib.request.urlopen(req, timeout=60) as response:
                                status_code = response.getcode()
                                if status_code == 200:
                                    result = json.loads(response.read().decode())
                                    text = result.get("text", "No transcription available")
                                    GLib.idle_add(self._stt_update_result, text, True)
                                    GLib.idle_add(self._stt_update_status, "✓ Transcription complete", True)
                                else:
                                    error_msg = f"Error: {status_code}"
                                    GLib.idle_add(self._stt_update_status, error_msg, True)
                        except urllib.error.HTTPError as e:
                            error_msg = f"Error: {e.code} - {e.read().decode()[:100]}"
                            GLib.idle_add(self._stt_update_status, error_msg, True)
                except Exception as e:
                    GLib.idle_add(self._stt_update_status, f"Error: {str(e)}", True)
                finally:
                    GLib.idle_add(lambda: button.set_sensitive(True))
            except Exception as e:
                GLib.idle_add(self._stt_update_status, f"Error: {str(e)}", True)
            finally:
                GLib.idle_add(lambda: button.set_sensitive(True))
        
        threading.Thread(target=transcribe, daemon=True).start()
    
    def _stt_update_status(self, message, is_success=False):
        """Update STT status label."""
        # Remove all error-related classes first
        self.stt_status_label.remove_css_class("error")
        self.stt_status_label.remove_css_class("error-text")
        
        if "Error" in message or "error" in message.lower():
            # Use a more readable error style - larger font, better contrast
            self.stt_status_label.add_css_class("error-text")
            # Set larger font size for errors
            self.stt_status_label.set_markup(f'<span size="large" weight="bold" foreground="#ff4444">{message}</span>')
        else:
            # Normal text - remove markup
            self.stt_status_label.set_markup(f'<span size="medium">{message}</span>')
        return False
    
    def _stt_update_result(self, text, success):
        """Update STT result display."""
        self.stt_result_buffer.set_text(text)
        return False
    
    def _on_refresh_status(self, button):
        """Refresh service status."""
        if button:
            button.set_sensitive(False)
        
        def fetch_status():
            status_text = "=== Gateway Connection Check ===\n\n"
            
            # First check if gateway is reachable
            gateway_available = False
            try:
                if HAS_HTTPX:
                    with httpx.Client(timeout=5.0) as client:
                        health_response = client.get(f"{self.gateway_url}/health")
                        if health_response.status_code == 200:
                            gateway_available = True
                            status_text += "✓ Gateway is running and responding\n"
                        else:
                            status_text += f"⚠ Gateway responded with status {health_response.status_code}\n"
                else:
                    import urllib.request
                    with urllib.request.urlopen(f"{self.gateway_url}/health", timeout=5) as response:
                        if response.getcode() == 200:
                            gateway_available = True
                            status_text += "✓ Gateway is running and responding\n"
                        else:
                            status_text += f"⚠ Gateway responded with status {response.getcode()}\n"
            except Exception as e:
                status_text += f"✗ Gateway is NOT running or not reachable\n"
                status_text += f"  Error: {str(e)}\n"
                status_text += f"\n  Make sure the Gateway service is started in the launcher.\n"
                status_text += f"  Gateway should be running on: {self.gateway_url}\n"
                GLib.idle_add(self._update_status_display, status_text)
                if button:
                    GLib.idle_add(lambda: button.set_sensitive(True))
                return
            
            if not gateway_available:
                status_text += "\n⚠ Gateway health check failed. Services may not be initialized.\n"
                GLib.idle_add(self._update_status_display, status_text)
                if button:
                    GLib.idle_add(lambda: button.set_sensitive(True))
                return
            
            status_text += "\n=== Service Status ===\n\n"
            
            try:
                if HAS_HTTPX:
                    with httpx.Client(timeout=10.0) as client:
                        # Get service status
                        try:
                            status_response = client.get(f"{self.gateway_url}/api/services/status")
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                status_text += f"STT: {status_data.get('stt', {}).get('status', 'unknown')}\n"
                                tts_data = status_data.get('tts', {})
                                for backend, info in tts_data.items():
                                    status_text += f"TTS {backend}: {info.get('status', 'unknown')}\n"
                            else:
                                status_text += f"Error fetching status: {status_response.status_code}\n"
                        except Exception as e:
                            status_text += f"Error fetching status: {str(e)}\n"
                        
                        status_text += "\n=== Detailed Debug Info ===\n\n"
                        
                        try:
                            debug_response = client.get(f"{self.gateway_url}/api/debug/info")
                            if debug_response.status_code == 200:
                                debug_data = debug_response.json()
                                import json
                                status_text += json.dumps(debug_data, indent=2)
                            else:
                                status_text += f"Error fetching debug info: {debug_response.status_code}\n"
                        except Exception as e:
                            status_text += f"Error fetching debug info: {str(e)}\n"
                else:
                    # Fallback using urllib
                    import urllib.request
                    import json
                    
                    try:
                        with urllib.request.urlopen(f"{self.gateway_url}/api/services/status", timeout=10) as response:
                            if response.getcode() == 200:
                                status_data = json.loads(response.read().decode())
                                status_text += f"STT: {status_data.get('stt', {}).get('status', 'unknown')}\n"
                                tts_data = status_data.get('tts', {})
                                for backend, info in tts_data.items():
                                    status_text += f"TTS {backend}: {info.get('status', 'unknown')}\n"
                            else:
                                status_text += f"Error fetching status: {response.getcode()}\n"
                    except Exception as e:
                        status_text += f"Error fetching status: {str(e)}\n"
                    
                    status_text += "\n=== Detailed Debug Info ===\n\n"
                    
                    try:
                        with urllib.request.urlopen(f"{self.gateway_url}/api/debug/info", timeout=10) as response:
                            if response.getcode() == 200:
                                debug_data = json.loads(response.read().decode())
                                status_text += json.dumps(debug_data, indent=2)
                            else:
                                status_text += f"Error fetching debug info: {response.getcode()}\n"
                    except Exception as e:
                        status_text += f"Error fetching debug info: {str(e)}\n"
                
                GLib.idle_add(self._update_status_display, status_text)
            except Exception as e:
                GLib.idle_add(self._update_status_display, f"Error: {str(e)}")
            finally:
                if button:
                    GLib.idle_add(lambda: button.set_sensitive(True))
        
        threading.Thread(target=fetch_status, daemon=True).start()
    
    def _update_status_display(self, text):
        """Update status display."""
        self.status_buffer.set_text(text)
        return False

