# jarvis/agents/calendar_agent.py
from typing import Any, Dict, Set, List
import json
import uuid
from .base import NetworkAgent
from .message import Message
from ..services.calendar_service import CalendarService
from ..ai_clients import BaseAIClient
from ..logger import JarvisLogger
from typing import Any, Dict, Set, List
from datetime import datetime, timedelta, timezone


class CollaborativeCalendarAgent(NetworkAgent):
    """Calendar agent that collaborates with other agents"""

    def __init__(
        self,
        ai_client: BaseAIClient,
        calendar_service: CalendarService,
        logger: JarvisLogger | None = None,
    ):
        super().__init__("CalendarAgent", logger)
        self.calendar_service = calendar_service
        self.ai_client = ai_client

        # Tools and prompt for natural language commands
        self.tools = [
            # ===== EXISTING ROUTES =====
            {
                "type": "function",
                "function": {
                    "name": "get_all_events",
                    "description": "Get all events in the calendar",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_next_event",
                    "description": "Get the next upcoming event",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_today_events",
                    "description": "Get all events scheduled for today",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_tomorrow_events",
                    "description": "Get all events scheduled for tomorrow",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events_by_date",
                    "description": "Get all events for a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            }
                        },
                        "required": ["date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_week_events",
                    "description": "Get events for a week starting from the given date (or current week if not specified)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date of the week in YYYY-MM-DD format (optional)",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_month_events",
                    "description": "Get events for a specific month",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "year_month": {
                                "type": "string",
                                "description": "Month in YYYY-MM format (optional, defaults to current month)",
                            }
                        },
                        "required": [],
                    },
                },
            },
            # ===== SEARCH AND FILTERING =====
            {
                "type": "function",
                "function": {
                    "name": "search_events",
                    "description": "Search events by query string (searches title and description)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query string",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results to return (optional)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events_in_range",
                    "description": "Get events within a date range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format",
                            },
                        },
                        "required": ["start_date", "end_date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events_by_duration",
                    "description": "Get events filtered by duration",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "min_minutes": {
                                "type": "integer",
                                "description": "Minimum duration in minutes (optional)",
                            },
                            "max_minutes": {
                                "type": "integer",
                                "description": "Maximum duration in minutes (optional)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            # ===== CATEGORIES =====
            {
                "type": "function",
                "function": {
                    "name": "get_categories",
                    "description": "Get all available event categories",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events_by_category",
                    "description": "Get events filtered by category",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category name to filter by",
                            }
                        },
                        "required": ["category"],
                    },
                },
            },
            # ===== CONFLICTS AND FREE TIME =====
            {
                "type": "function",
                "function": {
                    "name": "check_conflicts",
                    "description": "Check if there are scheduling conflicts at a specific time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "time": {
                                "type": "string",
                                "description": "Time to check in YYYY-MM-DD HH:MM format",
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration to check in minutes (default: 60)",
                                "default": 60,
                            },
                        },
                        "required": ["time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_event_time",
                    "description": "Validate if an event can be scheduled at a specific time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "time": {
                                "type": "string",
                                "description": "Time to validate in YYYY-MM-DD HH:MM format",
                            },
                            "duration_seconds": {
                                "type": "integer",
                                "description": "Duration in seconds (default: 3600)",
                                "default": 3600,
                            },
                            "title": {
                                "type": "string",
                                "description": "Event title for validation (default: Test Event)",
                                "default": "Test Event",
                            },
                        },
                        "required": ["time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_free_slots",
                    "description": "Find free time slots on a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format (defaults to today)",
                            },
                            "start_hour": {
                                "type": "integer",
                                "description": "Start hour (0–23, defaults to current hour)",
                            },
                            "end_hour": {
                                "type": "integer",
                                "description": "End hour (0–23, defaults to 17)",
                                "default": 17,
                            },
                            "min_duration_minutes": {
                                "type": "integer",
                                "description": "Minimum slot duration in minutes (default: 30)",
                                "default": 30,
                            },
                        },
                        "required": ["date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_next_available_slot",
                    "description": "Find the next available time slot",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Required duration in minutes (default: 60)",
                                "default": 60,
                            },
                            "after": {
                                "type": "string",
                                "description": "Find slot after this time in YYYY-MM-DD HH:MM format (optional)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            # ===== STATISTICS =====
            {
                "type": "function",
                "function": {
                    "name": "get_event_stats",
                    "description": "Get statistics for events in a date range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format",
                            },
                        },
                        "required": ["start_date", "end_date"],
                    },
                },
            },
            # ===== CREATE/UPDATE OPERATIONS =====
            {
                "type": "function",
                "function": {
                    "name": "add_event",
                    "description": "Add a new event to the calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title"},
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            },
                            "time": {
                                "type": "string",
                                "description": "Time in HH:MM format",
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration in minutes (default: 60)",
                                "default": 60,
                            },
                            "description": {
                                "type": "string",
                                "description": "Event description (optional)",
                                "default": "",
                            },
                            "category": {
                                "type": "string",
                                "description": "Event category (optional)",
                                "default": "",
                            },
                        },
                        "required": ["title", "date", "time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_event",
                    "description": "Update an entire event (all fields required)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"},
                            "title": {"type": "string", "description": "New title"},
                            "time": {
                                "type": "string",
                                "description": "New time in YYYY-MM-DD HH:MM format",
                            },
                            "duration_seconds": {
                                "type": "integer",
                                "description": "Duration in seconds (default: 3600)",
                                "default": 3600,
                            },
                            "description": {
                                "type": "string",
                                "description": "New description",
                                "default": "",
                            },
                            "category": {
                                "type": "string",
                                "description": "New category",
                                "default": "",
                            },
                        },
                        "required": ["event_id", "title", "time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_event_fields",
                    "description": "Update specific fields of an event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"},
                            "fields": {
                                "type": "object",
                                "description": "Object containing fields to update (e.g., {title: 'New Title', category: 'Work'})",
                            },
                        },
                        "required": ["event_id", "fields"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reschedule_event",
                    "description": "Reschedule an event to a new date and time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"},
                            "new_date": {
                                "type": "string",
                                "description": "New date in YYYY-MM-DD format",
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New time in HH:MM format",
                            },
                            "keep_duration": {
                                "type": "boolean",
                                "description": "Keep original duration (default: true)",
                                "default": True,
                            },
                        },
                        "required": ["event_id", "new_date", "new_time"],
                    },
                },
            },
            # ===== RECURRING EVENTS =====
            {
                "type": "function",
                "function": {
                    "name": "get_recurring_events",
                    "description": "List all recurring events",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_recurring_event",
                    "description": "Create a recurring event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title"},
                            "start": {
                                "type": "string",
                                "description": "Start time in YYYY-MM-DD HH:MM format",
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration in minutes",
                            },
                            "pattern": {
                                "type": "object",
                                "description": "Recurrence pattern description",
                            },
                            "description": {
                                "type": "string",
                                "description": "Event description",
                                "default": "",
                            },
                            "category": {
                                "type": "string",
                                "description": "Event category",
                                "default": "",
                            },
                        },
                        "required": ["title", "start", "duration_minutes", "pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_recurring_event",
                    "description": "Update an existing recurring event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"},
                            "title": {"type": "string", "description": "Event title"},
                            "start": {
                                "type": "string",
                                "description": "Start time in YYYY-MM-DD HH:MM format",
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Duration in minutes",
                            },
                            "pattern": {
                                "type": "object",
                                "description": "Recurrence pattern description",
                            },
                            "description": {
                                "type": "string",
                                "description": "Event description",
                                "default": "",
                            },
                            "category": {
                                "type": "string",
                                "description": "Event category",
                                "default": "",
                            },
                        },
                        "required": [
                            "event_id",
                            "title",
                            "start",
                            "duration_minutes",
                            "pattern",
                        ],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_recurring_event",
                    "description": "Delete a recurring event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"}
                        },
                        "required": ["event_id"],
                    },
                },
            },
            # ===== BULK OPERATIONS =====
            {
                "type": "function",
                "function": {
                    "name": "add_events_bulk",
                    "description": "Add multiple events at once",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "events": {
                                "type": "array",
                                "description": "Array of event objects",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "time": {
                                            "type": "string",
                                            "description": "YYYY-MM-DD HH:MM",
                                        },
                                        "duration_seconds": {
                                            "type": "integer",
                                            "default": 3600,
                                        },
                                        "description": {
                                            "type": "string",
                                            "default": "",
                                        },
                                        "category": {"type": "string", "default": ""},
                                    },
                                    "required": ["title", "time"],
                                },
                            }
                        },
                        "required": ["events"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_events_bulk",
                    "description": "Delete multiple events by their IDs",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_ids": {
                                "type": "array",
                                "description": "Array of event IDs to delete",
                                "items": {"type": "string"},
                            }
                        },
                        "required": ["event_ids"],
                    },
                },
            },
            # ===== DELETE OPERATIONS =====
            {
                "type": "function",
                "function": {
                    "name": "delete_event",
                    "description": "Delete an event by its ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"},
                            "soft_delete": {
                                "type": "boolean",
                                "description": "Soft delete (can be restored) instead of permanent delete",
                                "default": False,
                            },
                        },
                        "required": ["event_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_all_events",
                    "description": "Delete all events (use with caution!)",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_events_by_date",
                    "description": "Delete all events on a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            }
                        },
                        "required": ["date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_events_in_week",
                    "description": "Delete all events in a week starting from the given date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date of the week in YYYY-MM-DD format",
                            }
                        },
                        "required": ["start_date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_events_before",
                    "description": "Delete all events before a specific datetime",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "datetime_str": {
                                "type": "string",
                                "description": "Datetime in YYYY-MM-DDTHH:MM format",
                            }
                        },
                        "required": ["datetime_str"],
                    },
                },
            },
            # ===== SOFT DELETE AND RESTORE =====
            {
                "type": "function",
                "function": {
                    "name": "get_deleted_events",
                    "description": "Get all soft-deleted events that can be restored",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "restore_event",
                    "description": "Restore a soft-deleted event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {
                                "type": "string",
                                "description": "Event ID to restore",
                            }
                        },
                        "required": ["event_id"],
                    },
                },
            },
            # ===== SUMMARY AND ANALYSIS =====
            {
                "type": "function",
                "function": {
                    "name": "get_schedule_summary",
                    "description": "Get a summary of the schedule for a given range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "string",
                                "description": "Range: 'today', 'week', or 'month'",
                                "enum": ["today", "week", "month"],
                                "default": "today",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_busy_days",
                    "description": "Find days with many events within a date range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format",
                            },
                            "threshold_events": {
                                "type": "integer",
                                "description": "Minimum events to consider a day busy (default: 3)",
                                "default": 3,
                            },
                        },
                        "required": ["start_date", "end_date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_overlapping_events",
                    "description": "Find all events that overlap with each other",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            # ===== ADVANCED HELPERS =====
            {
                "type": "function",
                "function": {
                    "name": "find_best_time_for_event",
                    "description": "Find the best available time slot across multiple dates",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Required duration in minutes",
                            },
                            "preferred_dates": {
                                "type": "array",
                                "description": "List of preferred dates in YYYY-MM-DD format",
                                "items": {"type": "string"},
                            },
                            "working_hours": {
                                "type": "array",
                                "description": "Working hours as [start_hour, end_hour] (default: [9, 17])",
                                "items": {"type": "integer"},
                                "minItems": 2,
                                "maxItems": 2,
                                "default": [9, 17],
                            },
                        },
                        "required": ["duration_minutes", "preferred_dates"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_event_by_id",
                    "description": "Get a specific event by its ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "Event ID"}
                        },
                        "required": ["event_id"],
                    },
                },
            },
        ]

        self.system_prompt = (
            "You are Jarvis, the AI assistant from Iron Man. "
            "Your user is Owen Stepan taking on the role of Tony Stark. "
            "Respond in a clear, conversational style without using asterisks or "
            "other non-textual formatting. You help manage the user's schedule by:\n"
            "1. Understanding natural language requests\n"
            "2. Breaking down complex tasks into calendar API calls\n"
            "3. Executing the necessary operations in the correct order\n"
            "4. Explaining the results plainly\n\n"
            "Current date: {current_date}. Always interpret dates relative to this value.\n\n"
            "You have access to comprehensive calendar management functions including:\n"
            "- Viewing events (by date, week, month, or with filters)\n"
            "- Searching and categorizing events\n"
            "- Adding, updating, and deleting events (including bulk operations)\n"
            "- Finding free time slots and checking for conflicts\n"
            "- Analyzing schedule patterns and statistics\n"
            "- Managing soft-deleted events (can be restored)\n"
            "- Handling recurring events\n\n"
            "When working with events, remember:\n"
            "- Events have an ID, title, time, duration, description, and optional category\n"
            "- Times are in 'YYYY-MM-DD HH:MM' format\n"
            "- Durations are typically in minutes for user-facing functions\n"
            "- Some functions use duration_seconds internally\n"
            "- Soft delete allows events to be restored later\n"
            "- Always validate times before adding events to avoid conflicts"
        )

        self._function_map = {
            # Existing routes
            "get_all_events": self.calendar_service.get_all_events,
            "get_next_event": self.calendar_service.get_next_event,
            "get_today_events": self.calendar_service.get_today_events,
            "get_tomorrow_events": self.calendar_service.get_tomorrow_events,
            "get_events_by_date": self.calendar_service.get_events_by_date,
            "get_week_events": self.calendar_service.get_week_events,
            "get_month_events": self.calendar_service.get_month_events,
            # Search and filtering
            "search_events": self.calendar_service.search_events,
            "get_events_in_range": self.calendar_service.get_events_in_range,
            "get_events_by_duration": self.calendar_service.get_events_by_duration,
            # Categories
            "get_categories": self.calendar_service.get_categories,
            "get_events_by_category": self.calendar_service.get_events_by_category,
            # Conflicts and free time
            "check_conflicts": self.calendar_service.check_conflicts,
            "validate_event_time": self.calendar_service.validate_event_time,
            "find_free_slots": self.calendar_service.find_free_slots,
            "find_next_available_slot": self.calendar_service.find_next_available_slot,
            # Statistics
            "get_event_stats": self.calendar_service.get_event_stats,
            # Create/Update operations
            "add_event": self.calendar_service.add_event,
            "update_event": self.calendar_service.update_event,
            "update_event_fields": self.calendar_service.update_event_fields,
            "reschedule_event": self.calendar_service.reschedule_event,
            # Recurring events
            "get_recurring_events": self.calendar_service.get_recurring_events,
            "add_recurring_event": self.calendar_service.add_recurring_event,
            "update_recurring_event": self.calendar_service.update_recurring_event,
            "delete_recurring_event": self.calendar_service.delete_recurring_event,
            # Bulk operations
            "add_events_bulk": self.calendar_service.add_events_bulk,
            "delete_events_bulk": self.calendar_service.delete_events_bulk,
            # Delete operations
            "delete_event": self.calendar_service.delete_event,
            "delete_all_events": self.calendar_service.delete_all_events,
            "delete_events_by_date": self.calendar_service.delete_events_by_date,
            "delete_events_in_week": self.calendar_service.delete_events_in_week,
            "delete_events_before": self.calendar_service.delete_events_before,
            # Soft delete and restore
            "get_deleted_events": self.calendar_service.get_deleted_events,
            "restore_event": self.calendar_service.restore_event,
            # Summary and analysis
            "get_schedule_summary": self.calendar_service.get_schedule_summary,
            "get_busy_days": self.calendar_service.get_busy_days,
            "get_overlapping_events": self.calendar_service.get_overlapping_events,
            # Advanced helpers
            "find_best_time_for_event": self.calendar_service.find_best_time_for_event,
            "get_event_by_id": self.calendar_service.get_event_by_id,
        }

    @property
    def description(self) -> str:
        return "Manages calendar, scheduling, and time-related operations with full CRUD capabilities"

    @property
    def capabilities(self) -> Set[str]:
        return {
            # View capabilities
            "view_calendar_schedule",
            "view_calendar_events",
            "search_calendar_events",
            "get_calendar_statistics",
            "view_upcoming_appointments",
            "check_calendar_availability",
            # Modification capabilities
            "add_calendar_event",
            "schedule_appointment",
            "update_calendar_event",
            "reschedule_appointment",
            "remove_calendar_event",
            "cancel_appointment",
            "bulk_calendar_operations",
            # Time-specific queries
            "find_free_time_slots",
            "check_scheduling_conflicts",
            "analyze_calendar_patterns",
            "find_meeting_times",
            # Calendar management
            "manage_event_categories",
            "restore_deleted_appointments",
            "organize_calendar",
            # Date/time specific
            "get_today_schedule",
            "get_week_schedule",
            "get_month_schedule",
            "check_busy_days",
            "manage_recurring_events",
        }

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        func = self._function_map.get(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}
        try:
            self.logger.log("INFO", f"Calling {function_name}", json.dumps(arguments))

            # Handle special case for working_hours parameter
            if (
                function_name == "find_best_time_for_event"
                and "working_hours" in arguments
            ):
                if (
                    isinstance(arguments["working_hours"], list)
                    and len(arguments["working_hours"]) == 2
                ):
                    arguments["working_hours"] = tuple(arguments["working_hours"])

            result = await func(**arguments)
            self.logger.log("INFO", f"Result {function_name}", json.dumps(result))
            return result
        except Exception as exc:
            error = {
                "error": str(exc),
                "function": function_name,
                "arguments": arguments,
            }
            self.logger.log("ERROR", f"Error {function_name}", json.dumps(error))
            return error

    async def _process_calendar_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language calendar command using AI."""
        self.logger.log("DEBUG", "Processing NL command", command)
        current_date = self.calendar_service.current_date()
        messages = [
            {
                "role": "system",
                "content": self.system_prompt.format(current_date=current_date),
            },
            {"role": "user", "content": command},
        ]
        actions_taken: List[Dict[str, Any]] = []

        iterations = 0
        MAX_ITERATIONS = 10  # Increased for complex operations
        tool_calls = None
        while iterations < MAX_ITERATIONS:
            message, tool_calls = await self.ai_client.chat(messages, self.tools)
            self.logger.log(
                "INFO", "AI response", getattr(message, "content", str(message))
            )

            if not tool_calls:
                break

            messages.append(message.model_dump())
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)
                self.logger.log("INFO", "Tool call", function_name)
                result = await self._execute_function(function_name, arguments)
                actions_taken.append(
                    {
                        "function": function_name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )

            iterations += 1

        if iterations >= MAX_ITERATIONS:
            self.logger.log("ERROR", "Max iterations reached", str(iterations))

        if tool_calls:
            message, _ = await self.ai_client.chat(messages, [])

        response_text = message.content if hasattr(message, "content") else str(message)
        self.logger.log("INFO", "NL command result", response_text)

        return {"response": response_text, "actions": actions_taken}

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"Handling {capability}", json.dumps(data))

        command_text = data.get("command")
        if command_text and capability != "calendar_command":
            self.logger.log("INFO", "Using command text", command_text)
            result = await self._process_calendar_command(command_text)
            if result:
                await self.send_capability_response(
                    message.from_agent, result, message.request_id, message.id
                )
            return

        # Track active request details so follow-up responses can be managed
        self.active_tasks.setdefault(
            message.request_id,
            {
                "data": data,
                "original_requester": message.from_agent,
                "original_message_id": message.id,
                "responses": [],
            },
        )

        try:
            result = None
            command = data.get("command")
            if not isinstance(command, str):
                await self.send_error(
                    message.from_agent, "Invalid command", message.request_id
                )
                return
            result = await self._process_calendar_command(command)

            if result:
                await self.send_capability_response(
                    message.from_agent, result, message.request_id, message.id
                )

        except Exception as e:
            await self.send_error(message.from_agent, str(e), message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents"""
        request_id = message.request_id

        if request_id not in self.active_tasks:
            return

        task = self.active_tasks[request_id]
        self.logger.log(
            "DEBUG",
            "Capability response received",
            json.dumps({"request_id": request_id, "data": message.content}),
        )
        # Store the response for potential aggregation
        task["responses"].append(
            {
                "from_agent": message.from_agent,
                "content": message.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
