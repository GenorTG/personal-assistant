"""Todo tool for managing tasks and todo items."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
import uuid
from ..base_tool import BaseTool

logger = logging.getLogger(__name__)


class TodoTool(BaseTool):
    """Tool for managing todo items and tasks."""
    
    def __init__(self, todos_dir: Optional[Path] = None):
        """Initialize todo tool.
        
        Args:
            todos_dir: Directory to store todo files (defaults to data/todos)
        """
        from ....config.settings import settings
        
        if todos_dir is None:
            todos_dir = Path(settings.data_dir) / "todos"
        self.todos_dir = Path(todos_dir)
        self.todos_dir.mkdir(parents=True, exist_ok=True)
        self.todos_file = self.todos_dir / "todos.json"
    
    @property
    def name(self) -> str:
        return "todo"
    
    @property
    def description(self) -> str:
        return """Manage todo items and tasks. Use this tool when the user asks to:
- Create, add, or make a new todo/task/item
- List or show todos (can filter by status, priority, due date, or category)
- Get/read a specific todo by ID to see its details
- Update or modify an existing todo (change title, description, status, priority, due date, category, etc.)
- Delete a specific todo
- Mark a todo as complete/done
- Mark a todo as incomplete/pending
- Clear all completed todos
- Get todos by category or project

**CRITICAL FOR CREATE ACTIONS**: When action="create", you MUST extract and include the title parameter:
1. **title** (MANDATORY): The task/todo title - extract from the user's message
   - "add 'buy milk' to my todo list" → title="buy milk"
   - "create a todo to fix the bug" → title="fix the bug"
   - "remind me to call John" → title="call John"
   - If no explicit title is given, try to infer from context or ask for clarification

**Optional parameters for create/update**:
- **description**: Additional details about the todo
- **priority**: "low", "medium", "high", or "urgent" (default: "medium")
- **due_date**: When the todo should be completed (natural language like "tomorrow", "next friday", or ISO format)
- **category**: Organize todos by category/project (e.g., "work", "personal", "shopping")
- **status**: "pending" (default) or "completed"

EXAMPLE: User says "add 'buy groceries' to my todo list with high priority"
Extract:
- action: "create"
- title: "buy groceries"
- priority: "high"
- status: "pending" (default)

NEVER call this tool with action="create" without including the title parameter!
"""
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "get", "update", "delete", "complete", "uncomplete", "clear_completed"],
                    "description": "Action to perform. Use 'create' when user asks to add/create a new todo. Use 'list' to show todos (can filter by status, priority, category, or due_date). Use 'get' to retrieve a specific todo by ID. Use 'update' to modify a todo. Use 'delete' to remove a todo. Use 'complete' to mark a todo as done. Use 'uncomplete' to mark a todo as pending. Use 'clear_completed' to delete all completed todos."
                },
                "todo_id": {
                    "type": "string",
                    "description": "Todo ID (required ONLY for get, update, delete, complete, uncomplete actions). Not needed for create or list."
                },
                "title": {
                    "type": "string",
                    "description": "Todo title/task name. **MANDATORY FOR CREATE ACTIONS** - You MUST ALWAYS include this parameter when action='create'. Extract the task from the user's message. Examples: 'buy milk' → title='buy milk', 'fix bug' → title='fix bug'. NEVER omit this parameter for create actions!"
                },
                "description": {
                    "type": "string",
                    "description": "Optional todo description or additional notes. Only include if user provides it."
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Todo priority level. Default is 'medium' if not specified."
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "completed"],
                    "description": "Todo status. Default is 'pending' for new todos. Use 'completed' when marking as done."
                },
                "due_date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Due date for the todo. Can be natural language (e.g., 'tomorrow', 'next friday', 'in 3 days') or ISO format. The tool will parse natural language dates relative to current date/time."
                },
                "category": {
                    "type": "string",
                    "description": "Category or project name to organize todos (e.g., 'work', 'personal', 'shopping', 'project-name'). Only include if user provides it."
                },
                "filter_status": {
                    "type": "string",
                    "enum": ["all", "pending", "completed"],
                    "description": "Filter todos by status when action='list'. Default is 'all'."
                },
                "filter_priority": {
                    "type": "string",
                    "enum": ["all", "low", "medium", "high", "urgent"],
                    "description": "Filter todos by priority when action='list'. Default is 'all'."
                },
                "filter_category": {
                    "type": "string",
                    "description": "Filter todos by category when action='list'. Only include if user wants to filter by category."
                }
            },
            "required": ["action"],
            "if": {
                "properties": {
                    "action": {
                        "const": "create"
                    }
                }
            },
            "then": {
                "required": ["title"]
            }
        }
    
    def _load_todos(self) -> List[Dict[str, Any]]:
        """Load todos from JSON storage."""
        if not self.todos_file.exists():
            return []
        
        try:
            with open(self.todos_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading todos: {e}")
            return []
    
    def _save_todos(self, todos: List[Dict[str, Any]]) -> bool:
        """Save todos to JSON storage."""
        try:
            with open(self.todos_file, 'w', encoding='utf-8') as f:
                json.dump(todos, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Error saving todos: {e}")
            return False
    
    def _parse_natural_language_date(self, date_str: str) -> Optional[str]:
        """Parse natural language date strings to ISO format.
        
        Supports patterns like:
        - "tomorrow"
        - "next friday"
        - "in 3 days"
        - "2026-01-15"
        """
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        now = datetime.now()
        
        # Try ISO format first
        try:
            # If it's already ISO format, return as-is
            datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return date_str
        except (ValueError, AttributeError):
            pass
        
        # Parse natural language
        if date_str == "today":
            result_date = now
        elif date_str == "tomorrow":
            result_date = now + timedelta(days=1)
        elif date_str.startswith("in "):
            # "in 3 days", "in 1 week"
            parts = date_str.split()
            if len(parts) >= 3 and parts[1].isdigit():
                days = int(parts[1])
                if "day" in parts[2]:
                    result_date = now + timedelta(days=days)
                elif "week" in parts[2]:
                    result_date = now + timedelta(weeks=days)
                else:
                    result_date = now + timedelta(days=days)
            else:
                return None
        elif date_str.startswith("next "):
            # "next friday", "next monday"
            day_name = date_str.split()[1]
            days_ahead = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6
            }.get(day_name.lower(), None)
            if days_ahead is not None:
                days_until = (days_ahead - now.weekday()) % 7
                if days_until == 0:
                    days_until = 7  # Next week
                result_date = now + timedelta(days=days_until)
            else:
                return None
        else:
            return None
        
        # Return ISO format string
        return result_date.isoformat()
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute todo tool."""
        action = arguments.get("action")
        
        if action == "create":
            return await self._create_todo(arguments)
        elif action == "list":
            return await self._list_todos(arguments)
        elif action == "get":
            return await self._get_todo(arguments)
        elif action == "update":
            return await self._update_todo(arguments)
        elif action == "delete":
            return await self._delete_todo(arguments)
        elif action == "complete":
            return await self._complete_todo(arguments)
        elif action == "uncomplete":
            return await self._uncomplete_todo(arguments)
        elif action == "clear_completed":
            return await self._clear_completed_todos()
        else:
            return {
                "error": f"Unknown action: {action}",
                "result": None
            }
    
    async def _create_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new todo item."""
        title = arguments.get("title")
        if not title:
            return {
                "error": "Title is required for 'create' action",
                "result": None
            }
        
        todos = self._load_todos()
        
        # Create new todo
        todo_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        due_date = arguments.get("due_date")
        if due_date and not due_date.startswith("202"):  # Not ISO format
            due_date = self._parse_natural_language_date(due_date)
        
        new_todo = {
            "id": todo_id,
            "title": title,
            "description": arguments.get("description", ""),
            "priority": arguments.get("priority", "medium"),
            "status": arguments.get("status", "pending"),
            "due_date": due_date,
            "category": arguments.get("category", ""),
            "created_at": now,
            "updated_at": now,
            "completed_at": None
        }
        
        todos.append(new_todo)
        
        if self._save_todos(todos):
            logger.info(f"[TODO TOOL] Created todo: {title} (ID: {todo_id})")
            
            # Broadcast WebSocket event
            try:
                from ...websocket_manager import get_websocket_manager
                ws_manager = get_websocket_manager()
                await ws_manager.broadcast_todo_created(new_todo)
                await ws_manager.broadcast_todos_changed()
            except Exception as e:
                logger.debug(f"Failed to broadcast todo created: {e}")
            
            return {
                "result": {
                    "todo": new_todo,
                    "message": f"Todo '{title}' created successfully"
                },
                "error": None
            }
        else:
            return {
                "error": "Failed to save todo",
                "result": None
            }
    
    async def _list_todos(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List todos with optional filtering."""
        todos = self._load_todos()
        
        # Apply filters
        filter_status = arguments.get("filter_status", "all")
        filter_priority = arguments.get("filter_priority", "all")
        filter_category = arguments.get("filter_category")
        
        filtered_todos = todos
        
        if filter_status != "all":
            filtered_todos = [t for t in filtered_todos if t.get("status") == filter_status]
        
        if filter_priority != "all":
            filtered_todos = [t for t in filtered_todos if t.get("priority") == filter_priority]
        
        if filter_category:
            filtered_todos = [t for t in filtered_todos if t.get("category", "").lower() == filter_category.lower()]
        
        # Sort by: priority (urgent > high > medium > low), then by created_at
        priority_order = {"urgent": 4, "high": 3, "medium": 2, "low": 1}
        filtered_todos.sort(
            key=lambda t: (
                -priority_order.get(t.get("priority", "medium"), 2),
                t.get("created_at", "")
            ),
            reverse=False
        )
        
        return {
            "result": {
                "todos": filtered_todos,
                "count": len(filtered_todos),
                "total": len(todos)
            },
            "error": None
        }
    
    async def _get_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a specific todo by ID."""
        todo_id = arguments.get("todo_id")
        if not todo_id:
            return {
                "error": "todo_id is required for 'get' action",
                "result": None
            }
        
        todos = self._load_todos()
        todo = next((t for t in todos if t.get("id") == todo_id), None)
        
        if not todo:
            return {
                "error": f"Todo with ID '{todo_id}' not found",
                "result": None
            }
        
        return {
            "result": {
                "todo": todo
            },
            "error": None
        }
    
    async def _update_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing todo."""
        todo_id = arguments.get("todo_id")
        if not todo_id:
            return {
                "error": "todo_id is required for 'update' action",
                "result": None
            }
        
        todos = self._load_todos()
        todo_index = next((i for i, t in enumerate(todos) if t.get("id") == todo_id), None)
        
        if todo_index is None:
            return {
                "error": f"Todo with ID '{todo_id}' not found",
                "result": None
            }
        
        todo = todos[todo_index]
        
        # Update fields
        if "title" in arguments:
            todo["title"] = arguments["title"]
        if "description" in arguments:
            todo["description"] = arguments["description"]
        if "priority" in arguments:
            todo["priority"] = arguments["priority"]
        if "status" in arguments:
            todo["status"] = arguments["status"]
            if arguments["status"] == "completed" and not todo.get("completed_at"):
                todo["completed_at"] = datetime.now().isoformat()
            elif arguments["status"] == "pending":
                todo["completed_at"] = None
        if "due_date" in arguments:
            due_date = arguments["due_date"]
            if due_date and not due_date.startswith("202"):  # Not ISO format
                due_date = self._parse_natural_language_date(due_date)
            todo["due_date"] = due_date
        if "category" in arguments:
            todo["category"] = arguments["category"]
        
        todo["updated_at"] = datetime.now().isoformat()
        
        if self._save_todos(todos):
            logger.info(f"[TODO TOOL] Updated todo: {todo.get('title')} (ID: {todo_id})")
            return {
                "result": {
                    "todo": todo,
                    "message": f"Todo '{todo.get('title')}' updated successfully"
                },
                "error": None
            }
        else:
            return {
                "error": "Failed to save updated todo",
                "result": None
            }
    
    async def _delete_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a todo."""
        todo_id = arguments.get("todo_id")
        if not todo_id:
            return {
                "error": "todo_id is required for 'delete' action",
                "result": None
            }
        
        todos = self._load_todos()
        todo = next((t for t in todos if t.get("id") == todo_id), None)
        
        if not todo:
            return {
                "error": f"Todo with ID '{todo_id}' not found",
                "result": None
            }
        
        todos = [t for t in todos if t.get("id") != todo_id]
        
        if self._save_todos(todos):
            logger.info(f"[TODO TOOL] Deleted todo: {todo.get('title')} (ID: {todo_id})")
            
            # Broadcast WebSocket event
            try:
                from ...websocket_manager import get_websocket_manager
                ws_manager = get_websocket_manager()
                await ws_manager.broadcast_todo_deleted(todo_id)
                await ws_manager.broadcast_todos_changed()
            except Exception as e:
                logger.debug(f"Failed to broadcast todo deleted: {e}")
            
            return {
                "result": {
                    "message": f"Todo '{todo.get('title')}' deleted successfully"
                },
                "error": None
            }
        else:
            return {
                "error": "Failed to delete todo",
                "result": None
            }
    
    async def _complete_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a todo as completed."""
        todo_id = arguments.get("todo_id")
        if not todo_id:
            return {
                "error": "todo_id is required for 'complete' action",
                "result": None
            }
        
        return await self._update_todo({
            "todo_id": todo_id,
            "status": "completed"
        })
    
    async def _uncomplete_todo(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a todo as pending (uncomplete)."""
        todo_id = arguments.get("todo_id")
        if not todo_id:
            return {
                "error": "todo_id is required for 'uncomplete' action",
                "result": None
            }
        
        return await self._update_todo({
            "todo_id": todo_id,
            "status": "pending"
        })
    
    async def _clear_completed_todos(self) -> Dict[str, Any]:
        """Delete all completed todos."""
        todos = self._load_todos()
        completed_count = len([t for t in todos if t.get("status") == "completed"])
        
        todos = [t for t in todos if t.get("status") != "completed"]
        
        if self._save_todos(todos):
            logger.info(f"[TODO TOOL] Cleared {completed_count} completed todos")
            return {
                "result": {
                    "message": f"Cleared {completed_count} completed todos",
                    "deleted_count": completed_count
                },
                "error": None
            }
        else:
            return {
                "error": "Failed to clear completed todos",
                "result": None
            }
