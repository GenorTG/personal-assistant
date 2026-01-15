#!/usr/bin/env python3
import sys
import asyncio
import json
from pathlib import Path

gateway_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(gateway_dir / "src"))

from src.services.service_manager import ServiceManager

async def main():
    sm = ServiceManager()
    await sm.initialize()
    tools = await sm.tool_manager.list_tools()
    print(json.dumps(tools[0], indent=2))

if __name__ == '__main__':
    asyncio.run(main())
