"""Test script for system monitoring."""
import asyncio
import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

async def test_monitoring():
    """Test the system monitor."""
    from src.services.system_monitor import system_monitor
    
    print("=" * 60)
    print("SYSTEM MONITORING TEST")
    print("=" * 60)
    
    status = system_monitor.get_status()
    
    print(f"\nSystem Overview:")
    print(f"  Total RAM: {status['system']['total_ram_gb']} GB")
    print(f"  RAM Used: {status['system']['ram_used_gb']} GB")
    print(f"  Total VRAM: {status['system']['total_vram_gb']} GB")
    print(f"  CPU: {status['system']['cpu_percent']}%")
    
    print(f"\nServices ({len(status['services'])} configured):")
    print("=" * 60)
    
    for service in status['services']:
        status_icon = "✓" if service['status'] == 'running' else "✗"
        print(f"\n{status_icon} {service['name']} (Port {service['port']})")
        print(f"  Status: {service['status']}")
        
        if service['status'] == 'running':
            print(f"  PID: {service['pid']}")
            print(f"  RAM: {service['ram_gb']:.2f} GB")
            print(f"  VRAM: {service['vram_gb']:.2f} GB")
            print(f"  CPU: {service['cpu_percent']}%")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_monitoring())
