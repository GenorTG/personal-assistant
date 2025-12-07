"""TTS Testing UI for the launcher."""
import customtkinter as ctk
import requests
import threading
import tempfile
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List


class TTSTestPanel(ctk.CTkFrame):
    """Panel for testing TTS services."""
    
    def __init__(self, parent, colors: Dict[str, str], log_callback):
        super().__init__(parent, fg_color=colors["bg_panel"])
        self.colors = colors
        self.log_callback = log_callback
        self.gateway_url = "http://localhost:8000"
        self.current_backend: Optional[str] = None
        self.available_backends: List[Dict[str, Any]] = []
        self.voices: List[Dict[str, Any]] = []
        self.test_audio_file: Optional[str] = None
        
        self._create_ui()
        # Don't auto-load - wait for gateway to be ready
        # User can click Refresh when services are running
    
    def _create_ui(self):
        """Create the TTS test UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="TTS Service Testing",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        # Main content frame
        content = ctk.CTkFrame(self, fg_color=self.colors["bg_card"])
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(3, weight=1)
        
        # Backend selection
        backend_frame = ctk.CTkFrame(content, fg_color="transparent")
        backend_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        backend_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            backend_frame,
            text="TTS Backend:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"]
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        self.backend_var = ctk.StringVar(value="")
        self.backend_dropdown = ctk.CTkComboBox(
            backend_frame,
            values=[],
            variable=self.backend_var,
            command=self._on_backend_selected,
            width=200
        )
        self.backend_dropdown.grid(row=0, column=1, sticky="w")
        
        self.refresh_btn = ctk.CTkButton(
            backend_frame,
            text="Load Backends",
            command=self._load_backends,
            width=120,
            height=32,
            fg_color=self.colors["accent_blue"],
            hover_color="#0063B1"
        )
        self.refresh_btn.grid(row=0, column=2, padx=(10, 0))
        
        # Gateway status indicator
        self.gateway_status_label = ctk.CTkLabel(
            backend_frame,
            text="Gateway: Not checked",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_secondary"]
        )
        self.gateway_status_label.grid(row=0, column=3, padx=(10, 0))
        
        # Voice selection
        voice_frame = ctk.CTkFrame(content, fg_color="transparent")
        voice_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=15)
        voice_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            voice_frame,
            text="Voice:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"]
        ).grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        self.voice_var = ctk.StringVar(value="")
        self.voice_dropdown = ctk.CTkComboBox(
            voice_frame,
            values=[],
            variable=self.voice_var,
            width=200,
            state="disabled"  # Disabled until voices are loaded
        )
        self.voice_dropdown.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        # Refresh voices button
        self.refresh_voices_btn = ctk.CTkButton(
            voice_frame,
            text="Refresh Voices",
            command=lambda: self._load_voices(refresh=True),
            width=120,
            height=32,
            fg_color=self.colors["accent_blue"],
            hover_color="#0063B1",
            state="disabled"  # Disabled until backend is selected
        )
        self.refresh_voices_btn.grid(row=0, column=2, padx=(0, 0))
        
        # Test text input
        text_frame = ctk.CTkFrame(content, fg_color="transparent")
        text_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=15)
        text_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(
            text_frame,
            text="Test Text:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.test_text = ctk.CTkTextbox(
            text_frame,
            height=100,
            font=ctk.CTkFont(size=12)
        )
        self.test_text.insert("1.0", "Hello, this is a test of the text-to-speech system.")
        self.test_text.grid(row=1, column=0, sticky="ew")
        
        # Test button and status
        button_frame = ctk.CTkFrame(content, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=15)
        button_frame.grid_columnconfigure(1, weight=1)
        
        self.test_btn = ctk.CTkButton(
            button_frame,
            text="Test TTS",
            command=self._test_tts,
            width=150,
            height=40,
            fg_color=self.colors["accent_blue"],
            hover_color="#0063B1"
        )
        self.test_btn.grid(row=0, column=0, padx=(0, 10))
        
        self.status_label = ctk.CTkLabel(
            button_frame,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"]
        )
        self.status_label.grid(row=0, column=1, sticky="w")
        
        self.play_btn = ctk.CTkButton(
            button_frame,
            text="Play Audio",
            command=self._play_audio,
            width=120,
            height=40,
            fg_color=self.colors["accent_green"],
            hover_color="#0E6B0E",
            state="disabled"
        )
        self.play_btn.grid(row=0, column=2, padx=(10, 0))
    
    def _check_gateway(self) -> bool:
        """Check if gateway is available."""
        try:
            response = requests.get(f"{self.gateway_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def _load_backends(self):
        """Load available TTS backends."""
        def _run():
            try:
                # First check if gateway is available
                self.gateway_status_label.configure(text="Gateway: Checking...", text_color=self.colors["accent_orange"])
                self.refresh_btn.configure(state="disabled")
                
                if not self._check_gateway():
                    self.gateway_status_label.configure(
                        text="Gateway: Not available (start gateway service first)",
                        text_color=self.colors["accent_red"]
                    )
                    self.status_label.configure(
                        text="Gateway service not running. Start the gateway service first.",
                        text_color=self.colors["accent_red"]
                    )
                    self.log_callback("Gateway service not available. Please start the gateway service first.")
                    return
                
                self.gateway_status_label.configure(text="Gateway: Available", text_color=self.colors["accent_green"])
                self.log_callback("Loading TTS backends...")
                
                response = requests.get(f"{self.gateway_url}/api/voice/tts/backends", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self.available_backends = data.get("backends", [])
                    
                    backend_names = []
                    for backend in self.available_backends:
                        name = backend.get("name", "unknown")
                        status = backend.get("status", "unknown")
                        error_msg = backend.get("error_message")
                        
                        # Only show status if it's not an error (errors are shown separately)
                        # For errors, just show the name with a visual indicator
                        if status == "error" and error_msg:
                            backend_names.append(f"{name} ⚠")
                        elif status == "ready":
                            backend_names.append(f"{name} ✓")
                        elif status == "not_initialized":
                            # Check if service is actually running (might be ready but not initialized)
                            backend_names.append(f"{name}")
                        else:
                            backend_names.append(f"{name} ({status})")
                    
                    self.backend_dropdown.configure(values=backend_names)
                    if backend_names:
                        self.backend_dropdown.set(backend_names[0])
                        self._on_backend_selected(backend_names[0])
                    
                    self.log_callback(f"Loaded {len(self.available_backends)} TTS backends")
                    self.status_label.configure(text="Backends loaded successfully", text_color=self.colors["accent_green"])
                else:
                    self.log_callback(f"Failed to load backends: {response.status_code}")
                    self.status_label.configure(text="Failed to load backends", text_color=self.colors["accent_red"])
            except requests.exceptions.ConnectionError:
                self.gateway_status_label.configure(
                    text="Gateway: Connection refused (not running)",
                    text_color=self.colors["accent_red"]
                )
                self.status_label.configure(
                    text="Gateway service not running. Start the gateway service first.",
                    text_color=self.colors["accent_red"]
                )
                self.log_callback("Cannot connect to gateway. Please start the gateway service first.")
            except Exception as e:
                self.log_callback(f"Error loading backends: {e}")
                self.status_label.configure(text=f"Error: {e}", text_color=self.colors["accent_red"])
                self.gateway_status_label.configure(text="Gateway: Error", text_color=self.colors["accent_red"])
            finally:
                self.refresh_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()
    
    def _on_backend_selected(self, selection: str):
        """Handle backend selection."""
        if not selection:
            return
        
        # Extract backend name from selection
        # Handle formats: "name ✓", "name ⚠", "name (status)", or just "name"
        backend_name = selection
        if " ✓" in backend_name:
            backend_name = backend_name.split(" ✓")[0]
        elif " ⚠" in backend_name:
            backend_name = backend_name.split(" ⚠")[0]
        elif " (" in backend_name:
            backend_name = backend_name.split(" (")[0]
        backend_name = backend_name.strip().lower()
        
        # Find backend info
        backend_info = None
        for backend in self.available_backends:
            if backend.get("name", "").lower() == backend_name:
                backend_info = backend
                break
        
        if not backend_info:
            return
        
        self.current_backend = backend_name
        self.log_callback(f"Selected backend: {backend_name}")
        
        # Clear voice dropdown and enable refresh button
        self.voice_dropdown.configure(values=[], state="disabled")
        self.voice_var.set("")
        self.voices = []
        self.refresh_voices_btn.configure(state="normal")
        
        # Switch to this backend (but don't auto-load voices)
        def _switch():
            try:
                self.log_callback(f"Switching to {backend_name}...")
                response = requests.post(
                    f"{self.gateway_url}/api/voice/tts/backends/{backend_name}/switch",
                    timeout=10
                )
                if response.status_code == 200:
                    self.log_callback(f"Switched to {backend_name}. Click 'Refresh Voices' to load voices.")
                else:
                    self.log_callback(f"Failed to switch backend: {response.status_code}")
                    self.refresh_voices_btn.configure(state="disabled")
            except Exception as e:
                self.log_callback(f"Error switching backend: {e}")
                self.refresh_voices_btn.configure(state="disabled")
        
        threading.Thread(target=_switch, daemon=True).start()
    
    def _load_voices(self, refresh: bool = False):
        """Load voices for the current backend."""
        if not self.current_backend:
            self.status_label.configure(
                text="Select a backend first",
                text_color=self.colors["accent_red"]
            )
            return
        
        # Disable button while loading
        self.refresh_voices_btn.configure(state="disabled")
        self.voice_dropdown.configure(state="disabled", values=[])
        self.voice_var.set("")
        
        def _run():
            try:
                if refresh:
                    self.log_callback(f"Refreshing voices for {self.current_backend} (hot-reload)...")
                    self.status_label.configure(
                        text="Refreshing voices...",
                        text_color=self.colors["accent_orange"]
                    )
                    # Call refresh endpoint first
                    refresh_response = requests.post(
                        f"{self.gateway_url}/api/voice/tts/backends/{self.current_backend}/voices/refresh",
                        timeout=10
                    )
                    if refresh_response.status_code == 200:
                        refresh_data = refresh_response.json()
                        reload_stats = refresh_data.get("reload_stats", {})
                        if reload_stats:
                            added = reload_stats.get("added", 0)
                            removed = reload_stats.get("removed", 0)
                            if added > 0 or removed > 0:
                                self.log_callback(f"Voice reload: {added} added, {removed} removed")
                    else:
                        self.log_callback(f"Refresh endpoint returned {refresh_response.status_code}, continuing anyway...")
                else:
                    self.log_callback(f"Loading voices for {self.current_backend}...")
                    self.status_label.configure(
                        text="Loading voices...",
                        text_color=self.colors["accent_orange"]
                    )
                
                # Now fetch the voices
                response = requests.get(
                    f"{self.gateway_url}/api/voice/tts/backends/{self.current_backend}/voices",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    self.voices = data.get("voices", [])
                    
                    # Store voices with both ID and name for lookup
                    voice_options = []
                    for voice in self.voices:
                        voice_id = voice.get("id", "unknown")
                        voice_name = voice.get("name", voice_id)
                        # Store as "name (id)" format so we can extract ID later
                        voice_options.append(f"{voice_name} ({voice_id})")
                    
                    if voice_options:
                        self.voice_dropdown.configure(values=voice_options, state="normal")
                        self.voice_dropdown.set(voice_options[0])
                        self.status_label.configure(
                            text=f"Loaded {len(self.voices)} voices",
                            text_color=self.colors["accent_green"]
                        )
                        self.log_callback(f"Loaded {len(self.voices)} voices")
                    else:
                        self.voice_dropdown.configure(values=[], state="disabled")
                        self.status_label.configure(
                            text="No voices available",
                            text_color=self.colors["accent_orange"]
                        )
                        self.log_callback(f"No voices found for {self.current_backend}")
                else:
                    error_text = response.text[:100] if response.text else f"Status {response.status_code}"
                    self.status_label.configure(
                        text=f"Failed to load voices: {response.status_code}",
                        text_color=self.colors["accent_red"]
                    )
                    self.log_callback(f"Failed to load voices: {response.status_code} - {error_text}")
            except Exception as e:
                self.status_label.configure(
                    text=f"Error: {str(e)[:50]}",
                    text_color=self.colors["accent_red"]
                )
                self.log_callback(f"Error loading voices: {e}")
            finally:
                # Re-enable refresh button
                self.refresh_voices_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()
    
    def _test_tts(self):
        """Test TTS generation."""
        # Check gateway first
        if not self._check_gateway():
            self.status_label.configure(
                text="Gateway not available. Start gateway service first.",
                text_color=self.colors["accent_red"]
            )
            return
        
        if not self.current_backend:
            self.status_label.configure(text="No backend selected", text_color=self.colors["accent_red"])
            return
        
        text = self.test_text.get("1.0", "end-1c").strip()
        if not text:
            self.status_label.configure(text="No text entered", text_color=self.colors["accent_red"])
            return
        
        voice_selection = self.voice_var.get()
        voice = None
        if voice_selection:
            # Extract voice ID from selection format: "name (id)" or just "id"
            if " (" in voice_selection and voice_selection.endswith(")"):
                # Format: "Default Voice (default)" - extract ID from parentheses
                voice = voice_selection.split(" (")[-1].rstrip(")")
            else:
                # Might be just the ID or name, try to find it in voices list
                for v in self.voices:
                    voice_id = v.get("id", "")
                    voice_name = v.get("name", "")
                    if voice_id == voice_selection or voice_name == voice_selection:
                        voice = voice_id
                        break
                # If still not found, use as-is (might be an ID already)
                if not voice:
                    voice = voice_selection
        else:
            # No voice selected, use default
            voice = "default"
        
        def _run():
            try:
                self.test_btn.configure(state="disabled")
                self.status_label.configure(text="Generating...", text_color=self.colors["accent_orange"])
                self.log_callback(f"Testing TTS with backend: {self.current_backend}, voice: {voice or 'default'}")
                
                # Make the same request the frontend makes
                response = requests.post(
                    f"{self.gateway_url}/api/voice/tts",
                    json={"text": text, "voice": voice if voice else None},
                    timeout=60,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    # Save audio to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(response.content)
                        self.test_audio_file = f.name
                    
                    self.status_label.configure(text="✓ Success! Audio generated", text_color=self.colors["accent_green"])
                    self.play_btn.configure(state="normal")
                    self.log_callback(f"TTS test successful! Audio saved to: {self.test_audio_file}")
                else:
                    error_msg = f"TTS failed: {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("detail", error_msg)
                    except:
                        error_msg = response.text[:100] if response.text else error_msg
                    
                    self.status_label.configure(text=error_msg, text_color=self.colors["accent_red"])
                    self.log_callback(f"TTS test failed: {error_msg}")
            except Exception as e:
                self.status_label.configure(text=f"Error: {e}", text_color=self.colors["accent_red"])
                self.log_callback(f"TTS test error: {e}")
            finally:
                self.test_btn.configure(state="normal")
        
        threading.Thread(target=_run, daemon=True).start()
    
    def _play_audio(self):
        """Play the generated audio file."""
        if not self.test_audio_file or not os.path.exists(self.test_audio_file):
            self.status_label.configure(text="No audio file available", text_color=self.colors["accent_red"])
            return
        
        def _run():
            try:
                self.log_callback(f"Playing audio: {self.test_audio_file}")
                
                if platform.system() == "Windows":
                    # Windows: use start command to play with default player
                    os.startfile(self.test_audio_file)
                elif platform.system() == "Darwin":
                    # macOS: use open command
                    subprocess.run(["open", self.test_audio_file], check=False)
                else:
                    # Linux: try various players
                    players = ["xdg-open", "aplay", "paplay", "play"]
                    for player in players:
                        try:
                            subprocess.run([player, self.test_audio_file], check=False, timeout=5)
                            break
                        except (FileNotFoundError, subprocess.TimeoutExpired):
                            continue
                
                self.log_callback("Audio playback started")
            except Exception as e:
                self.log_callback(f"Error playing audio: {e}")
                self.status_label.configure(text=f"Playback error: {e}", text_color=self.colors["accent_red"])
        
        threading.Thread(target=_run, daemon=True).start()
    
    def cleanup(self):
        """Clean up temporary files."""
        if self.test_audio_file and os.path.exists(self.test_audio_file):
            try:
                os.unlink(self.test_audio_file)
            except Exception:
                pass

