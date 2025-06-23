"""Tool definitions for CalendarAgent."""
from typing import Any, Dict, List

tools: List[Dict[str, Any]] = [
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
            "description": "Create a recurring calendar event with a specific recurrence rule. Use this for any event that repeats on a daily, weekly, monthly, or yearly basis, such as workouts, classes, alarms, or birthdays.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Name of the recurring event. Example: 'Wake Up', 'Gym Session', 'Team Meeting'",
                    },
                    "start": {
                        "type": "string",
                        "description": "Start time in 'YYYY-MM-DD HH:MM' format (24-hour clock, local time)",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Length of the event in minutes. Example: 30 for a 30-minute event, 60 for 1 hour",
                    },
                    "pattern": {
                        "type": "object",
                        "description": 'Describes the recurrence pattern. Always include \'type\'. Add \'days\' only if it\'s weekly.\n\nExamples:\n- Daily: { "type": "daily" }\n- Every 2 days: { "type": "daily", "interval": 2 }\n- Weekly on Monday and Wednesday: { "type": "weekly", "days": [1, 3] }\n- Monthly: { "type": "monthly" }\n- Yearly: { "type": "yearly" }',
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "daily",
                                    "weekly",
                                    "monthly",
                                    "yearly",
                                ],
                                "description": "How often the event repeats:\n- 'daily': every X days\n- 'weekly': every X weeks on specified days (see 'days')\n- 'monthly': every X months on the same date\n- 'yearly': every X years on the same date",
                            },
                            "interval": {
                                "type": "integer",
                                "description": "Repeat interval. Example:\n- interval: 1 with type 'daily' = every day\n- interval: 2 with type 'weekly' = every other week",
                                "default": 1,
                            },
                            "max": {
                                "type": "integer",
                                "description": "Maximum number of times the event should repeat. Use -1 for unlimited recurrence.",
                                "default": -1,
                            },
                            "end": {
                                "type": "string",
                                "description": "Optional end date. Format: 'YYYY-MM-DD HH:MM'. If set, event stops on or before this time.",
                                "default": "",
                            },
                            "days": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "For weekly recurrence only. List of weekdays: 0 = Sunday, 1 = Monday, ..., 6 = Saturday. Example: [1,3,5] for Mon/Wed/Fri.",
                                "default": [],
                            },
                        },
                        "required": ["type"],
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional additional info for the event. Example: 'Take meds after waking up'.",
                        "default": "",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional label for organizing events. Example: 'Health', 'Work', 'Personal'.",
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
            "description": "Update a recurring event by changing its title, time, duration, or recurrence pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID of the recurring event to update. This must already exist.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New or unchanged title for the event. Example: 'Wake Up'",
                    },
                    "start": {
                        "type": "string",
                        "description": "New start time in 'YYYY-MM-DD HH:MM' format",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Updated length of the event in minutes",
                    },
                    "pattern": {
                        "type": "object",
                        "description": 'Updated recurrence pattern. Use the same structure as add_recurring_event.\n\nExamples:\n- Daily: { "type": "daily" }\n- Every 3 days: { "type": "daily", "interval": 3 }\n- Weekly on Tue/Thu: { "type": "weekly", "days": [2, 4] }\n- Monthly: { "type": "monthly" }\n- Yearly: { "type": "yearly" }',
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "daily",
                                    "weekly",
                                    "monthly",
                                    "yearly",
                                ],
                                "description": "Type of recurrence: daily / weekly / monthly / yearly",
                            },
                            "interval": {
                                "type": "integer",
                                "description": "How frequently the event repeats. Example: 1 = every period, 2 = every other period",
                                "default": 1,
                            },
                            "max": {
                                "type": "integer",
                                "description": "Maximum number of occurrences. -1 for infinite repetition",
                                "default": -1,
                            },
                            "end": {
                                "type": "string",
                                "description": "Cutoff date/time for recurrence (optional). Format: 'YYYY-MM-DD HH:MM'",
                                "default": "",
                            },
                            "days": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Only for weekly recurrence. Days of the week as integers: 0 = Sun, ..., 6 = Sat",
                                "default": [],
                            },
                        },
                        "required": ["type"],
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated description text (optional)",
                        "default": "",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional new category label",
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
