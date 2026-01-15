"""Calendar tool for managing events in iCal format."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging
from ..base_tool import BaseTool

logger = logging.getLogger(__name__)


class CalendarTool(BaseTool):
    """Tool for managing calendar events with iCal file storage."""
    
    def __init__(self, calendar_dir: Optional[Path] = None):
        """Initialize calendar tool.
        
        Args:
            calendar_dir: Directory to store calendar files (defaults to data/calendars)
        """
        from ....config.settings import settings
        
        if calendar_dir is None:
            calendar_dir = Path(settings.data_dir) / "calendars"
        self.calendar_dir = Path(calendar_dir)
        self.calendar_dir.mkdir(parents=True, exist_ok=True)
        self.calendar_file = self.calendar_dir / "calendar.ics"
    
    @property
    def name(self) -> str:
        return "calendar"
    
    @property
    def description(self) -> str:
        return """Manage calendar events with comprehensive features. Use this tool when the user asks to:
- Create, add, or schedule a meeting/event/appointment (automatically checks for conflicts)
- List or show calendar events (can filter by date, today, or date range)
- Get/read a specific event by ID to see its details
- Update or modify an existing event (change title, times, location, description, etc.)
- Delete a specific event
- Delete all events on a specific date
- Create all-day events (set all_day=true)
- Check if a date/time is available (check_conflicts action)
- Export the calendar

**CRITICAL FOR CREATE ACTIONS**: When action="create", you MUST extract and include ALL THREE mandatory parameters:
1. **title** (MANDATORY): Extract from phrases like "called 'X'", "called X", "named X", "titled X", or the event name itself
   - "meeting called 'Important Meeting'" → title="Important Meeting" (include the quotes content)
   - "add a meeting called Team Standup" → title="Team Standup" 
   - "schedule Doctor Appointment" → title="Doctor Appointment"
   - If user says "called 'LLM Test Meeting'", extract title="LLM Test Meeting" (the text after 'called', including quotes content)
   - If no explicit title found, use default "Meeting" but ALWAYS include this field

2. **start_time** (MANDATORY): Extract from phrases like "at 2pm", "from 2pm", "starts at 2pm", "tomorrow at 2pm"
   - Can be natural language (e.g., "tomorrow at 2pm", "friday at 13:00") or ISO format
   - For all-day events, set all_day=true and start_time can be just the date
   
3. **end_time** (MANDATORY): Extract from phrases like "to 3pm", "until 3pm", "ends at 3pm", "from 2pm to 3pm"
   - Can be natural language (e.g., "tomorrow at 3pm", "friday at 14:00") or ISO format
   - If only duration given (e.g., "1 hour meeting"), calculate end_time from start_time
   - For all-day events, end_time can be the same date or next day

IMPORTANT: The tool automatically checks for overlapping events when creating. If conflicts are found, they will be reported in the result.

EXAMPLE: User says "Please add a meeting tomorrow at 2pm to 3pm called 'LLM Test Meeting'"
Extract:
- action: "create"
- title: "LLM Test Meeting" (extract text after "called", including quotes content)
- start_time: "tomorrow at 2pm" or "2026-01-15T14:00:00"
- end_time: "tomorrow at 3pm" or "2026-01-15T15:00:00"

**NEVER call this tool with action="create" without including title, start_time, and end_time parameters!**
"""
    
    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "get", "update", "delete", "delete_day", "export", "clear", "check_conflicts"],
                    "description": "Action to perform. Use 'create' when user asks to add/schedule/create a meeting or event (automatically checks for conflicts). Use 'list' to show events (can filter by date). Use 'get' to retrieve a specific event by ID to read its details. Use 'update' to modify an event (change title, times, location, description, etc.). Use 'delete' to remove a specific event. Use 'delete_day' to delete all events on a specific date. Use 'export' to export the calendar. Use 'clear' to delete ALL events from the calendar. Use 'check_conflicts' to check if a time slot is available."
                },
                "event_id": {
                    "type": "string",
                    "description": "Event ID (required ONLY for get, update, delete actions). Not needed for create or list."
                },
                "title": {
                    "type": "string",
                    "description": "Event title/name. **MANDATORY FOR CREATE ACTIONS** - You MUST ALWAYS include this parameter when action='create'. CRITICAL EXTRACTION RULES: 1) Look for the word 'called' followed by text in quotes or after it (e.g., 'called \"Meeting Title\"' or 'called Meeting Title' → extract 'Meeting Title'). 2) Look for 'named' or 'titled' similarly. 3) If the user says 'add a Team Meeting', extract 'Team Meeting' as the title. 4) If no explicit title is found, use a descriptive default like 'Meeting' or 'Event', but ALWAYS include this field. NEVER omit this parameter for create actions - the tool will fail without it!"
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description or notes. Only include if user provides it."
                },
                "start_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Event start time. REQUIRED for 'create' action. Can be natural language (e.g., 'tomorrow at 2pm', 'friday at 13:00', 'next week monday at 9am') or ISO format. Extract from user message - look for phrases like 'at 2pm', 'from 2pm', 'starts at 2pm', 'tomorrow at 2pm'. The tool will parse natural language dates relative to current date/time."
                },
                "end_time": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Event end time. REQUIRED for 'create' action. Can be natural language (e.g., 'tomorrow at 3pm', 'friday at 14:00', 'next week monday at 10am') or ISO format. Extract from user message - look for phrases like 'to 3pm', 'until 3pm', 'ends at 3pm', 'from 2pm to 3pm'. If user only provides duration (e.g., '1 hour meeting'), calculate end_time from start_time. The tool will parse natural language dates relative to current date/time. For all-day events, can be same date or next day."
                },
                "location": {
                    "type": "string",
                    "description": "Optional event location. Only include if user provides it."
                },
                "all_day": {
                    "type": "boolean",
                    "description": "Whether this is an all-day event. Set to true for whole day events (e.g., 'all day meeting', 'whole day event'). Default is false."
                },
                "date": {
                    "type": "string",
                    "format": "date",
                    "description": "Date for filtering or deleting. Used with 'list' (filter_date), 'delete_day', or 'check_conflicts'. Can be natural language like 'today', 'tomorrow', 'friday', or ISO format like '2026-01-15'."
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
                "required": ["title", "start_time", "end_time"]
            }
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute calendar tool."""
        action = arguments.get("action")
        
        if action == "create":
            return await self._create_event(arguments)
        elif action == "list":
            return await self._list_events(arguments)
        elif action == "get":
            return await self._get_event(arguments)
        elif action == "update":
            return await self._update_event(arguments)
        elif action == "delete":
            return await self._delete_event(arguments)
        elif action == "export":
            return await self._export_calendar()
        elif action == "clear":
            return await self._clear_all_events()
        elif action == "delete_day":
            return await self._delete_day_events(arguments)
        elif action == "check_conflicts":
            return await self._check_conflicts(arguments)
        else:
            return {
                "error": f"Unknown action: {action}",
                "result": None
            }
    
    def _load_events(self) -> List[Dict[str, Any]]:
        """Load events from JSON storage (simpler than parsing iCal)."""
        events_file = self.calendar_dir / "events.json"
        if not events_file.exists():
            return []
        
        try:
            with open(events_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading events: {e}")
            return []
    
    def _save_events(self, events: List[Dict[str, Any]]) -> bool:
        """Save events to JSON storage."""
        events_file = self.calendar_dir / "events.json"
        try:
            with open(events_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, indent=2, default=str)
            
            # Also update iCal file
            self._update_ical_file(events)
            return True
        except Exception as e:
            logger.error(f"Error saving events: {e}")
            return False
    
    def _update_ical_file(self, events: List[Dict[str, Any]]):
        """Update iCal file from events."""
        try:
            ical_lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Personal Assistant//Calendar//EN",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH"
            ]
            
            for event in events:
                ical_lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{event.get('id', '')}",
                    f"DTSTART:{self._format_ical_datetime(event.get('start_time'))}",
                    f"DTEND:{self._format_ical_datetime(event.get('end_time'))}",
                    f"SUMMARY:{event.get('title', '')}",
                    f"DESCRIPTION:{event.get('description', '')}",
                    f"LOCATION:{event.get('location', '')}",
                    f"DTSTAMP:{self._format_ical_datetime(datetime.utcnow())}",
                    "END:VEVENT"
                ])
            
            ical_lines.append("END:VCALENDAR")
            
            with open(self.calendar_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(ical_lines))
        except Exception as e:
            logger.error(f"Error updating iCal file: {e}")
    
    def _parse_natural_language_date(self, date_str: str) -> Optional[datetime]:
        """Parse natural language date strings to datetime.
        
        Supports patterns like:
        - "friday in two days"
        - "tomorrow at 1pm"
        - "friday at 13:00"
        - "in 2 days at 1pm"
        - "next friday at 1pm"
        """
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        now = datetime.now()
        
        # Try ISO format first
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
        
        # Parse natural language
        result_date = now.replace(hour=12, minute=0, second=0, microsecond=0)  # Default to noon
        
        # Extract time (e.g., "1pm", "13:00", "13pm")
        import re
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?|(\d{1,2}):(\d{2})'
        time_match = re.search(time_pattern, date_str)
        if time_match:
            if time_match.group(4):  # HH:MM format
                hour = int(time_match.group(4))
                minute = int(time_match.group(5))
                result_date = result_date.replace(hour=hour, minute=minute)
            else:  # 12-hour format
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                am_pm = time_match.group(3)
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                result_date = result_date.replace(hour=hour, minute=minute)
        
        # Parse day references
        days_ahead = 0
        if 'today' in date_str:
            days_ahead = 0
        elif 'tomorrow' in date_str:
            days_ahead = 1
        elif 'in' in date_str:
            # Extract number of days (e.g., "in 2 days")
            days_match = re.search(r'in\s+(\d+)\s+days?', date_str)
            if days_match:
                days_ahead = int(days_match.group(1))
        
        # Parse weekday
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for i, day in enumerate(weekdays):
            if day in date_str:
                current_weekday = now.weekday()
                target_weekday = i
                days_until = (target_weekday - current_weekday) % 7
                if days_until == 0 and 'next' in date_str:
                    days_until = 7
                elif days_until == 0 and 'today' not in date_str:
                    days_until = 7  # If today is the weekday, assume next week
                days_ahead = days_until
                break
        
        result_date = now + timedelta(days=days_ahead)
        if time_match:
            # Re-apply time after calculating the date
            if time_match.group(4):
                hour = int(time_match.group(4))
                minute = int(time_match.group(5))
                result_date = result_date.replace(hour=hour, minute=minute)
            else:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                am_pm = time_match.group(3)
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                result_date = result_date.replace(hour=hour, minute=minute)
        
        return result_date
    
    def _format_ical_datetime(self, dt_str: str) -> str:
        """Format datetime string for iCal format."""
        try:
            if isinstance(dt_str, str):
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            else:
                dt = dt_str
            
            # Format as YYYYMMDDTHHMMSSZ
            return dt.strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    
    async def _create_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new calendar event."""
        import uuid
        import logging
        logger = logging.getLogger(__name__)
        
        title = arguments.get("title")
        start_time_str = arguments.get("start_time")
        end_time_str = arguments.get("end_time")
        action = arguments.get("action", "create")
        
        logger.info(f"[CALENDAR TOOL] Creating event with arguments: {json.dumps(arguments, indent=2)}")
        logger.info(f"[CALENDAR TOOL] Extracted - title: {title}, start_time: {start_time_str}, end_time: {end_time_str}")
        
        # If title is missing, try to extract from arguments or use a default
        if not title:
            # Try to find title in other fields or use default
            title = arguments.get("name") or arguments.get("event_name") or "Meeting"
            logger.warning(f"[CALENDAR TOOL] Title was missing, using fallback: {title}")
        
        if not start_time_str or not end_time_str:
            missing = []
            if not start_time_str:
                missing.append("start_time")
            if not end_time_str:
                missing.append("end_time")
            error_msg = f"Missing required parameters for 'create' action: {', '.join(missing)}. Received arguments: {json.dumps(arguments)}"
            logger.error(f"[CALENDAR TOOL] {error_msg}")
            return {
                "error": error_msg,
                "result": None
            }
        
        # Parse natural language dates
        start_time_dt = self._parse_natural_language_date(start_time_str)
        end_time_dt = self._parse_natural_language_date(end_time_str)
        
        if not start_time_dt or not end_time_dt:
            return {
                "error": f"Could not parse date/time: start_time={start_time_str}, end_time={end_time_str}",
                "result": None
            }
        
        # Ensure end_time is after start_time
        if end_time_dt <= start_time_dt:
            # Default to 1 hour duration if end_time is before or equal to start_time
            end_time_dt = start_time_dt + timedelta(hours=1)
        
        # Check for all-day event
        all_day = arguments.get("all_day", False)
        if all_day:
            # For all-day events, set to start of day and end of day
            start_time_dt = start_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time_dt = end_time_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        start_time = start_time_dt.isoformat()
        end_time = end_time_dt.isoformat()
        
        events = self._load_events()
        
        # Check for overlapping events BEFORE creating
        conflicts = self._find_overlapping_events(events, start_time_dt, end_time_dt, exclude_id=None)
        
        event = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": arguments.get("description", ""),
            "start_time": start_time,
            "end_time": end_time,
            "location": arguments.get("location", ""),
            "all_day": all_day,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        events.append(event)
        self._save_events(events)
        
        # Broadcast WebSocket event
        try:
            from ...websocket_manager import get_websocket_manager
            ws_manager = get_websocket_manager()
            await ws_manager.broadcast_calendar_event_created(event)
            await ws_manager.broadcast_calendar_events_changed()
        except Exception as e:
            logger.debug(f"Failed to broadcast calendar event created: {e}")
        
        result = {
            "event": event,
            "conflicts": conflicts if conflicts else [],
            "has_conflicts": len(conflicts) > 0
        }
        
        if conflicts:
            logger.warning(f"[CALENDAR TOOL] Created event with {len(conflicts)} overlapping event(s)")
        
        return {
            "result": result,
            "error": None
        }
    
    async def _list_events(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List all calendar events."""
        events = self._load_events()
        
        # Filter by date range if provided
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        
        # Handle natural language date queries (e.g., "today", "tomorrow")
        filter_today = arguments.get("filter_today", False)
        filter_date = arguments.get("filter_date")  # Specific date to filter
        
        if filter_today or filter_date:
            now = datetime.now()
            if filter_today:
                # Filter for events today
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                filtered = []
                for event in events:
                    try:
                        event_start = datetime.fromisoformat(event.get("start_time", "").replace("Z", "+00:00"))
                        # Remove timezone for comparison
                        if event_start.tzinfo:
                            event_start = event_start.replace(tzinfo=None)
                        if today_start <= event_start <= today_end:
                            filtered.append(event)
                    except (ValueError, AttributeError):
                        # Skip events with invalid dates
                        continue
                events = filtered
            elif filter_date:
                # Filter for events on a specific date
                try:
                    filter_dt = self._parse_natural_language_date(filter_date)
                    if filter_dt:
                        filter_start = filter_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                        filter_end = filter_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                        filtered = []
                        for event in events:
                            try:
                                event_start = datetime.fromisoformat(event.get("start_time", "").replace("Z", "+00:00"))
                                if event_start.tzinfo:
                                    event_start = event_start.replace(tzinfo=None)
                                if filter_start <= event_start <= filter_end:
                                    filtered.append(event)
                            except (ValueError, AttributeError):
                                continue
                        events = filtered
                except Exception:
                    pass  # If parsing fails, return all events
        
        if start_date or end_date:
            filtered = []
            for event in events:
                event_start_str = event.get("start_time", "")
                try:
                    # Parse event start time for proper date comparison
                    event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                    if event_start.tzinfo:
                        event_start = event_start.replace(tzinfo=None)
                    
                    # Parse filter dates if provided
                    if start_date:
                        try:
                            filter_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                            if filter_start.tzinfo:
                                filter_start = filter_start.replace(tzinfo=None)
                            if event_start < filter_start:
                                continue
                        except (ValueError, AttributeError):
                            # Fallback to string comparison
                            if event_start_str < start_date:
                                continue
                    
                    if end_date:
                        try:
                            filter_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                            if filter_end.tzinfo:
                                filter_end = filter_end.replace(tzinfo=None)
                            if event_start > filter_end:
                                continue
                        except (ValueError, AttributeError):
                            # Fallback to string comparison
                            if event_start_str > end_date:
                                continue
                    
                    filtered.append(event)
                except (ValueError, AttributeError):
                    # If parsing fails, skip this event
                    continue
            events = filtered
        
        # Sort by start_time
        events.sort(key=lambda x: x.get("start_time", ""))
        
        return {
            "result": {
                "events": events,
                "count": len(events)
            },
            "error": None
        }
    
    async def _get_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a specific event by ID."""
        event_id = arguments.get("event_id")
        if not event_id:
            return {
                "error": "event_id is required",
                "result": None
            }
        
        events = self._load_events()
        for event in events:
            if event.get("id") == event_id:
                return {
                    "result": event,
                    "error": None
                }
        
        return {
            "error": "Event not found",
            "result": None
        }
    
    async def _update_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing event."""
        event_id = arguments.get("event_id")
        if not event_id:
            return {
                "error": "event_id is required",
                "result": None
            }
        
        events = self._load_events()
        for i, event in enumerate(events):
            if event.get("id") == event_id:
                # Check for conflicts if times are being updated
                original_start = event.get("start_time")
                original_end = event.get("end_time")
                
                # Parse new times if provided
                new_start_time_dt = None
                new_end_time_dt = None
                
                if "start_time" in arguments:
                    new_start_time_str = arguments.get("start_time")
                    new_start_time_dt = self._parse_natural_language_date(new_start_time_str)
                    if not new_start_time_dt:
                        return {
                            "error": f"Could not parse start_time: {new_start_time_str}",
                            "result": None
                        }
                
                if "end_time" in arguments:
                    new_end_time_str = arguments.get("end_time")
                    new_end_time_dt = self._parse_natural_language_date(new_end_time_str)
                    if not new_end_time_dt:
                        return {
                            "error": f"Could not parse end_time: {new_end_time_str}",
                            "result": None
                        }
                
                # Use new times or keep original
                if new_start_time_dt:
                    final_start_dt = new_start_time_dt
                else:
                    final_start_dt = datetime.fromisoformat(original_start.replace("Z", "+00:00"))
                
                if new_end_time_dt:
                    final_end_dt = new_end_time_dt
                else:
                    final_end_dt = datetime.fromisoformat(original_end.replace("Z", "+00:00"))
                
                if final_start_dt.tzinfo:
                    final_start_dt = final_start_dt.replace(tzinfo=None)
                if final_end_dt.tzinfo:
                    final_end_dt = final_end_dt.replace(tzinfo=None)
                
                # Check for conflicts (excluding the event being updated)
                conflicts = self._find_overlapping_events(events, final_start_dt, final_end_dt, exclude_id=event_id)
                
                # Update event fields
                if "title" in arguments:
                    event["title"] = arguments["title"]
                if "description" in arguments:
                    event["description"] = arguments["description"]
                if "location" in arguments:
                    event["location"] = arguments["location"]
                if "all_day" in arguments:
                    event["all_day"] = arguments["all_day"]
                
                if new_start_time_dt:
                    if event.get("all_day"):
                        new_start_time_dt = new_start_time_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    event["start_time"] = new_start_time_dt.isoformat()
                
                if new_end_time_dt:
                    if event.get("all_day"):
                        new_end_time_dt = new_end_time_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                    event["end_time"] = new_end_time_dt.isoformat()
                
                event["updated_at"] = datetime.utcnow().isoformat()
                events[i] = event
                self._save_events(events)
                
                result = {
                    "event": event,
                    "conflicts": conflicts if conflicts else [],
                    "has_conflicts": len(conflicts) > 0
                }
                
                if conflicts:
                    logger.warning(f"[CALENDAR TOOL] Updated event with {len(conflicts)} overlapping event(s)")
                
                return {
                    "result": result,
                    "error": None
                }
        
        return {
            "error": "Event not found",
            "result": None
        }
    
    async def _delete_event(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an event."""
        event_id = arguments.get("event_id")
        if not event_id:
            return {
                "error": "event_id is required",
                "result": None
            }
        
        events = self._load_events()
        for i, event in enumerate(events):
            if event.get("id") == event_id:
                deleted = events.pop(i)
                self._save_events(events)
                
                # Broadcast WebSocket event
                try:
                    from ...websocket_manager import get_websocket_manager
                    ws_manager = get_websocket_manager()
                    await ws_manager.broadcast_calendar_event_deleted(event_id)
                    await ws_manager.broadcast_calendar_events_changed()
                except Exception as e:
                    logger.debug(f"Failed to broadcast calendar event deleted: {e}")
                
                return {
                    "result": {"deleted": deleted},
                    "error": None
                }
        
        return {
            "error": "Event not found",
            "result": None
        }
    
    async def _export_calendar(self) -> Dict[str, Any]:
        """Export calendar as iCal file path."""
        events = self._load_events()
        self._update_ical_file(events)
        
        return {
            "result": {
                "ical_file": str(self.calendar_file),
                "event_count": len(events)
            },
            "error": None
        }
    
    async def _clear_all_events(self) -> Dict[str, Any]:
        """Clear all events from the calendar."""
        try:
            # Clear events.json
            events_file = self.calendar_dir / "events.json"
            if events_file.exists():
                with open(events_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, indent=2)
            
            # Clear calendar.ics
            if self.calendar_file.exists():
                with open(self.calendar_file, 'w', encoding='utf-8') as f:
                    f.write("BEGIN:VCALENDAR\n")
                    f.write("VERSION:2.0\n")
                    f.write("PRODID:-//Personal Assistant//Calendar//EN\n")
                    f.write("CALSCALE:GREGORIAN\n")
                    f.write("METHOD:PUBLISH\n")
                    f.write("END:VCALENDAR\n")
            
            logger.info("Cleared all calendar events")
            return {
                "result": {
                    "cleared": True,
                    "message": "All calendar events have been cleared"
                },
                "error": None
            }
        except Exception as e:
            logger.error(f"Error clearing calendar: {e}")
            return {
                "error": f"Failed to clear calendar: {str(e)}",
                "result": None
            }
    
    def _find_overlapping_events(self, events: List[Dict[str, Any]], start_time: datetime, end_time: datetime, exclude_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find events that overlap with the given time range.
        
        Args:
            events: List of all events
            start_time: Start time of the event to check
            end_time: End time of the event to check
            exclude_id: Event ID to exclude from check (for updates)
            
        Returns:
            List of overlapping events
        """
        conflicts = []
        
        for event in events:
            if exclude_id and event.get("id") == exclude_id:
                continue
            
            try:
                event_start_str = event.get("start_time", "")
                event_end_str = event.get("end_time", "")
                
                if not event_start_str or not event_end_str:
                    continue
                
                # Parse event times
                event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                event_end = datetime.fromisoformat(event_end_str.replace("Z", "+00:00"))
                
                # Remove timezone for comparison
                if event_start.tzinfo:
                    event_start = event_start.replace(tzinfo=None)
                if event_end.tzinfo:
                    event_end = event_end.replace(tzinfo=None)
                
                # Check for overlap: two events overlap if one starts before the other ends
                # and ends after the other starts
                if (start_time < event_end and end_time > event_start):
                    conflicts.append({
                        "id": event.get("id"),
                        "title": event.get("title"),
                        "start_time": event_start_str,
                        "end_time": event_end_str,
                        "overlap_type": self._get_overlap_type(start_time, end_time, event_start, event_end)
                    })
            except Exception as e:
                logger.warning(f"Error checking overlap for event {event.get('id')}: {e}")
                continue
        
        return conflicts
    
    def _get_overlap_type(self, start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> str:
        """Determine the type of overlap between two events.
        
        Returns:
            Type of overlap: 'full', 'partial_start', 'partial_end', 'contains', 'contained'
        """
        if start1 <= start2 and end1 >= end2:
            return "contains"  # Event 1 contains event 2
        elif start2 <= start1 and end2 >= end1:
            return "contained"  # Event 1 is contained in event 2
        elif start1 < start2 and end1 > start2:
            return "partial_start"  # Event 1 starts before but overlaps
        elif start1 < end2 and end1 > end2:
            return "partial_end"  # Event 1 ends after but overlaps
        else:
            return "full"  # Full overlap
    
    async def _delete_day_events(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Delete all events on a specific date."""
        date_str = arguments.get("date")
        if not date_str:
            return {
                "error": "date parameter is required for delete_day action",
                "result": None
            }
        
        # Parse the date
        target_date = self._parse_natural_language_date(date_str)
        if not target_date:
            return {
                "error": f"Could not parse date: {date_str}",
                "result": None
            }
        
        # Set to start and end of day
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        events = self._load_events()
        deleted_events = []
        remaining_events = []
        
        for event in events:
            try:
                event_start_str = event.get("start_time", "")
                if not event_start_str:
                    remaining_events.append(event)
                    continue
                
                event_start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
                if event_start.tzinfo:
                    event_start = event_start.replace(tzinfo=None)
                
                # Check if event is on this date
                if day_start <= event_start <= day_end:
                    deleted_events.append(event)
                else:
                    remaining_events.append(event)
            except Exception as e:
                logger.warning(f"Error processing event for delete_day: {e}")
                remaining_events.append(event)
        
        self._save_events(remaining_events)
        
        return {
            "result": {
                "deleted_count": len(deleted_events),
                "deleted_events": deleted_events,
                "date": date_str
            },
            "error": None
        }
    
    async def _check_conflicts(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a time slot has conflicts with existing events."""
        start_time_str = arguments.get("start_time")
        end_time_str = arguments.get("end_time")
        date_str = arguments.get("date")
        
        if not start_time_str or not end_time_str:
            if date_str:
                # Check entire day
                target_date = self._parse_natural_language_date(date_str)
                if not target_date:
                    return {
                        "error": f"Could not parse date: {date_str}",
                        "result": None
                    }
                start_time_dt = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time_dt = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                return {
                    "error": "start_time and end_time (or date) are required for check_conflicts action",
                    "result": None
                }
        else:
            start_time_dt = self._parse_natural_language_date(start_time_str)
            end_time_dt = self._parse_natural_language_date(end_time_str)
            
            if not start_time_dt or not end_time_dt:
                return {
                    "error": f"Could not parse date/time: start_time={start_time_str}, end_time={end_time_str}",
                    "result": None
                }
        
        events = self._load_events()
        conflicts = self._find_overlapping_events(events, start_time_dt, end_time_dt)
        
        return {
            "result": {
                "available": len(conflicts) == 0,
                "has_conflicts": len(conflicts) > 0,
                "conflicts": conflicts,
                "conflict_count": len(conflicts)
            },
            "error": None
        }

