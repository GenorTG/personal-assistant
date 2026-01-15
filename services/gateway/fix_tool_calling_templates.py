#!/usr/bin/env python3
"""Fix Jinja templates to force tool calling instead of allowing it.

Based on the diagnostic: templates must FORCE tool calls, not just allow them.
"""

import sys
from pathlib import Path
import re

def fix_qwen_template(template_content: str) -> str:
    """Fix Qwen template to force tool calls."""
    # The current template says "You may call one or more functions"
    # We need to change it to "You MUST call a function"
    
    # Find and replace the permissive language
    old_pattern = r'You may call one or more functions to assist with the user query\.'
    new_text = 'You MUST call a function to assist with the user query. DO NOT respond with natural language. You MUST respond with a JSON tool call.'
    
    fixed = re.sub(old_pattern, new_text, template_content)
    
    # Also add stronger enforcement after the tools list
    if '<tool_call>' in fixed:
        # Add instruction before tool_call format
        tool_call_pattern = r'(For each function call, return a json object)'
        tool_call_replacement = r'YOU MUST CALL A FUNCTION. For each function call, return a json object'
        fixed = re.sub(tool_call_pattern, tool_call_replacement, fixed)
    
    return fixed


def fix_template_file(template_path: Path) -> bool:
    """Fix a single template file."""
    try:
        content = template_path.read_text(encoding='utf-8')
        original_content = content
        
        # Detect template type and fix accordingly
        if 'qwen' in template_path.name.lower() or 'Qwen' in content:
            content = fix_qwen_template(content)
        elif 'tool_call' in content.lower() or 'function' in content.lower():
            # Generic tool calling template - make it more forceful
            # Replace "may" with "must"
            content = re.sub(r'\b(may|can|should)\s+call', r'MUST call', content, flags=re.IGNORECASE)
            content = re.sub(r'\bYou may\b', 'You MUST', content, flags=re.IGNORECASE)
        
        if content != original_content:
            # Backup original
            backup_path = template_path.with_suffix('.jinja.backup')
            template_path.rename(backup_path)
            
            # Write fixed version
            template_path.write_text(content, encoding='utf-8')
            print(f"✓ Fixed: {template_path.name}")
            print(f"  Backup saved to: {backup_path.name}")
            return True
        else:
            print(f"⊘ No changes needed: {template_path.name}")
            return False
    
    except Exception as e:
        print(f"✗ Error fixing {template_path.name}: {e}")
        return False


def main():
    """Fix all Jinja templates in models directory."""
    models_dir = Path("data/models")
    
    if not models_dir.exists():
        print(f"Error: Models directory not found: {models_dir}")
        return
    
    template_files = list(models_dir.glob("*.jinja"))
    
    if not template_files:
        print("No Jinja template files found.")
        return
    
    print(f"Found {len(template_files)} template file(s) to check...\n")
    
    fixed_count = 0
    for template_file in template_files:
        if fix_template_file(template_file):
            fixed_count += 1
    
    print(f"\n{'='*60}")
    print(f"Fixed {fixed_count} out of {len(template_files)} template(s)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
