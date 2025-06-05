from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Tuple

from .ai_clients import BaseAIClient
from .calendar_service import CalendarService
from .logger import JarvisLogger


class AICalendarAgent:
    """AI agent that interprets natural language and executes calendar operations."""

    def __init__(self, ai_client: BaseAIClient, calendar_service: CalendarService, logger: JarvisLogger | None = None) -> None:
        self.ai_client = ai_client
        self.calendar_service = calendar_service
        self.logger = logger or JarvisLogger()
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
            "You are Jarvis, the AI assistant from Iron Man. "
            "Your user is Owen Stepan taking on the role of Tony Stark. "
            "Respond in a clear, conversational style without using asterisks or "
            "other non-textual formatting. You help manage the user's schedule "
            "by:\n"
            "1. Understanding natural language requests\n"
            "2. Breaking down complex tasks into calendar API calls\n"
            "3. Executing the necessary operations in the correct order\n"
            "4. Explaining the results plainly\n\n"
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
            self.logger.log("INFO", f"Calling {function_name}", json.dumps(arguments))
            result = await func(**arguments)
            self.logger.log("INFO", f"Result {function_name}", json.dumps(result))
            return result
        except Exception as exc:
            error = {"error": str(exc)}
            self.logger.log("ERROR", f"Error {function_name}", json.dumps(error))
            return error

    async def process_request(self, user_input: str) -> Tuple[str, List[Dict[str, Any]]]:
        current_date = date.today().strftime("%Y-%m-%d")
        messages = [
            {"role": "system", "content": self.system_prompt.format(current_date=current_date)},
            {"role": "user", "content": user_input},
        ]
        actions_taken: List[Dict[str, Any]] = []

        self.logger.log("INFO", "User request", user_input)

        iterations = 0
        MAX_ITERATIONS = 5
        while iterations < MAX_ITERATIONS:
            message, tool_calls = await self.ai_client.chat(messages, self.tools)
            self.logger.log("INFO", "AI response", getattr(message, "content", str(message)))

            if not tool_calls:
                break

            messages.append(message.model_dump())
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)
                self.logger.log("INFO", "Tool call", function_name)
                result = await self._execute_function(function_name, arguments)
                actions_taken.append({"function": function_name, "arguments": arguments, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

            iterations += 1

        if iterations >= MAX_ITERATIONS:
            self.logger.log("ERROR", "Max iterations reached", str(iterations))

        if tool_calls:
            # If we exited due to reaching max iterations, get a final response without further tool calls
            message, _ = await self.ai_client.chat(messages, [])

        self.logger.log("INFO", "Final response", getattr(message, "content", str(message)))

        return message.content if hasattr(message, "content") else str(message), actions_taken

    async def process_request_with_reasoning(self, user_input: str) -> Dict[str, Any]:
        response_text, actions = await self.process_request(user_input)
        return {
            "user_input": user_input,
            "response": response_text,
            "actions": actions,
            "success": all("error" not in a.get("result", {}) for a in actions),
        }
