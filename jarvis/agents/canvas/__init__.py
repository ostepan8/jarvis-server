# jarvis/agents/canvas/canvas_agent.py
from typing import Any, Dict, List, Optional, Set
import json
from datetime import datetime, timezone

from ..base import NetworkAgent
from ..message import Message
from ...services.canvas_service import CanvasService
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger


class CanvasAgent(NetworkAgent):
    """Agent that interfaces with Canvas LMS to fetch courses, assignments, to-dos, calendar events, messages, and notifications."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        canvas_service: CanvasService,
        logger: Optional[JarvisLogger] = None,
    ):
        super().__init__("CanvasAgent", logger)
        self.ai_client = ai_client
        self.canvas_service = canvas_service

        # Define tools for the Canvas agent
        self.tools = [
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
                    "name": "get_current_courses",
                    "description": "Get only currently active/relevant courses",
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
                    "name": "get_todo",
                    "description": "Get to-do items (assignments, discussions, quizzes, calendar events)",
                    "parameters": {"type": "object", "properties": {}, "required": []},
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
        ]

        # A concise system prompt for Canvas interactions
        self.system_prompt = (
            "You are Jarvis, a helpful assistant for Canvas LMS. "
            "Your user is Owen Stepan. "
            "Use the provided tools to fetch courses, assignments, to-dos, calendar events, messages, and notifications. "
            "When a user asks about homework or assignments, provide detailed, actionable information including: "
            "1. Assignment names and course names "
            "2. Due dates (be specific about dates and times) "
            "3. Points possible "
            "4. Whether they've submitted or not "
            "5. How many days until due "
            "6. Brief description of what the assignment is about "
            "7. Prioritize by urgency (due soonest first) "
            "Be thorough and helpful - users need specific details to plan their work effectively. "
            "Focus on current/active courses only to avoid showing outdated information."
        )

        # Map each intent name to the corresponding CanvasService method
        self.intent_map: Dict[str, Any] = {
            "get_courses": self.canvas_service.get_courses,
            "get_current_courses": self.canvas_service.get_current_courses,
            "get_enrollments": self.canvas_service.get_enrollments,
            "get_course_assignments": self.canvas_service.get_course_assignments,
            "get_todo": self.canvas_service.get_todo,
            "get_calendar_events": self.canvas_service.get_calendar_events,
            "get_notifications": self.canvas_service.get_notifications,
            "get_messages": self.canvas_service.get_messages,
            "get_homework_summary": self.canvas_service.get_homework_summary,
            "get_comprehensive_homework": self.canvas_service.get_comprehensive_homework,
        }

        # Track ongoing requests so we can handle follow-up responses if needed
        self.active_tasks: Dict[str, Any] = {}

        self.logger.log("DEBUG", "Initialized CanvasAgent")

    @property
    def description(self) -> str:
        return "Fetches and manages Canvas LMS data: courses, assignments, to-dos, calendar events, messages, and notifications."

    @property
    def capabilities(self) -> Set[str]:
        return set(self.intent_map.keys())

    def _format_homework_response(self, result: Dict[str, Any]) -> str:
        """Format homework data into a user-friendly response."""
        if not result.get("success"):
            return f"Sorry, I couldn't retrieve your homework: {result.get('error', 'Unknown error')}"

        if "homework_summary" in result:
            # Handle get_homework_summary response
            homework_summary = result["homework_summary"]
            weekend_homework = homework_summary.get("weekend_homework", [])
            overdue_homework = homework_summary.get("overdue_homework", [])
            upcoming_homework = homework_summary.get("upcoming_homework", [])

            response_parts = []

            # Weekend homework
            if weekend_homework:
                response_parts.append("🗓️ **WEEKEND HOMEWORK:**")
                for hw in weekend_homework[:5]:  # Limit to 5 items
                    course_name = hw.get("course_name", "Unknown Course")
                    assignment_name = hw.get("assignment", {}).get(
                        "name", "Unknown Assignment"
                    )
                    due_date = hw.get("due_date", "Unknown date")
                    days_until = hw.get("days_until_due", "Unknown")

                    response_parts.append(f"• **{assignment_name}** - {course_name}")
                    response_parts.append(f"  Due: {due_date} ({days_until} days)")
                    response_parts.append("")

            # Overdue homework
            if overdue_homework:
                response_parts.append("⚠️ **OVERDUE ASSIGNMENTS:**")
                for hw in overdue_homework[:3]:  # Limit to 3 items
                    course_name = hw.get("course_name", "Unknown Course")
                    assignment_name = hw.get("assignment", {}).get(
                        "name", "Unknown Assignment"
                    )

                    response_parts.append(f"• **{assignment_name}** - {course_name}")
                response_parts.append("")

            # Summary
            total_weekend = len(weekend_homework)
            total_overdue = len(overdue_homework)
            total_upcoming = len(upcoming_homework)

            if total_weekend == 0 and total_overdue == 0 and total_upcoming == 0:
                response_parts.append(
                    "✅ **Great news!** You have no homework due this weekend and no overdue assignments."
                )
            else:
                response_parts.append("📊 **SUMMARY:**")
                response_parts.append(f"• {total_weekend} assignments due this weekend")
                response_parts.append(f"• {total_overdue} overdue assignments")
                response_parts.append(f"• {total_upcoming} upcoming assignments")

            return "\n".join(response_parts)

        elif "weekend_homework" in result:
            # Handle get_comprehensive_homework response
            weekend_homework = result.get("weekend_homework", [])
            due_soon = result.get("due_soon", [])

            response_parts = []

            if weekend_homework:
                response_parts.append("🗓️ **WEEKEND HOMEWORK:**")
                for hw in weekend_homework[:5]:
                    name = hw.get("name", "Unknown Assignment")
                    course_name = hw.get("course_name", "Unknown Course")
                    due_date = hw.get("due_date_formatted", "Unknown date")
                    points = hw.get("points_possible", 0)

                    response_parts.append(f"• **{name}** - {course_name}")
                    response_parts.append(f"  Due: {due_date} | Points: {points}")

                    if hw.get("brief_description"):
                        response_parts.append(f"  {hw['brief_description'][:100]}...")
                    response_parts.append("")

            if due_soon:
                response_parts.append("⏰ **DUE SOON:**")
                for hw in due_soon[:3]:
                    name = hw.get("name", "Unknown Assignment")
                    course_name = hw.get("course_name", "Unknown Course")
                    due_date = hw.get("due_date_formatted", "Unknown date")

                    response_parts.append(f"• **{name}** - {course_name}")
                    response_parts.append(f"  Due: {due_date}")
                    response_parts.append("")

            # Summary
            total_assignments = result.get("total_assignments", 0)
            weekend_count = result.get("weekend_homework_count", 0)
            due_soon_count = result.get("due_soon_count", 0)

            response_parts.append("📊 **SUMMARY:**")
            response_parts.append(f"• {total_assignments} total assignments")
            response_parts.append(f"• {weekend_count} due this weekend")
            response_parts.append(f"• {due_soon_count} due soon")

            return "\n".join(response_parts)

        return "I retrieved your homework information, but couldn't format it properly. Please try asking again."

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        func = self.intent_map.get(function_name)
        if not func:
            return {"success": False, "error": f"Unknown function: {function_name}"}

        try:
            self.logger.log("INFO", f"Calling {function_name}", json.dumps(arguments))
            result = await func(**arguments)

            # Log success/failure
            if isinstance(result, dict) and result.get("success") is not None:
                status = "SUCCESS" if result.get("success") else "FAILED"
                self.logger.log(
                    "INFO",
                    f"{status} {function_name}",
                    result.get("summary", result.get("message", "")),
                )
            else:
                self.logger.log("INFO", f"Result {function_name}", f"Returned data")

            return result
        except Exception as exc:
            error_result = {
                "success": False,
                "error": str(exc),
                "function": function_name,
                "arguments": arguments,
            }
            self.logger.log("ERROR", f"Error {function_name}", json.dumps(error_result))
            return error_result

    async def _process_canvas_command(self, command: str) -> Dict[str, Any]:
        """Drive the LLM → tool call loop for a single natural-language command."""
        self.logger.log("DEBUG", "Processing Canvas command", command)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": command},
        ]
        actions: List[Dict[str, Any]] = []
        iterations = 0
        MAX_ITERATIONS = 5
        message = None
        tool_calls = None

        while iterations < MAX_ITERATIONS:
            try:
                message, tool_calls = await self.ai_client.strong_chat(
                    messages, self.tools
                )
                self.logger.log("INFO", "LLM response", getattr(message, "content", ""))
            except Exception as e:
                if "context_length_exceeded" in str(
                    e
                ) or "maximum context length" in str(e):
                    self.logger.log("ERROR", "Context length exceeded", str(e))
                    return {
                        "success": False,
                        "error": "Request too large - please ask for more specific information",
                        "actions": actions,
                    }
                else:
                    self.logger.log("ERROR", "LLM call failed", str(e))
                    return {
                        "success": False,
                        "error": f"Error processing request: {str(e)}",
                        "actions": actions,
                    }

            if not tool_calls:
                break

            # Append the assistant message before executing its tool calls
            messages.append(message.model_dump())

            for call in tool_calls:
                fname = call.function.name
                args = json.loads(call.function.arguments)
                self.logger.log("INFO", f"Tool call: {fname}", json.dumps(args))

                result = await self._execute_function(fname, args)
                actions.append({"function": fname, "arguments": args, "result": result})

                # Feed the tool's result back into the LLM context
                # For Canvas results, provide a VERY concise summary to avoid token limits
                if isinstance(result, dict) and result.get("success"):
                    # Create a minimal summary for LLM context
                    if fname == "get_homework_summary":
                        summary = {
                            "success": True,
                            "action": "Retrieved homework summary",
                            "weekend_count": result.get("homework_summary", {}).get(
                                "weekend_count", 0
                            ),
                            "overdue_count": len(
                                result.get("homework_summary", {}).get(
                                    "overdue_homework", []
                                )
                            ),
                            "upcoming_count": len(
                                result.get("homework_summary", {}).get(
                                    "upcoming_homework", []
                                )
                            ),
                            "message": "Homework data retrieved successfully",
                        }
                    elif fname == "get_comprehensive_homework":
                        summary = {
                            "success": True,
                            "action": "Retrieved comprehensive homework",
                            "total_assignments": result.get("total_assignments", 0),
                            "due_soon_count": result.get("due_soon_count", 0),
                            "weekend_count": result.get("weekend_homework_count", 0),
                            "message": "Comprehensive homework data retrieved",
                        }
                    elif fname == "get_current_courses":
                        summary = {
                            "success": True,
                            "action": "Retrieved current courses",
                            "current_courses": result.get("current_courses", 0),
                            "total_courses": result.get("total_courses", 0),
                            "message": "Current courses retrieved successfully",
                        }
                    else:
                        # For other Canvas functions, provide minimal context
                        summary = {
                            "success": True,
                            "action": f"Executed {fname}",
                            "message": result.get(
                                "summary", "Data retrieved successfully"
                            ),
                        }

                    context_result = summary
                else:
                    context_result = {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                    }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(context_result),
                    }
                )

            iterations += 1

        response_text = message.content if message else "No response generated"
        return {"success": True, "response": response_text, "actions": actions}

    async def _handle_capability_request(self, message: Message) -> None:
        """Entry-point for other agents asking CanvasAgent to do work."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        # Track this request so we can attach follow-up responses if needed
        self.active_tasks.setdefault(
            message.request_id,
            {"data": data, "original_requester": message.from_agent, "responses": []},
        )

        try:
            prompt = data.get("prompt")
            if not isinstance(prompt, str):
                await self.send_error(
                    message.from_agent, "Invalid prompt", message.request_id
                )
                return

            result = await self._process_canvas_command(prompt)
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as e:
            await self.send_error(message.from_agent, str(e), message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        """Collect responses if we ever ask other agents to help."""
        request_id = message.request_id
        if request_id not in self.active_tasks:
            self.logger.log("WARNING", "Unknown response for request", request_id)
            return

        task = self.active_tasks[request_id]
        self.logger.log(
            "INFO", "Capability response received", json.dumps(message.content)
        )

        task["responses"].append(
            {
                "from_agent": message.from_agent,
                "content": message.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def receive_message(self, message: Message) -> None:
        """Handle incoming messages from the network."""
        if message.message_type == "capability_request":
            await self._handle_capability_request(message)
        elif message.message_type == "capability_response":
            await self._handle_capability_response(message)
        else:
            self.logger.log("WARNING", f"Unknown message type: {message.message_type}")

    async def send_capability_response(
        self, to_agent: str, content: Any, request_id: str, reply_to: str = None
    ) -> None:
        """Send a capability response back to the requesting agent."""
        if self.network:
            response = Message(
                from_agent=self.name,
                to_agent=to_agent,
                message_type="capability_response",
                content=content,
                request_id=request_id,
                reply_to=reply_to,
            )
            await self.network.send_message(response)

    async def send_error(self, to_agent: str, error: str, request_id: str) -> None:
        """Send an error response back to the requesting agent."""
        if self.network:
            response = Message(
                from_agent=self.name,
                to_agent=to_agent,
                message_type="error",
                content={"error": error},
                request_id=request_id,
            )
            await self.network.send_message(response)
