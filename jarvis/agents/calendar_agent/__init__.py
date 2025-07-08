# jarvis/agents/calendar_agent.py
from typing import Any, Dict, Set, List
import json
import uuid
from ..base import NetworkAgent
from ..message import Message
from ...services.calendar_service import CalendarService
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger
from datetime import datetime, timedelta, timezone
from .tools import tools as calendar_tools


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
        self.tools = calendar_tools
        # Get current local time as a formatted string
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.system_prompt = (
            "You are Jarvis, the AI assistant from Iron Man. "
            "Your user is Owen Stepan taking on the role of Tony Stark. "
            "Respond in a clear, conversational style without using asterisks or "
            "other non-textual formatting. You help manage the user's schedule by:\n"
            "1. Understanding natural language requests\n"
            "2. Breaking down complex tasks into calendar API calls\n"
            "3. Executing the necessary operations in the correct order\n"
            "4. Explaining the results plainly\n\n"
            f"Current date: {current_date}. Always interpret dates relative to this value.\n\n"
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
            "\n\n"
            "When the user gives a command, do not ask clarifying questions unless it is absolutely necessary to perform the action. "
            "If any required information is missing but can be inferred from context, do so intelligently and proceed with the task. "
            "Assume reasonable defaults when unsure (e.g., default recurring time is 09:15, default duration is 15 minutes, default category is 'General'). "
            "Only prompt the user if critical ambiguity prevents action. Prioritize completing the request smoothly and efficiently without back-and-forth. "
            "Favor decisive execution over cautious delays."
        )

        self.intent_map = {
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
            "schedule_appointment",  # covers generic adds
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
            # Use this to represent recurring creation
            "add_recurring_event",  # ✅ Direct tool that handles creation and recurrence
            "update_recurring_event",
            "delete_recurring_event",
            "get_recurring_events",
        }

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        func = self.intent_map.get(function_name)
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
            message, tool_calls = await self.ai_client.strong_chat(messages, self.tools)
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

        response_text = message.content
        self.logger.log("INFO", "NL command result", response_text)

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
            command = data.get("command")
            if not isinstance(command, str):
                await self.send_error(
                    message.from_agent, "Invalid command", message.request_id
                )
                return

            self.logger.log("INFO", "Processing command", command)
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
            self.logger.log(
                "WARNING",
                "Received capability response for unknown request_id",
                request_id,
            )
            return

        task = self.active_tasks[request_id]
        self.logger.log(
            "INFO",
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
