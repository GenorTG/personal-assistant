#!/usr/bin/env python3
"""Debug script to check function calling setup."""
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def main():
    from services.service_manager import service_manager
    from services.llm.manager import LLMManager
    from services.tools.manager import ToolManager
    from services.memory.store import MemoryStore
    
    print("=" * 80)
    print("Function Calling Debug")
    print("=" * 80)
    
    # Initialize services
    print("\n1. Initializing services...")
    memory_store = MemoryStore()
    await memory_store.initialize()
    
    tool_manager = ToolManager(memory_store=memory_store)
    await tool_manager.initialize()
    
    # Check if LLM manager has tool_manager
    if hasattr(service_manager, 'llm_manager') and service_manager.llm_manager:
        llm_manager = service_manager.llm_manager
        print(f"\n2. LLM Manager found: {type(llm_manager).__name__}")
        print(f"   - Model loaded: {llm_manager.is_model_loaded()}")
        print(f"   - Supports tool calling: {llm_manager.supports_tool_calling}")
        print(f"   - Current chat format: {getattr(llm_manager, 'current_chat_format', 'None')}")
        print(f"   - Current model name: {llm_manager.current_model_name}")
        
        # Check tool_manager
        tool_source = getattr(llm_manager, 'tool_manager', None) or getattr(llm_manager, 'tool_registry', None)
        print(f"   - Tool source available: {tool_source is not None}")
        if tool_source:
            print(f"   - Tool source type: {type(tool_source).__name__}")
            try:
                tools = await tool_source.list_tools()
                print(f"   - Tools retrieved: {len(tools)}")
                for i, tool in enumerate(tools[:5], 1):
                    name = tool.get('function', {}).get('name', 'unknown')
                    params = tool.get('function', {}).get('parameters', {})
                    has_title = 'title' in params
                    print(f"     {i}. {name} - has title: {has_title}")
                    if params.get('properties'):
                        for prop_name, prop_def in list(params.get('properties', {}).items())[:2]:
                            prop_has_title = isinstance(prop_def, dict) and 'title' in prop_def
                            print(f"        - {prop_name}: has title: {prop_has_title}")
            except Exception as e:
                print(f"   - Error listing tools: {e}")
        else:
            print("   - ⚠️  NO TOOL SOURCE - tools won't be sent!")
        
        # Check system prompt
        system_prompt = llm_manager._build_system_prompt()
        print(f"\n3. System prompt:")
        print(f"   - Length: {len(system_prompt)}")
        print(f"   - Preview: {system_prompt[:100]}...")
        if "chatml-function-calling" in str(getattr(llm_manager, 'current_chat_format', '')):
            expected = "A chat between a curious user and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the user's questions. The assistant calls functions with appropriate input when necessary"
            if system_prompt == expected:
                print("   - ✅ System prompt matches expected for chatml-function-calling")
            else:
                print("   - ❌ System prompt does NOT match expected!")
                print(f"   - Expected: {expected[:80]}...")
    else:
        print("\n2. ⚠️  LLM Manager not initialized!")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
