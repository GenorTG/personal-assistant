"""Models view component for launcher."""
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

# Add launcher directory to path
launcher_dir = Path(__file__).parent.parent
sys.path.insert(0, str(launcher_dir))

from config import PROJECT_ROOT


class ModelsView(Gtk.Box):
    """View showing downloaded models and their tool calling support."""
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        title_label = Gtk.Label(label="Downloaded Models")
        title_label.set_xalign(0)
        title_label.add_css_class("title")
        title_label.set_margin_bottom(8)
        header.append(title_label)
        
        # Refresh button
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self._on_refresh)
        header.append(refresh_button)
        
        self.append(header)
        
        # Scrolled window for model list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        
        # Model list container
        self.models_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scrolled.set_child(self.models_box)
        
        self.append(scrolled)
        
        # Status label
        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.status_label.add_css_class("dim-label")
        self.append(self.status_label)
        
        # Load models initially
        self._load_models()
    
    def _on_refresh(self, button):
        """Refresh the models list."""
        self._load_models()
    
    def _load_models(self):
        """Load and display models."""
        # Clear existing models
        child = self.models_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.models_box.remove(child)
            child = next_child
        
        # Find models directory
        models_dir = PROJECT_ROOT / "services" / "data" / "models"
        if not models_dir.exists():
            self.status_label.set_text("No models directory found")
            return
        
        # Find all GGUF files
        gguf_files = list(models_dir.glob("**/*.gguf"))
        
        if not gguf_files:
            self.status_label.set_text("No models found")
            return
        
        # Load model info
        models = []
        for gguf_file in sorted(gguf_files):
            model_info = self._get_model_info(gguf_file, models_dir)
            if model_info:
                models.append(model_info)
        
        # Display models
        if not models:
            self.status_label.set_text("No models with metadata found")
            return
        
        for model in models:
            row = self._create_model_row(model)
            self.models_box.append(row)
        
        # Update status
        with_tools = sum(1 for m in models if m.get("supports_tool_calling"))
        self.status_label.set_text(
            f"Found {len(models)} model(s) - {with_tools} with tool calling support"
        )
    
    def _get_model_info(self, gguf_file: Path, models_dir: Path) -> Optional[Dict[str, Any]]:
        """Get model information from file and metadata."""
        try:
            # Get file size
            file_size = gguf_file.stat().st_size
            size_gb = file_size / (1024 ** 3)
            size_mb = file_size / (1024 ** 2)
            
            # Try to load metadata from model_info.json
            metadata_file = gguf_file.parent / "model_info.json"
            metadata = {}
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except Exception as e:
                    print(f"Error reading metadata for {gguf_file.name}: {e}", file=sys.stderr)
            
            # Get model name
            model_name = metadata.get("name") or gguf_file.stem
            
            # Get tool calling info
            tool_calling = metadata.get("tool_calling", {})
            supports_tool_calling = tool_calling.get("supports_tool_calling", False)
            suggested_format = tool_calling.get("suggested_chat_format")
            detection_method = tool_calling.get("detection_method", "unknown")
            
            # Get architecture
            architecture = metadata.get("architecture") or "Unknown"
            
            # Get relative path for display
            try:
                relative_path = gguf_file.relative_to(models_dir)
                model_id = str(relative_path)
            except ValueError:
                model_id = gguf_file.name
            
            return {
                "name": model_name,
                "filename": gguf_file.name,
                "path": str(gguf_file),
                "model_id": model_id,
                "size_gb": size_gb,
                "size_mb": size_mb,
                "supports_tool_calling": supports_tool_calling,
                "suggested_format": suggested_format,
                "detection_method": detection_method,
                "architecture": architecture,
                "repo_id": metadata.get("repo_id"),
                "author": metadata.get("author"),
            }
        except Exception as e:
            print(f"Error getting model info for {gguf_file.name}: {e}", file=sys.stderr)
            return None
    
    def _create_model_row(self, model: Dict[str, Any]) -> Gtk.Box:
        """Create a row widget for a model."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        row.add_css_class("model-row")
        
        # Add border
        row.add_css_class("frame")
        
        # Top row: Name and tool calling badge
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Model name
        name_label = Gtk.Label(label=model["name"])
        name_label.set_xalign(0)
        name_label.add_css_class("title-4")
        name_label.set_hexpand(True)
        top_row.append(name_label)
        
        # Tool calling badge
        if model.get("supports_tool_calling"):
            tool_badge = Gtk.Label(label="✓ Tools")
            tool_badge.add_css_class("success")
            # Make it green
            css_provider = Gtk.CssProvider()
            css = b"label.success { color: #22c55e; font-weight: bold; }"
            css_provider.load_from_data(css)
            tool_badge.get_style_context().add_provider(
                css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        else:
            tool_badge = Gtk.Label(label="✗ No Tools")
            tool_badge.add_css_class("dim-label")
        
        top_row.append(tool_badge)
        row.append(top_row)
        
        # Details row
        details_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        # Size
        if model["size_gb"] >= 1:
            size_text = f"{model['size_gb']:.2f} GB"
        else:
            size_text = f"{model['size_mb']:.1f} MB"
        
        size_label = Gtk.Label(label=f"Size: {size_text}")
        size_label.set_xalign(0)
        size_label.add_css_class("dim-label")
        details_row.append(size_label)
        
        # Architecture
        arch_label = Gtk.Label(label=f"Arch: {model['architecture']}")
        arch_label.set_xalign(0)
        arch_label.add_css_class("dim-label")
        details_row.append(arch_label)
        
        # Tool calling format (if available)
        if model.get("suggested_format"):
            format_label = Gtk.Label(label=f"Format: {model['suggested_format']}")
            format_label.set_xalign(0)
            format_label.add_css_class("dim-label")
            details_row.append(format_label)
        
        row.append(details_row)
        
        # Filename (smaller, dimmed)
        filename_label = Gtk.Label(label=f"File: {model['filename']}")
        filename_label.set_xalign(0)
        filename_label.add_css_class("dim-label")
        filename_label.add_css_class("caption")
        row.append(filename_label)
        
        return row


