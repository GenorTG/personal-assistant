"""Sandboxed code execution."""
import subprocess
import asyncio
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from ..config.settings import settings

logger = logging.getLogger(__name__)


class CodeSandbox:
    """Sandboxed code execution environment."""
    
    def __init__(self):
        self.max_execution_time = settings.max_code_execution_time
        self.temp_dir = Path(tempfile.gettempdir()) / "code_sandbox"
        self.temp_dir.mkdir(exist_ok=True)
    
    async def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute Python code in a sandbox.
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds (default from settings)
        
        Returns:
            Dictionary with 'output', 'error', and 'success' fields
        """
        timeout = timeout or self.max_execution_time
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False,
            dir=str(self.temp_dir)
        ) as f:
            f.write(code)
            script_path = f.name
        
        try:
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                'python',
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.temp_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                output = stdout.decode('utf-8', errors='replace')
                error = stderr.decode('utf-8', errors='replace')
                
                return {
                    "output": output,
                    "error": error if error else None,
                    "success": process.returncode == 0
                }
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "output": "",
                    "error": f"Execution timeout after {timeout} seconds",
                    "success": False
                }
        except Exception as e:
            logger.error(f"Error executing Python code: {e}", exc_info=True)
            return {
                "output": "",
                "error": str(e),
                "success": False
            }
        finally:
            # Clean up
            try:
                os.unlink(script_path)
            except Exception:
                pass
    
    async def execute_javascript(
        self,
        code: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute JavaScript code in a sandbox.
        
        Args:
            code: JavaScript code to execute
            timeout: Execution timeout in seconds (default from settings)
        
        Returns:
            Dictionary with 'output', 'error', and 'success' fields
        """
        timeout = timeout or self.max_execution_time
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False,
            dir=str(self.temp_dir)
        ) as f:
            f.write(code)
            script_path = f.name
        
        try:
            # Execute with timeout (requires Node.js)
            process = await asyncio.create_subprocess_exec(
                'node',
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.temp_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                output = stdout.decode('utf-8', errors='replace')
                error = stderr.decode('utf-8', errors='replace')
                
                return {
                    "output": output,
                    "error": error if error else None,
                    "success": process.returncode == 0
                }
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "output": "",
                    "error": f"Execution timeout after {timeout} seconds",
                    "success": False
                }
        except FileNotFoundError:
            return {
                "output": "",
                "error": "Node.js not found. Please install Node.js to run JavaScript code.",
                "success": False
            }
        except Exception as e:
            logger.error(f"Error executing JavaScript code: {e}", exc_info=True)
            return {
                "output": "",
                "error": str(e),
                "success": False
            }
        finally:
            # Clean up
            try:
                os.unlink(script_path)
            except Exception:
                pass

