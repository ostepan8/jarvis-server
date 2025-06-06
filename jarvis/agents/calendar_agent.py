# jarvis/agents/calendar_agent.py
from typing import Any, Dict, Set, List
import json
from datetime import datetime, timedelta
import uuid

from .base import NetworkAgent
from .message import Message
from ..services.calendar_service import CalendarService
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


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
            "analyze_schedule": self.calendar_service.analyze_schedule,
        }

        # Register additional handlers
        self.message_handlers["schedule_update"] = self._handle_schedule_update
        self.message_handlers["availability_check"] = self._handle_availability_check

    async def _handle_availability_check(self, message: Message) -> None:
        """Respond with simple availability information for a given date."""
        date_str = message.content.get(
            "date", self.calendar_service.current_date()
        )
        events = await self.calendar_service.get_events_by_date(date_str)
        available = len(events.get("events", [])) == 0
        result = {"available": available, "date": date_str, "events": events.get("events", [])}
        await self.send_capability_response(message.from_agent, result, message.request_id, message.id)

    @property
    def description(self) -> str:
        return "Manages calendar, scheduling, and time-related operations"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "view_schedule",
            "add_event",
            "remove_event",
            "modify_event",
            "find_free_time",
            "check_availability",
            "schedule_optimization",
            "calendar_command",
        }

    @property
    def dependencies(self) -> Set[str]:
        return {
            "send_notification",  # From email agent
            "get_contact_info",  # From contacts agent
            "get_weather",  # From weather agent for outdoor events
            "get_traffic",  # From maps agent for travel time
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

    async def _process_calendar_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language calendar command using AI."""
        current_date = self.calendar_service.current_date()
        messages = [
            {"role": "system", "content": self.system_prompt.format(current_date=current_date)},
            {"role": "user", "content": command},
        ]
        actions_taken: List[Dict[str, Any]] = []

        iterations = 0
        MAX_ITERATIONS = 5
        tool_calls = None
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
            message, _ = await self.ai_client.chat(messages, [])

        response_text = message.content if hasattr(message, "content") else str(message)

        return {"response": response_text, "actions": actions_taken}

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
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

            elif capability == "find_free_time":
                duration = data.get("duration_minutes", 60)
                date_str = data.get(
                    "date", self.calendar_service.current_date()
                )
                preferences = data.get("preferences", {})

                # Get schedule
                schedule = await self.calendar_service.get_events_by_date(date_str)

                # If looking for meeting with someone else
                if "attendees" in data:
                    # Request their availability
                    for attendee in data["attendees"]:
                        await self.request_capability(
                            "check_user_availability",
                            {"user": attendee, "date": date_str},
                            message.request_id,
                        )
                    self.active_tasks[message.request_id]["finding_mutual_time"] = True
                    return

                # Find free slots
                free_slots = self._calculate_free_slots(
                    schedule.get("events", []), duration, preferences
                )
                result = {"free_slots": free_slots, "date": date_str}

            elif capability == "schedule_optimization":
                # Complex operation that might need multiple agents
                date_range = data.get("date_range", "week")
                goals = data.get("goals", ["minimize_gaps", "respect_preferences"])

                # Get current schedule
                events = await self._get_events_for_range(date_range)

                # Check weather for outdoor events
                outdoor_events = [e for e in events if "outdoor" in e.get("tags", [])]
                if outdoor_events:
                    await self.request_capability(
                        "get_weather_forecast",
                        {"dates": [e["date"] for e in outdoor_events]},
                        message.request_id,
                    )
                    self.active_tasks[message.request_id]["optimizing"] = True
                    return

                # Optimize
                result = self._optimize_schedule(events, goals)

            elif capability == "calendar_command":
                command = data.get("command")
                if not isinstance(command, str):
                    await self.send_error(message.from_agent, "Invalid command", message.request_id)
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

        # Handle different types of responses
        if "finding_mutual_time" in task:
            task["responses"].append(message.content)

            # If we have all responses, calculate mutual free time
            if len(task["responses"]) == len(task["data"]["attendees"]):
                mutual_slots = self._find_mutual_availability(task["responses"])

                # Send final response
                await self.send_capability_response(
                    task["original_requester"],
                    {"mutual_free_slots": mutual_slots},
                    request_id,
                    task["original_message_id"],
                )

                del self.active_tasks[request_id]

        elif "pending_add" in task:
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

    async def _handle_schedule_update(self, message: Message) -> None:
        """Handle schedule update notifications from other agents"""
        update_type = message.content.get("type")

        if update_type == "travel_time_changed":
            # Adjust event times based on new travel time
            event_id = message.content.get("event_id")
            new_travel_time = message.content.get("travel_time_minutes")
            await self._adjust_event_for_travel(event_id, new_travel_time)

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

    def _calculate_free_slots(
        self, events: List[Dict], duration_minutes: int, preferences: Dict
    ) -> List[Dict]:
        """Calculate free time slots"""
        work_start = preferences.get("earliest", "09:00")
        work_end = preferences.get("latest", "17:00")

        # Implementation of free slot calculation
        free_slots = []

        # Sort events by time
        sorted_events = sorted(events, key=lambda x: x["time"])

        # ... calculation logic ...

        return free_slots

    def _find_mutual_availability(
        self, availability_responses: List[Dict]
    ) -> List[Dict]:
        """Find mutual free time from multiple availability responses"""
        # Find intersection of all free slots
        # ... implementation ...
        return []

    async def _check_conflicts(self, event_data: Dict) -> List[str]:
        """Check for scheduling conflicts"""
        # Check for time conflicts
        date = event_data.get("date")
        time = event_data.get("time")
        duration = event_data.get("duration_minutes", 60)

        if not date or not time:
            # Cannot check conflicts without a specific date and time
            return []

        existing = await self.calendar_service.get_events_by_date(date)
        conflicts = []

        # ... conflict checking logic ...

        return conflicts

    async def _get_events_for_range(self, date_range: str) -> List[Dict]:
        """Retrieve events for a given date range."""
        events: List[Dict] = []
        if date_range == "week":
            start = datetime.now()
            for i in range(7):
                day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
                day_events = await self.calendar_service.get_events_by_date(day)
                events.extend(day_events.get("events", []))
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            day_events = await self.calendar_service.get_events_by_date(today)
            events.extend(day_events.get("events", []))
        return events

    def _optimize_schedule(self, events: List[Dict], goals: List[str]) -> Dict[str, Any]:
        """Return a naive optimized schedule."""
        sorted_events = sorted(events, key=lambda e: e.get("time", ""))
        return {"optimized_events": sorted_events, "goals": goals}

    async def _adjust_event_for_travel(self, event_id: str, new_travel_time: int) -> None:
        """Placeholder for adjusting events based on travel time."""
        self.logger.log(
            "INFO",
            "Adjust travel time",
            f"{event_id} -> {new_travel_time}",
        )
