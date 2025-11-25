"""Tool call parser from LLM responses."""
from typing import List, Dict, Any
import json
import re


class ToolCallParser:
    """Parses tool calls from LLM responses."""
    
    def parse(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from LLM response.
        
        Supports multiple formats:
        1. JSON format: {"tool": "name", "arguments": {...}}
        2. Function calling format: <function_calls><invoke name="tool_name"><parameter name="param">value</parameter></invoke></function_calls>
        3. Structured text: Tool: tool_name\nArguments: {...}
        
        Args:
            response: LLM response text
            
        Returns:
            List of tool call dictionaries with 'name' and 'arguments' keys
        """
        tool_calls = []
        
        # Try JSON format: {"tool": "name", "arguments": {...}}
        # Match complete JSON objects
        json_pattern = r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^}]*\})\s*\}'
        json_matches = re.finditer(json_pattern, response)
        for match in json_matches:
            try:
                tool_name = match.group(1)
                arguments_str = match.group(2)
                # Try to parse arguments as JSON
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    # If not valid JSON, try to extract key-value pairs
                    arguments = self._parse_arguments_text(arguments_str)
                tool_calls.append({
                    "name": tool_name,
                    "arguments": arguments
                })
            except (json.JSONDecodeError, IndexError):
                continue
        
        # Try function calling format: <function_calls>...</function_calls>
        if not tool_calls:
            function_pattern = r'<function_calls>.*?</function_calls>'
            function_match = re.search(function_pattern, response, re.DOTALL)
            if function_match:
                function_calls = self._parse_function_calls(function_match.group(0))
                tool_calls.extend(function_calls)
        
        # Try structured text format: Tool: name\nArguments: {...}
        if not tool_calls:
            text_pattern = r'Tool\s*:\s*([^\n]+)\s*\n\s*Arguments\s*:\s*(\{.*?\})'
            text_matches = re.finditer(text_pattern, response, re.DOTALL)
            for match in text_matches:
                try:
                    tool_name = match.group(1).strip()
                    arguments_str = match.group(2).strip()
                    try:
                        arguments = json.loads(arguments_str)
                    except json.JSONDecodeError:
                        arguments = self._parse_arguments_text(arguments_str)
                    tool_calls.append({
                        "name": tool_name,
                        "arguments": arguments
                    })
                except (json.JSONDecodeError, IndexError):
                    continue
        
        return tool_calls
    
    def _parse_function_calls(self, xml_content: str) -> List[Dict[str, Any]]:
        """Parse function calls from XML-like format.
        
        Args:
            xml_content: XML content with function calls
            
        Returns:
            List of tool call dictionaries
        """
        tool_calls = []
        
        # Pattern: <invoke name="tool_name">...</invoke>
        invoke_pattern = r'<invoke\s+name="([^"]+)"[^>]*>(.*?)</invoke>'
        invoke_matches = re.finditer(invoke_pattern, xml_content, re.DOTALL)
        
        for match in invoke_matches:
            tool_name = match.group(1)
            params_content = match.group(2)
            
            # Parse parameters: <parameter name="param">value</parameter>
            arguments = {}
            param_pattern = r'<parameter\s+name="([^"]+)"[^>]*>(.*?)</parameter>'
            param_matches = re.finditer(param_pattern, params_content, re.DOTALL)
            
            for param_match in param_matches:
                param_name = param_match.group(1)
                param_value = param_match.group(2).strip()
                # Try to parse as JSON, otherwise use as string
                try:
                    arguments[param_name] = json.loads(param_value)
                except json.JSONDecodeError:
                    arguments[param_name] = param_value
            
            tool_calls.append({
                "name": tool_name,
                "arguments": arguments
            })
        
        return tool_calls
    
    def _parse_arguments_text(self, text: str) -> Dict[str, Any]:
        """Parse arguments from text format.
        
        Args:
            text: Arguments text (may be JSON-like or key=value format)
            
        Returns:
            Dictionary of arguments
        """
        arguments = {}
        
        # Try to extract key-value pairs from text like: key: value, key2: value2
        kv_pattern = r'"([^"]+)"\s*:\s*"([^"]+)"'
        kv_matches = re.finditer(kv_pattern, text)
        for match in kv_matches:
            key = match.group(1)
            value = match.group(2)
            arguments[key] = value
        
        # If no matches, try simple key=value format
        if not arguments:
            simple_pattern = r'(\w+)\s*=\s*([^\s,}]+)'
            simple_matches = re.finditer(simple_pattern, text)
            for match in simple_matches:
                key = match.group(1)
                value = match.group(2).strip('"\'')
                arguments[key] = value
        
        return arguments
