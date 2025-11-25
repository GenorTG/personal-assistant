#!/usr/bin/env python3
"""
Test script for Chatterbox external service integration.
Tests automatic cloning, setup, and basic functionality.
"""

import sys
from pathlib import Path

# Add launcher to path
sys.path.insert(0, str(Path(__file__).parent / "launcher"))

from external_services_manager import ExternalServicesManager
from pathlib import Path

def test_external_services():
    """Test external services manager."""
    print("=" * 60)
    print("Testing Chatterbox TTS External Service Integration")
    print("=" * 60)
    
    root_dir = Path(__file__).parent
    ext_mgr = ExternalServicesManager(root_dir)
    
    # Test 1: Clone chatterbox repo
    print("\n[TEST 1] Cloning Chatterbox TTS API...")
    repo_url = "https://github.com/travisvn/chatterbox-tts-api"
    service_name = "chatterbox"
    target_dir = root_dir / "external_services" / "chatterbox-tts-api"
    
    result = ext_mgr.ensure_service_cloned(repo_url, service_name, target_dir)
    
    if result:
        print("✓ Chatterbox repository cloned/verified successfully")
    else:
        print("✗ Failed to clone Chatterbox repository")
        return False
    
    # Test 2: Setup service
    print("\n[TEST 2] Setting up Chatterbox service...")
    result = ext_mgr.setup_service(service_name, target_dir)
    
    if result:
        print("✓ Chatterbox service setup successfully")
    else:
        print("✗ Failed to setup Chatterbox service")
        return False
    
    # Test 3: Get service info
    print("\n[TEST 3] Getting service information...")
    info = ext_mgr.get_service_info(service_name, target_dir)
    
    print(f"  - Service exists: {info.get('exists')}")
    print(f"  - Is Git repo: {info.get('is_git_repo')}")
    print(f"  - Path: {info.get('path')}")
    if 'branch' in info:
        print(f"  - Branch: {info.get('branch')}")
    if 'commit_hash' in info:
        print(f"  - Commit: {info.get('commit_hash', 'N/A')[:8]}...")
    
    if info.get('exists') and info.get('is_git_repo'):
        print("✓ Service information retrieved successfully")
    else:
        print("✗ Service information incomplete")
        return False
    
    # Test 4: Check launcher integration
    print("\n[TEST 4] Testing launcher service manager integration...")
    try:
        from launcher.manager import ServiceManager
        svc_mgr = ServiceManager(root_dir)
        
        # Check chatterbox service configuration
        chatterbox_config = svc_mgr.services.get("chatterbox")
        if not chatterbox_config:
            print("✗ Chatterbox not found in service manager")
            return False
        
        print(f"  - Service name: {chatterbox_config['name']}")
        print(f"  - Service port: {chatterbox_config['port']}")
        print(f"  - Service dir: {chatterbox_config['dir']}")
        print(f"  - Is external: {chatterbox_config.get('is_external', False)}")
        print(f"  - Repo URL: {chatterbox_config.get('repo_url', 'N/A')}")
        
        # Verify directory matches
        if chatterbox_config['dir'] == target_dir:
            print("✓ Launcher integration successful")
        else:
            print(f"✗ Directory mismatch: expected {target_dir}, got {chatterbox_config['dir']}")
            return False
            
    except Exception as e:
        print(f"✗ Launcher integration failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run the launcher GUI: python launcher/launcher.py")
    print("2. Click 'Install' on Chatterbox service")
    print("3. Click 'Start' to run the service")
    print("4. Test API at http://localhost:4123/health")
    
    return True

if __name__ == "__main__":
    try:
        success = test_external_services()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
