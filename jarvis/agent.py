from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Tuple

from .ai_clients import BaseAIClient
from .calendar_service import CalendarService


class AICalendarAgent:
    """AI agent that interprets natural language and executes calendar operations."""

    def __init__(self, ai_client: BaseAIClient, calendar_service: CalendarService) -> None:
        self.ai_client = ai_client
        self.calendar_service = calendar_service
        self.tools = [
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
                    "name": "add_event",
                    "description": "Add a new event to the calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            },
                            "time": {
                                "type": "string",
                                "description": "Time in HH:MM format",
                            },
                            "duration_minutes": {"type": "integer", "default": 60},
                            "description": {"type": "string", "default": ""},
                        },
                        "required": ["title", "date", "time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_event",
                    "description": "Delete an event by its ID",
                    "parameters": {
                        "type": "object",
                        "properties": {"event_id": {"type": "string"}},
                        "required": ["event_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_schedule",
                    "description": "Analyze schedule patterns and provide insights",
                    "parameters": {
                        "type": "object",
                        "properties": {"date_range": {"type": "string", "default": "today"}},
                        "required": [],
                    },
                },
            },
        ]
        self.system_prompt = (
            "You are a calendar management assistant. You help users manage their schedule by:\n"
            "1. Understanding their natural language requests\n"
            "2. Breaking down complex requests into individual API calls\n"
            "3. Executing the necessary calendar operations in the correct order\n"
            "4. Providing clear feedback about what was done\n\n"
            "Current date: {current_date}"
        )

        self._function_map = {
            "get_today_events": self.calendar_service.get_today_events,
            "get_events_by_date": self.calendar_service.get_events_by_date,
            "add_event": self.calendar_service.add_event,
            "delete_event": self.calendar_service.delete_event,
            "analyze_schedule": self.calendar_service.analyze_schedule,
        }

    async def _execute_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        func = self._function_map.get(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}
        try:
            result = await func(**arguments)
            return result
        except Exception as exc:
            return {"error": str(exc)}

    async def process_request(self, user_input: str) -> Tuple[str, List[Dict[str, Any]]]:
        current_date = date.today().strftime("%Y-%m-%d")
        messages = [
            {"role": "system", "content": self.system_prompt.format(current_date=current_date)},
            {"role": "user", "content": user_input},
        ]
        actions_taken: List[Dict[str, Any]] = []

        message, tool_calls = await self.ai_client.chat(messages, self.tools)

        if tool_calls:
            messages.append(message)
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)
                result = await self._execute_function(function_name, arguments)
                actions_taken.append({"function": function_name, "arguments": arguments, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
            message, _ = await self.ai_client.chat(messages, [])

        return message.content if hasattr(message, "content") else str(message), actions_taken

    async def process_request_with_reasoning(self, user_input: str) -> Dict[str, Any]:
        response_text, actions = await self.process_request(user_input)
        return {
            "user_input": user_input,
            "response": response_text,
            "actions": actions,
            "success": all("error" not in a.get("result", {}) for a in actions),
        }
