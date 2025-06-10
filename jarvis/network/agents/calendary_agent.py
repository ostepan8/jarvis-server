# jarvis/network/agents/calendar_agent.py
from typing import Any, Dict, Set, List
import json
from datetime import datetime, timedelta, timezone
import uuid

from ..core import NetworkAgent, Message
from ...calendar_service import CalendarService
from ...logger import JarvisLogger


class CollaborativeCalendarAgent(NetworkAgent):
    """Calendar agent that collaborates with other agents"""

    def __init__(
        self, calendar_service: CalendarService, logger: JarvisLogger | None = None
    ):
        super().__init__("CalendarAgent", logger)
        self.calendar_service = calendar_service

        # Register additional handlers
        self.message_handlers["schedule_update"] = self._handle_scrhedule_update
        self.message_handlers["availability_check"] = self._handle_availability_check

    async def _handle_availability_check(self, message: Message) -> None:
        """Respond with simple availability information for a given date."""
        date_str = message.content.get(
            "date", self.calendar_service.current_date_utc()
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
        }

    @property
    def dependencies(self) -> Set[str]:
        return {
            "send_notification",  # From email agent
            "get_contact_info",  # From contacts agent
            "get_weather",  # From weather agent for outdoor events
            "get_traffic",  # From maps agent for travel time
        }

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"Handling {capability}", json.dumps(data))

        try:
            result = None

            if capability == "view_schedule":
                date = data.get("date", self.calendar_service.current_date_utc())
                result = await self.calendar_service.get_events_by_date(date)

            elif capability == "add_event":
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
                    "date", self.calendar_service.current_date_utc()
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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

        existing = await self.calendar_service.get_events_by_date(date)
        conflicts = []

        # ... conflict checking logic ...

        return conflicts

    async def _get_events_for_range(self, date_range: str) -> List[Dict]:
        """Retrieve events for a given date range."""
        events: List[Dict] = []
        if date_range == "week":
            start = datetime.now(timezone.utc)
            for i in range(7):
                day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
                day_events = await self.calendar_service.get_events_by_date(day)
                events.extend(day_events.get("events", []))
        else:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
