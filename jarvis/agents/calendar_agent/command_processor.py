# jarvis/agents/calendar_agent/command_processor.py
from typing import Dict, Any, List
import json
from ...ai_clients import BaseAIClient
from ...services.calendar_service import CalendarService
from ...logging import JarvisLogger
from .prompt import get_calendar_system_prompt
from .function_registry import CalendarFunctionRegistry


class CalendarCommandProcessor:
    """Handles processing of natural language calendar commands"""

    def __init__(
        self,
        ai_client: BaseAIClient,
        calendar_service: CalendarService,
        function_registry: CalendarFunctionRegistry,
        tools: List[Dict[str, Any]],
        logger: JarvisLogger | None = None,
    ):
        self.ai_client = ai_client
        self.calendar_service = calendar_service
        self.function_registry = function_registry
        self.tools = tools
        self.logger = logger
        self.system_prompt = get_calendar_system_prompt()

    def _safe_json_dumps(self, obj):
        """Safely serialize an object to JSON, handling non-serializable types"""
        try:
            return json.dumps(obj)
        except (TypeError, ValueError) as e:
            # Handle non-serializable objects
            if hasattr(obj, "__dict__"):
                return json.dumps(obj.__dict__)
            elif hasattr(obj, "__name__"):
                return f"<{obj.__class__.__name__}: {obj.__name__}>"
            else:
                return f"<{type(obj).__name__}: {str(obj)}>"

    async def execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a calendar function with the given arguments"""
        func = self.function_registry.get_function(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}

        try:
            if self.logger:
                self.logger.log(
                    "INFO", f"Calling {function_name}", self._safe_json_dumps(arguments)
                )

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
            if self.logger:
                self.logger.log(
                    "INFO", f"Result {function_name}", self._safe_json_dumps(result)
                )
            return result

        except Exception as exc:
            error = {
                "error": str(exc),
                "function": function_name,
                "arguments": arguments,
            }
            if self.logger:
                self.logger.log(
                    "ERROR", f"Error {function_name}", self._safe_json_dumps(error)
                )
            return error

    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language calendar command using AI"""
        if self.logger:
            self.logger.log("DEBUG", "Processing NL command", command)

        try:
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
            message = None

            while iterations < MAX_ITERATIONS:
                try:
                    message, tool_calls = await self.ai_client.weak_chat(
                        messages, self.tools
                    )
                    if self.logger:
                        self.logger.log(
                            "INFO",
                            "AI response",
                            getattr(message, "content", str(message)),
                        )

                    if not tool_calls:
                        break

                    # Convert message to dict safely
                    message_dict = (
                        message.model_dump()
                        if hasattr(message, "model_dump")
                        else str(message)
                    )
                    if isinstance(message_dict, str):
                        message_dict = {"role": "assistant", "content": message_dict}

                    messages.append(message_dict)

                    for call in tool_calls:
                        function_name = call.function.name
                        arguments = json.loads(call.function.arguments)
                        if self.logger:
                            self.logger.log("INFO", "Tool call", function_name)

                        result = await self.execute_function(function_name, arguments)
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

                except Exception as e:
                    if self.logger:
                        self.logger.log(
                            "ERROR",
                            f"Error in command processing iteration {iterations}",
                            str(e),
                        )
                    break

            if iterations >= MAX_ITERATIONS and self.logger:
                self.logger.log("ERROR", "Max iterations reached", str(iterations))

            response_text = (
                getattr(message, "content", "No response generated")
                if message
                else "No response generated"
            )
            if self.logger:
                self.logger.log("INFO", "NL command result", response_text)

            return {"response": response_text, "actions": actions_taken}

        except Exception as e:
            error_msg = f"Error processing command: {str(e)}"
            if self.logger:
                self.logger.log("ERROR", "Command processing failed", error_msg)
            return {"error": error_msg}
