# jarvis/agents/weather_agent/command_processor.py
import json
import asyncio
import functools
from typing import Dict, Any, List
from ...ai_clients.base import BaseAIClient
from ...logger import JarvisLogger
from .function_registry import WeatherFunctionRegistry
from .prompt import get_weather_enhanced_prompt
from .tools.tools import tools as weather_tools


class WeatherCommandProcessor:
    """Handles processing of natural language weather commands"""

    def __init__(
        self,
        ai_client: BaseAIClient,
        function_registry: WeatherFunctionRegistry,
        logger: JarvisLogger | None = None,
        default_location: str = "Chicago",
    ):
        self.ai_client = ai_client
        self.function_registry = function_registry
        self.logger = logger
        self.default_location = default_location
        self.tools = weather_tools

    async def execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a weather function with proper error handling"""
        func = self.function_registry.get_function(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}

        try:
            # Run synchronous functions in executor to avoid blocking
            call = functools.partial(func, **arguments)
            result = await asyncio.get_running_loop().run_in_executor(None, call)
            return {"result": result}
        except Exception as exc:
            error = {"error": str(exc), "function": function_name, "args": arguments}
            if self.logger:
                self.logger.log(
                    "ERROR", f"Error executing {function_name}", json.dumps(error)
                )
            return error

    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process natural language weather command using LLM and tools"""
        if self.logger:
            self.logger.log("INFO", "=== PROCESSING WEATHER COMMAND ===", command)

        # Enhanced system message with location context
        system_message = get_weather_enhanced_prompt(self.default_location)

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": command},
        ]

        actions_taken = []
        iterations = 0

        while iterations < 5:  # Limit iterations to prevent infinite loops
            if self.logger:
                self.logger.log("INFO", f"Weather command iteration {iterations + 1}")

            message, tool_calls = await self.ai_client.strong_chat(messages, self.tools)

            if self.logger:
                self.logger.log("INFO", f"AI response: {message.content}")
                self.logger.log(
                    "INFO", f"Tool calls: {len(tool_calls) if tool_calls else 0}"
                )

            if not tool_calls:
                if self.logger:
                    self.logger.log(
                        "INFO", "No more tool calls - conversation complete"
                    )
                break

            messages.append(message.model_dump())

            # Execute tool calls
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)

                if self.logger:
                    self.logger.log(
                        "INFO", f"Executing: {function_name}", json.dumps(arguments)
                    )

                result = await self.execute_function(function_name, arguments)

                if self.logger:
                    self.logger.log(
                        "DEBUG", f"Tool result: {function_name}", json.dumps(result)
                    )

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

        final_response = (
            message.content if hasattr(message, "content") else str(message)
        )

        if self.logger:
            self.logger.log("INFO", "=== WEATHER COMMAND COMPLETE ===")
            self.logger.log("INFO", f"Total actions: {len(actions_taken)}")

        return {
            "response": final_response,
            "actions": actions_taken,
            "iterations": iterations,
        }
