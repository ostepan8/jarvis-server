# jarvis/agents/calendar_agent.py
from typing import Any, Dict, Set, List
import json
from datetime import datetime
import uuid
import jmespath

from .base import NetworkAgent
from .message import Message
from ..services.calendar_service import CalendarService
from ..ai_clients import BaseAIClient
from ..logger import JarvisLogger


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

        self.logger.log(
            "INFO",
            "Calendar agent initialized",
            f"capabilities={self.capabilities}",
        )

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
                            "start_time": {
                                "type": "string",
                                "description": "ISO timestamp for event start",
                            },
                            "end_time": {
                                "type": "string",
                                "description": "ISO timestamp for event end",
                            },
                            "duration_minutes": {"type": "integer", "default": 60},
                            "description": {"type": "string", "default": ""},
                        },
                        "required": ["title"],
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
                    "name": "get_schedule_summary",
                    "description": "Get a helpful summary of today's schedule",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {"type": "string", "default": "today"}
                        },
                        "required": [],
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
            "Current date: {current_date}. Always interpret dates relative to this value."
        )

        self._function_map = {
            "get_today_events": self.calendar_service.get_today_events,
            "get_events_by_date": self.calendar_service.get_events_by_date,
            "add_event": self.calendar_service.add_event,
            "delete_event": self.calendar_service.delete_event,
            "get_schedule_summary": self.calendar_service.get_schedule_summary,
        }

        # Register additional handlers
        self.message_handlers["availability_check"] = self._handle_availability_check

    async def _handle_availability_check(self, message: Message) -> None:
        """Respond with simple availability information for a given date."""
        date_str = message.content.get("date", self.calendar_service.current_date())
        events = await self.calendar_service.get_events_by_date(date_str)
        available = len(events.get("events", [])) == 0
        result = {
            "available": available,
            "date": date_str,
            "events": events.get("events", []),
        }
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    @property
    def description(self) -> str:
        return "Manages calendar, scheduling, and time-related operations"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "view_schedule",
            "add_event",
            "remove_event",
            "get_schedule_summary",
        }

    @property
    def dependencies(self) -> Set[str]:
        return {
            "send_notification",  # From email agent
            "get_contact_info",  # From contacts agent
            "get_weather",  # From weather agent for outdoor events
            "get_traffic",  # From maps agent for travel time
        }

    def _resolve_references(self, params: Any, context: Dict[str, Any]) -> Any:
        """Resolve `$` references using provided context via jmespath."""
        if isinstance(params, str) and params.startswith("$"):
            expr = params[1:]
            try:
                result = jmespath.search(expr, context)
                if isinstance(result, list) and len(result) == 1:
                    return result[0]
                return result
            except Exception:
                return None
        if isinstance(params, dict):
            return {k: self._resolve_references(v, context) for k, v in params.items()}
        if isinstance(params, list):
            return [self._resolve_references(v, context) for v in params]
        return params

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

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        context_data = message.content.get("context", {})
        if context_data:
            data = self._resolve_references(data, context_data)

        if capability not in self.capabilities:
            self.logger.log(
                "WARNING",
                "Unknown capability",
                f"{capability} for {self.name}",
            )
            return

        self.logger.log("INFO", f"Handling {capability}", json.dumps(data))

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

            if capability == "view_schedule":
                date = data.get("date", self.calendar_service.current_date())
                result = await self.calendar_service.get_events_by_date(date)

            elif capability == "add_event":
                # Normalize parameters allowing start_time/end_time as an alternative
                if ("date" not in data or "time" not in data) and (
                    data.get("start_time") and data.get("end_time")
                ):
                    try:
                        start_dt = datetime.fromisoformat(data["start_time"])
                        end_dt = datetime.fromisoformat(data["end_time"])
                        data["date"] = start_dt.strftime("%Y-%m-%d")
                        data["time"] = start_dt.strftime("%H:%M")
                        data["duration_minutes"] = int(
                            (end_dt - start_dt).total_seconds() // 60
                        )
                    except Exception:
                        await self.send_error(
                            message.from_agent,
                            "Invalid start_time or end_time format",
                            message.request_id,
                        )
                        return

                # Validate required fields
                required = ["title", "date", "time"]
                missing = [f for f in required if not data.get(f)]
                if missing:
                    await self.send_error(
                        message.from_agent,
                        f"Missing required fields for add_event: {', '.join(missing)}",
                        message.request_id,
                    )
                    return
                # Check for conflicts first
                conflicts = await self._check_conflicts(data)
                if conflicts:
                    # Request user confirmation through UI agent
                    await self.request_capability(
                        "user_confirmation",
                        {
                            "message": f"Event conflicts with: {conflicts}. Proceed?",
                            "options": ["yes", "no", "reschedule"],
                        },
                        message.request_id,
                    )
                    # Store for later processing
                    self.active_tasks[message.request_id]["pending_add"] = data
                    return

                result = await self.calendar_service.add_event(**data)

                # Notify other agents
                await self._notify_event_change("added", result)

            elif capability == "remove_event":
                event_id = data.get("event_id")
                if not event_id:
                    await self.send_error(
                        message.from_agent,
                        "Missing event_id for remove_event",
                        message.request_id,
                    )
                    return
                result = await self.calendar_service.delete_event(event_id)

            elif capability == "get_schedule_summary":
                date_range = data.get("date_range", "today")
                result = await self.calendar_service.get_schedule_summary(date_range)

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

        # Handle different types of responses
        if "pending_add" in task:
            # User confirmation response
            if message.content.get("confirmed"):
                # Add the event
                result = await self.calendar_service.add_event(**task["pending_add"])
                await self.send_capability_response(
                    task["original_requester"],
                    result,
                    request_id,
                    task["original_message_id"],
                )


    async def _notify_event_change(self, change_type: str, event_data: Dict) -> None:
        """Notify other agents about schedule changes"""
        await self.network.broadcast(
            self.name,
            "schedule_update",
            {
                "type": f"event_{change_type}",
                "event": event_data,
                "timestamp": datetime.now().isoformat(),
            },
            str(uuid.uuid4()),
        )

    async def _check_conflicts(self, event_data: Dict) -> List[str]:
        """Check for scheduling conflicts"""
        # Check for time conflicts
        date = event_data.get("date")
        time = event_data.get("time")
        duration = event_data.get("duration_minutes", 60)

        if (not date or not time) and event_data.get("start_time"):
            try:
                start_dt = datetime.fromisoformat(event_data["start_time"])
                end_dt = datetime.fromisoformat(event_data.get("end_time", event_data["start_time"]))
                date = start_dt.strftime("%Y-%m-%d")
                time = start_dt.strftime("%H:%M")
                duration = int((end_dt - start_dt).total_seconds() // 60)
            except Exception:
                return []

        if not date or not time:
            # Cannot check conflicts without a specific date and time
            return []

        existing = await self.calendar_service.get_events_by_date(date)
        conflicts = []

        # ... conflict checking logic ...

        return conflicts

