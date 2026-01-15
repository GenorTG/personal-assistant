"""Simple benchmark tool for testing function calling."""
from typing import Dict, Any
from ..base_tool import BaseTool


class BenchmarkTool(BaseTool):
    """Simple benchmark tool for testing function calling.
    
    This tool performs basic arithmetic operations to verify that
    function calling is working correctly with the model.
    """
    
    @property
    def name(self) -> str:
        return "add_numbers"
    
    @property
    def description(self) -> str:
        return "Add two numbers together. Returns the sum of the two numbers. Use this tool when asked to calculate the sum of two numbers or perform addition."
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "a": {
                    "type": "integer",
                    "description": "The first number to add"
                },
                "b": {
                    "type": "integer",
                    "description": "The second number to add"
                }
            },
            "required": ["a", "b"]
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the addition operation.
        
        Args:
            arguments: Dictionary with 'a' and 'b' keys containing integers
            
        Returns:
            Dictionary with 'result' containing the sum and 'error' (None if successful)
        """
        try:
            a = arguments.get("a")
            b = arguments.get("b")
            
            if a is None or b is None:
                return {
                    "result": None,
                    "error": "Both 'a' and 'b' parameters are required"
                }
            
            # Ensure they are integers
            a = int(a)
            b = int(b)
            
            result = a + b
            
            return {
                "result": result,
                "error": None
            }
        except (ValueError, TypeError) as e:
            return {
                "result": None,
                "error": f"Invalid arguments: {str(e)}. Expected integers for 'a' and 'b'."
            }
        except Exception as e:
            return {
                "result": None,
                "error": f"Unexpected error: {str(e)}"
            }
