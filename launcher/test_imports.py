#!/usr/bin/env python3
"""Test script to verify all launcher imports work correctly."""

import sys
from pathlib import Path

# Add launcher directory to path
launcher_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(launcher_dir))

print(f"Launcher directory: {launcher_dir}")
print(f"Python path (first 3): {sys.path[:3]}")
print()

errors = []

# Test imports
try:
    print("Testing ui.console...")
    from ui.console import ConsoleRedirector
    print("  ✓ ui.console imported successfully")
except Exception as e:
    error = f"  ✗ ui.console failed: {e}"
    print(error)
    errors.append(error)

try:
    print("Testing ui.logging...")
    from ui.logging import UILogger
    print("  ✓ ui.logging imported successfully")
except Exception as e:
    error = f"  ✗ ui.logging failed: {e}"
    print(error)
    errors.append(error)

try:
    print("Testing process.process_group...")
    from process.process_group import ProcessGroupManager
    print("  ✓ process.process_group imported successfully")
except Exception as e:
    error = f"  ✗ process.process_group failed: {e}"
    print(error)
    errors.append(error)

try:
    print("Testing process.process_utils...")
    from process.process_utils import kill_process_tree, kill_process_on_port
    print("  ✓ process.process_utils imported successfully")
except Exception as e:
    error = f"  ✗ process.process_utils failed: {e}"
    print(error)
    errors.append(error)

try:
    print("Testing install.chatterbox_cuda...")
    from install.chatterbox_cuda import ChatterboxCudaInstaller
    print("  ✓ install.chatterbox_cuda imported successfully")
except Exception as e:
    error = f"  ✗ install.chatterbox_cuda failed: {e}"
    print(error)
    errors.append(error)

try:
    print("Testing manager...")
    from manager import ServiceManager, ServiceStatus
    print("  ✓ manager imported successfully")
except Exception as e:
    error = f"  ✗ manager failed: {e}"
    print(error)
    errors.append(error)

print()
if errors:
    print("=" * 60)
    print("IMPORT ERRORS FOUND:")
    print("=" * 60)
    for error in errors:
        print(error)
    print("=" * 60)
    sys.exit(1)
else:
    print("=" * 60)
    print("ALL IMPORTS SUCCESSFUL!")
    print("=" * 60)
    sys.exit(0)

