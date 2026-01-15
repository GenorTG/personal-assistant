#!/usr/bin/env python3
"""Simple script to view LLM request/response logs in real-time."""
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def format_timestamp(ts: float) -> str:
    """Format timestamp to readable string."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def print_log_entry(log: dict, index: int):
    """Print a single log entry in a readable format."""
    print("\n" + "=" * 80)
    print(f"LOG ENTRY #{index + 1}")
    print("=" * 80)
    print(f"Timestamp: {format_timestamp(log['timestamp'])}")
    if log.get('duration_ms'):
        print(f"Duration: {log['duration_ms']:.2f} ms")
    if log.get('error'):
        print(f"ERROR: {log['error']}")
    
    # Print metadata
    if log.get('metadata'):
        print("\n--- METADATA ---")
        for key, value in log['metadata'].items():
            print(f"  {key}: {value}")
    
    # Print request
    if log.get('request'):
        print("\n--- REQUEST ---")
        request = log['request']
        print(f"Model: {request.get('model', 'N/A')}")
        print(f"Temperature: {request.get('temperature', 'N/A')}")
        print(f"Max Tokens: {request.get('max_tokens', 'N/A')}")
        
        if request.get('tools'):
            print(f"\nTools ({len(request['tools'])}):")
            for i, tool in enumerate(request['tools'], 1):
                func = tool.get('function', {})
                print(f"  {i}. {func.get('name', 'unknown')}")
                print(f"     Description: {func.get('description', 'N/A')[:100]}...")
                params = func.get('parameters', {})
                if 'title' in params:
                    print(f"     ✓ Has title field: {params['title']}")
                else:
                    print(f"     ✗ Missing title field!")
                if 'properties' in params:
                    props = params['properties']
                    print(f"     Properties: {list(props.keys())}")
                    for prop_name, prop_def in list(props.items())[:3]:
                        has_title = isinstance(prop_def, dict) and 'title' in prop_def
                        print(f"       - {prop_name}: {'✓ has title' if has_title else '✗ missing title'}")
        
        if request.get('tool_choice'):
            print(f"\nTool Choice: {json.dumps(request['tool_choice'], indent=2)}")
        
        if request.get('messages'):
            print(f"\nMessages ({len(request['messages'])}):")
            for i, msg in enumerate(request['messages'], 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if len(content) > 200:
                    content = content[:200] + "..."
                print(f"  {i}. [{role}]: {content}")
    
    # Print response
    if log.get('response'):
        print("\n--- RESPONSE ---")
        response = log['response']
        if response.get('choices'):
            choice = response['choices'][0]
            message = choice.get('message', {})
            content = message.get('content', '')
            if content:
                if len(content) > 500:
                    content = content[:500] + "..."
                print(f"Content: {content}")
            
            if message.get('tool_calls'):
                print(f"\nTool Calls ({len(message['tool_calls'])}):")
                for i, tc in enumerate(message['tool_calls'], 1):
                    func = tc.get('function', {})
                    print(f"  {i}. {func.get('name', 'unknown')}")
                    args = func.get('arguments', '{}')
                    try:
                        args_dict = json.loads(args) if isinstance(args, str) else args
                        print(f"     Arguments: {json.dumps(args_dict, indent=6)}")
                    except:
                        print(f"     Arguments: {args[:200]}")
        else:
            print("No choices in response")
    
    # Print tool calls from log
    if log.get('tool_calls'):
        print(f"\n--- EXTRACTED TOOL CALLS ({len(log['tool_calls'])}) ---")
        for i, tc in enumerate(log['tool_calls'], 1):
            func = tc.get('function', {})
            print(f"  {i}. {func.get('name', 'unknown')}")
            args = func.get('arguments', '{}')
            try:
                args_dict = json.loads(args) if isinstance(args, str) else args
                print(f"     Arguments: {json.dumps(args_dict, indent=6)}")
            except:
                print(f"     Arguments: {args[:200]}")

def main():
    """Main function to fetch and display logs."""
    import argparse
    
    parser = argparse.ArgumentParser(description="View LLM request/response logs")
    parser.add_argument("--limit", type=int, default=10, help="Number of logs to fetch (default: 10)")
    parser.add_argument("--watch", action="store_true", help="Watch for new logs (poll every 2 seconds)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--port", type=int, default=8042, help="Gateway port (default: 8042)")
    
    args = parser.parse_args()
    
    url = f"http://localhost:{args.port}/api/debug/llm-logs"
    
    if args.watch:
        print("Watching for new logs (Ctrl+C to stop)...")
        last_count = 0
        try:
            while True:
                try:
                    response = requests.get(url, params={"limit": args.limit}, timeout=5)
                    response.raise_for_status()
                    data = response.json()
                    logs = data.get('logs', [])
                    
                    if len(logs) > last_count:
                        new_logs = logs[:len(logs) - last_count]
                        for log in reversed(new_logs):
                            if args.json:
                                print(json.dumps(log, indent=2))
                            else:
                                print_log_entry(log, len(logs) - logs.index(log) - 1)
                        last_count = len(logs)
                    
                    time.sleep(2)
                except KeyboardInterrupt:
                    print("\nStopped watching.")
                    break
                except Exception as e:
                    print(f"Error: {e}")
                    time.sleep(2)
        except KeyboardInterrupt:
            pass
    else:
        try:
            response = requests.get(url, params={"limit": args.limit}, timeout=5)
            response.raise_for_status()
            data = response.json()
            logs = data.get('logs', [])
            
            if args.json:
                print(json.dumps(logs, indent=2))
            else:
                if not logs:
                    print("No logs available.")
                else:
                    print(f"Found {len(logs)} log entries (most recent first):\n")
                    for i, log in enumerate(logs):
                        print_log_entry(log, i)
        except Exception as e:
            print(f"Error fetching logs: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
