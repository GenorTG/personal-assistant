"""File access tool (sandboxed to data/files/)."""
from typing import Dict, Any, Optional, List
from pathlib import Path
import shutil
from ..base import BaseTool
from ...config.settings import settings


class FileAccessTool(BaseTool):
    """Tool for reading, writing, and managing files in data/files/ directory."""
    
    @property
    def name(self) -> str:
        return "file_access"
    
    @property
    def description(self) -> str:
        return "Read, write, list, and delete files in the data/files/ directory. All file operations are sandboxed to this directory for security."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read", "write", "list", "delete", "exists"],
                        "description": "File operation to perform"
                    },
                    "path": {
                        "type": "string",
                        "description": "File path relative to data/files/ directory"
                    },
                    "content": {
                        "type": "string",
                        "description": "File content (for write operation)"
                    }
                },
                "required": ["operation", "path"]
            }
        }
    
    def _validate_path(self, path: str) -> Optional[Path]:
        """Validate and resolve file path within sandbox.
        
        Args:
            path: File path
        
        Returns:
            Resolved Path object or None if invalid
        """
        # Resolve to absolute path
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = settings.files_dir / file_path
        
        # Resolve to prevent path traversal
        try:
            file_path = file_path.resolve()
        except Exception:
            return None
        
        # Ensure path is within files_dir
        try:
            file_path.relative_to(settings.files_dir.resolve())
        except ValueError:
            return None  # Path outside sandbox
        
        return file_path
    
    async def execute(
        self,
        operation: str,
        path: str,
        content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute file operation.
        
        Args:
            operation: Operation to perform
            path: File path
            content: File content (for write)
        
        Returns:
            Dictionary with operation result
        """
        file_path = self._validate_path(path)
        
        if not file_path:
            return {
                "error": f"Invalid path: {path}. Path must be within data/files/ directory."
            }
        
        try:
            if operation == "read":
                if not file_path.exists():
                    return {"error": f"File not found: {path}"}
                
                if not file_path.is_file():
                    return {"error": f"Path is not a file: {path}"}
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                
                return {
                    "result": {
                        "content": file_content,
                        "path": path,
                        "size": len(file_content)
                    }
                }
            
            elif operation == "write":
                # Ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                if content is None:
                    return {"error": "Content is required for write operation"}
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return {
                    "result": {
                        "message": f"File written successfully: {path}",
                        "path": path,
                        "size": len(content)
                    }
                }
            
            elif operation == "list":
                if not file_path.exists():
                    return {"error": f"Path not found: {path}"}
                
                if file_path.is_file():
                    return {
                        "result": {
                            "type": "file",
                            "path": path,
                            "size": file_path.stat().st_size
                        }
                    }
                
                # List directory contents
                items = []
                for item in file_path.iterdir():
                    items.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None
                    })
                
                return {
                    "result": {
                        "type": "directory",
                        "path": path,
                        "items": items
                    }
                }
            
            elif operation == "delete":
                if not file_path.exists():
                    return {"error": f"File not found: {path}"}
                
                if file_path.is_dir():
                    shutil.rmtree(file_path)
                else:
                    file_path.unlink()
                
                return {
                    "result": {
                        "message": f"Deleted: {path}"
                    }
                }
            
            elif operation == "exists":
                return {
                    "result": {
                        "exists": file_path.exists(),
                        "path": path
                    }
                }
            
            else:
                return {
                    "error": f"Unknown operation: {operation}"
                }
        
        except Exception as e:
            return {
                "error": f"Error performing {operation} operation: {str(e)}"
            }

