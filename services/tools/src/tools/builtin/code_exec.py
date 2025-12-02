"""Code execution tool."""
from typing import Dict, Any
from ..base import BaseTool
from ..sandbox import CodeSandbox


class CodeExecutionTool(BaseTool):
    """Tool for executing Python or JavaScript code in a sandbox."""
    
    def __init__(self):
        self.sandbox = CodeSandbox()
    
    @property
    def name(self) -> str:
        return "execute_code"
    
    @property
    def description(self) -> str:
        return "Execute Python or JavaScript code in a sandboxed environment. Useful for calculations, data processing, or running scripts."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code to execute"
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "javascript"],
                        "description": "Programming language (python or javascript)",
                        "default": "python"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (default: 30)",
                        "default": 30
                    }
                },
                "required": ["code"]
            }
        }
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute code in sandbox.
        
        Args:
            code: Code to execute
            language: Programming language
            timeout: Execution timeout
        
        Returns:
            Dictionary with execution result
        """
        if language == "python":
            result = await self.sandbox.execute_python(code, timeout)
        elif language == "javascript":
            result = await self.sandbox.execute_javascript(code, timeout)
        else:
            return {
                "error": f"Unsupported language: {language}. Supported: python, javascript"
            }
        
        if result["success"]:
            return {
                "result": {
                    "output": result["output"],
                    "language": language
                }
            }
        else:
            return {
                "error": result.get("error", "Code execution failed"),
                "result": {
                    "output": result.get("output", ""),
                    "language": language
                }
            }

