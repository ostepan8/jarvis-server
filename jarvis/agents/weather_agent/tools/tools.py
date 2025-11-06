from typing import Any, Dict, List

tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get current weather conditions for a specific location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Specific city name, e.g., 'Chicago', 'New York', 'London'. "
                            "Never use 'current location' - always ask user for city name if unclear."
                        ),
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Get weather forecast for next few days",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Specific city name, e.g., 'Chicago', 'New York', 'London'. "
                            "Never use 'current location'."
                        ),
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to forecast (1-5)",
                        "default": 3,
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_weather_locations",
            "description": "Compare current weather between multiple locations",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of city names to compare",
                    }
                },
                "required": ["locations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_recommendations",
            "description": "Get weather-based recommendations for activities, clothing, travel",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Specific city name, never 'current location'",
                    },
                    "activity": {
                        "type": "string",
                        "description": "Planned activity (e.g., 'outdoor event', 'travel', 'hiking')",
                        "default": "general",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_locations_for_weather_service",
            "description": "Search for location names when user input is unclear",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for location",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_air_quality",
            "description": "Get air quality information for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Specific city name, never 'current location'",
                    }
                },
                "required": ["location"],
            },
        },
    },
]
