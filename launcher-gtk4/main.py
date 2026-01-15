#!/usr/bin/env python3
"""GTK4 launcher for Personal Assistant."""
import sys
import os
import signal
import atexit
from pathlib import Path

# Add current directory to path so we can import modules
launcher_dir = Path(__file__).parent
sys.path.insert(0, str(launcher_dir))

# Ensure we have display access
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':0'

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from ui.main_window import MainWindow

# Global service manager for cleanup
_service_manager = None


def cleanup_services():
    """Cleanup function to stop all services."""
    global _service_manager
    if _service_manager:
        try:
            _service_manager.stop_all_services()
        except Exception as e:
            print(f"Error during cleanup: {e}", file=sys.stderr)

def signal_handler(signum, frame):
    """Handle termination signals."""
    print(f"\nReceived signal {signum}, cleaning up services...", file=sys.stderr)
    cleanup_services()
    sys.exit(0)

def main():
    """Entry point."""
    global _service_manager
    
    # Register cleanup handlers
    atexit.register(cleanup_services)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        app = Gtk.Application(application_id="com.personalassistant.launcher")

        window = None

        def on_startup(app):
            print("Application startup - creating window", file=sys.stderr)
            nonlocal window
            global _service_manager
            try:
                window = MainWindow(app)
                # Store service manager reference for cleanup
                _service_manager = window.service_manager
                window.present()
                print("Window created during startup", file=sys.stderr)
            except Exception as e:
                print(f"Error creating window: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                app.quit()

        def on_activate(app):
            print("Application activated", file=sys.stderr)
            if window:
                window.present()
        
        def on_shutdown(app):
            """Called when application is shutting down."""
            print("Application shutting down, cleaning up services...", file=sys.stderr)
            cleanup_services()

        app.connect("startup", on_startup)
        app.connect("activate", on_activate)
        app.connect("shutdown", on_shutdown)

        # Run the main loop - window will be created during startup
        exit_code = app.run()
        return exit_code
    except KeyboardInterrupt:
        cleanup_services()
        return 0
    except Exception as e:
        print(f"Error starting launcher: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        cleanup_services()
        return 1


if __name__ == "__main__":
    sys.exit(main())
