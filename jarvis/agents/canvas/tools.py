# jarvis/agents/canvas/tools.py

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_courses",
            "description": "Get all courses the user is enrolled in",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_concluded": {
                        "type": "boolean",
                        "description": "Whether to include concluded courses",
                        "default": False,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_enrollments",
            "description": "Get all enrollments for the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User ID (defaults to 'self')",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_assignments",
            "description": "Get all assignments for a specific course",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {
                        "type": "string",
                        "description": "The course ID to get assignments for",
                    },
                    "include_concluded": {
                        "type": "boolean",
                        "description": "Whether to include concluded assignments",
                        "default": False,
                    },
                    "recent_only": {
                        "type": "boolean",
                        "description": "Only get recent/upcoming assignments",
                        "default": True,
                    },
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todo",
            "description": "Get to-do items (assignments, discussions, quizzes, calendar events)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_comprehensive_homework",
            "description": "Get comprehensive homework information with full details including due dates, points, submission status, and descriptions. Use this when user asks about homework, assignments, or what they need to do.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_homework_summary",
            "description": "Get a summary of homework focused on weekend assignments",
            "parameters": {
                "type": "object",
                "properties": {
                    "weekend_focus": {
                        "type": "boolean",
                        "description": "Focus on weekend homework",
                        "default": True,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get calendar events from Canvas",
            "parameters": {
                "type": "object",
                "properties": {
                    "upcoming_only": {
                        "type": "boolean",
                        "description": "Only get upcoming events",
                        "default": True,
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notifications",
            "description": "Get account notifications and announcements",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_messages",
            "description": "Get inbox messages and conversations",
            "parameters": {
                "type": "object",
                "properties": {
                    "per_page": {
                        "type": "integer",
                        "description": "Number of messages to retrieve",
                        "default": 50,
                    }
                },
                "required": [],
            },
        },
    },
]
