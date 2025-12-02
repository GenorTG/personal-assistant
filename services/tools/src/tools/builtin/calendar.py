"""Calendar and reminder tool."""
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiosqlite
import uuid
from ..base import BaseTool
from ...config.settings import settings


class CalendarTool(BaseTool):
    """Tool for managing calendar events and reminders."""
    
    @property
    def name(self) -> str:
        return "calendar"
    
    @property
    def description(self) -> str:
        return "Create, list, and manage calendar reminders. Useful for scheduling tasks, setting reminders, and tracking events."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["create", "list", "get", "update", "delete", "complete"],
                        "description": "Calendar operation to perform"
                    },
                    "reminder_id": {
                        "type": "string",
                        "description": "Reminder ID (for get, update, delete, complete operations)"
                    },
                    "title": {
                        "type": "string",
                        "description": "Reminder title (for create/update operations)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Reminder description (for create/update operations)"
                    },
                    "due_at": {
                        "type": "string",
                        "description": "Due date/time in ISO format (for create/update operations)"
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "Completion status (for update/complete operations)"
                    }
                },
                "required": ["operation"]
            }
        }
    
    async def _initialize_db(self):
        """Initialize database table for reminders."""
        async with aiosqlite.connect(str(settings.db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    due_at TIMESTAMP,
                    repeat_rule TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    
    async def execute(
        self,
        operation: str,
        reminder_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_at: Optional[str] = None,
        completed: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Execute calendar operation.
        
        Args:
            operation: Operation to perform
            reminder_id: Reminder ID
            title: Reminder title
            description: Reminder description
            due_at: Due date/time
            completed: Completion status
        
        Returns:
            Dictionary with operation result
        """
        await self._initialize_db()
        
        try:
            if operation == "create":
                if not title:
                    return {
                        "error": "'title' is required for create operation"
                    }
                
                reminder_id = str(uuid.uuid4())
                now = datetime.utcnow().isoformat()
                
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    await db.execute("""
                        INSERT INTO reminders (id, title, description, due_at, completed, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (reminder_id, title, description, due_at, False, now))
                    await db.commit()
                
                return {
                    "result": {
                        "id": reminder_id,
                        "title": title,
                        "description": description,
                        "due_at": due_at,
                        "completed": False,
                        "message": "Reminder created successfully"
                    }
                }
            
            elif operation == "list":
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("""
                        SELECT id, title, description, due_at, completed, created_at
                        FROM reminders
                        ORDER BY due_at ASC, created_at DESC
                    """) as cursor:
                        rows = await cursor.fetchall()
                        
                        reminders = [
                            {
                                "id": row["id"],
                                "title": row["title"],
                                "description": row["description"],
                                "due_at": row["due_at"],
                                "completed": bool(row["completed"]),
                                "created_at": row["created_at"]
                            }
                            for row in rows
                        ]
                
                return {
                    "result": {
                        "reminders": reminders,
                        "count": len(reminders)
                    }
                }
            
            elif operation == "get":
                if not reminder_id:
                    return {
                        "error": "'reminder_id' is required for get operation"
                    }
                
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("""
                        SELECT id, title, description, due_at, completed, created_at
                        FROM reminders
                        WHERE id = ?
                    """, (reminder_id,)) as cursor:
                        row = await cursor.fetchone()
                        
                        if row:
                            return {
                                "result": {
                                    "id": row["id"],
                                    "title": row["title"],
                                    "description": row["description"],
                                    "due_at": row["due_at"],
                                    "completed": bool(row["completed"]),
                                    "created_at": row["created_at"]
                                }
                            }
                        else:
                            return {
                                "error": f"Reminder not found: {reminder_id}"
                            }
            
            elif operation == "update":
                if not reminder_id:
                    return {
                        "error": "'reminder_id' is required for update operation"
                    }
                
                # Build update query dynamically
                updates = []
                params = []
                
                if title is not None:
                    updates.append("title = ?")
                    params.append(title)
                if description is not None:
                    updates.append("description = ?")
                    params.append(description)
                if due_at is not None:
                    updates.append("due_at = ?")
                    params.append(due_at)
                if completed is not None:
                    updates.append("completed = ?")
                    params.append(completed)
                
                if not updates:
                    return {
                        "error": "No fields to update"
                    }
                
                params.append(reminder_id)
                
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    await db.execute(f"""
                        UPDATE reminders
                        SET {', '.join(updates)}
                        WHERE id = ?
                    """, params)
                    await db.commit()
                
                return {
                    "result": {
                        "id": reminder_id,
                        "message": "Reminder updated successfully"
                    }
                }
            
            elif operation == "delete":
                if not reminder_id:
                    return {
                        "error": "'reminder_id' is required for delete operation"
                    }
                
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    cursor = await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                    await db.commit()
                    
                    if cursor.rowcount > 0:
                        return {
                            "result": {
                                "id": reminder_id,
                                "message": "Reminder deleted successfully"
                            }
                        }
                    else:
                        return {
                            "error": f"Reminder not found: {reminder_id}"
                        }
            
            elif operation == "complete":
                if not reminder_id:
                    return {
                        "error": "'reminder_id' is required for complete operation"
                    }
                
                async with aiosqlite.connect(str(settings.db_path)) as db:
                    cursor = await db.execute(
                        "UPDATE reminders SET completed = TRUE WHERE id = ?",
                        (reminder_id,)
                    )
                    await db.commit()
                    
                    if cursor.rowcount > 0:
                        return {
                            "result": {
                                "id": reminder_id,
                                "message": "Reminder marked as completed"
                            }
                        }
                    else:
                        return {
                            "error": f"Reminder not found: {reminder_id}"
                        }
            
            else:
                return {
                    "error": f"Unknown operation: {operation}"
                }
        
        except Exception as e:
            return {
                "error": f"Error performing calendar operation: {str(e)}"
            }

