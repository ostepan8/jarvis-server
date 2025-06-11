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
            "Current date (UTC): {current_date}. Always interpret dates relative to this value."
            "Current date: {current_date}. Always interpret dates relative to this value."
        )

        self._function_map = {
            "get_today_events": self.calendar_service.get_today_events,
            "get_events_by_date": self.calendar_service.get_events_by_date,
            "add_event": self.calendar_service.add_event,
            "delete_event": self.calendar_service.delete_event,
        }

    @property
    def description(self) -> str:
        return "Manages calendar, scheduling, and time-related operations"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "view_schedule",
            "add_event",
            "remove_event",
        }

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
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
        MAX_ITERATIONS = 5
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
            self.logger.log("DEBUG", "Using command text", command_text)
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
        # Implement the to
