# jarvis/agents/roku_agent/command_processor.py
"""
Command processor for Roku agent - handles AI-driven command processing
"""
from typing import Dict, Any, Optional
import json
import asyncio

from ...ai_clients.base import BaseAIClient
from ...logging import JarvisLogger
from .function_registry import RokuFunctionRegistry
from .tools.tools import tools
from ..response import AgentResponse, ErrorInfo


class RokuCommandProcessor:
    """Processes natural language commands using AI and executes Roku functions."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        function_registry: RokuFunctionRegistry,
        logger: Optional[JarvisLogger] = None,
    ):
        self.ai_client = ai_client
        self.function_registry = function_registry
        self.logger = logger
        self.tools = tools
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the AI."""
        return """
You are JARVIS, an advanced AI assistant for controlling Roku TV devices. You have comprehensive control over Roku devices including:

DEVICE INFORMATION:
- Query device details, model, software version
- Check currently active app/channel
- List all installed apps and channels
- Get media player state and playback information

APP/CHANNEL CONTROL:
- Launch any installed app or channel by name
- Popular apps: Netflix, Hulu, YouTube, Disney+, Prime Video, HBO Max, etc.

PLAYBACK CONTROL:
- Play/pause media
- Fast forward and rewind
- Jump back with instant replay

NAVIGATION:
- Navigate menus using directional controls (up, down, left, right)
- Select items
- Go back to previous screens
- Return to home screen

VOLUME AND POWER:
- Adjust volume up/down
- Mute/unmute audio
- Power on/off the device

INPUT SWITCHING:
- Switch between HDMI inputs and tuner
- Control input sources for Roku TVs

SEARCH:
- Search for content across all installed channels

CONVERSATION STYLE:
- Be natural and conversational, not robotic
- Provide helpful confirmations after actions
- Anticipate user needs (e.g., if they say "watch Netflix", launch the app)
- Handle casual language (e.g., "turn it up" means volume up)
- Be proactive about suggesting related actions

COMMAND INTERPRETATION:
- "turn on/off" → power on/off
- "open/launch/start [app]" → launch_app_by_name
- "go home" → home
- "turn it up/louder" → volume_up
- "turn it down/quieter" → volume_down
- "mute" → volume_mute
- "play/pause/stop" → play/pause
- "go back" → back
- "what's playing" → get_active_app and get_player_info
- "switch to HDMI [1-4]" → switch_input

BEST PRACTICES:
1. Confirm actions with natural language
2. Provide context about what's happening
3. If an app name is ambiguous, list available apps and ask for clarification
4. For repeated actions (like volume), use the count parameter efficiently
5. Handle errors gracefully and suggest alternatives

Given a user's command, use the appropriate tools to accomplish their goal and respond in a natural, helpful way.
        """.strip()

    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language command using AI and tool calls."""
        if self.logger:
            self.logger.log("INFO", "=== PROCESSING ROKU COMMAND ===", command)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": command},
        ]

        actions_taken = []
        iterations = 0
        max_iterations = 5

        while iterations < max_iterations:
            if self.logger:
                self.logger.log("INFO", f"Roku command iteration {iterations + 1}")

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

                result = await self._execute_function(function_name, arguments)

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
            self.logger.log("INFO", "=== ROKU COMMAND COMPLETE ===")
            self.logger.log("INFO", f"Total actions: {len(actions_taken)}")

        # Check if any actions resulted in errors
        # Only treat as error if "error" key exists AND has a truthy value
        # (True or non-empty string, but not False)
        has_errors = any(
            result.get("error") is True
            or (isinstance(result.get("error"), str) and result.get("error"))
            for action in actions_taken
            for result in [action.get("result", {})]
        )

        if has_errors:
            # Extract the first error for error info
            error_action = next(
                (
                    action
                    for action in actions_taken
                    if (
                        action.get("result", {}).get("error") is True
                        or (
                            isinstance(action.get("result", {}).get("error"), str)
                            and action.get("result", {}).get("error")
                        )
                    )
                ),
                None,
            )
            error_msg = (
                error_action["result"]["error"] if error_action else "Unknown error"
            )
            # If error is True (boolean), convert to a message
            if error_msg is True:
                error_msg = "An error occurred during execution"

            # Return error response
            return AgentResponse.error_response(
                response=final_response,
                error=ErrorInfo(
                    message=error_msg,
                    error_type="FunctionExecutionError",
                ),
                actions=actions_taken,
            ).to_dict()

        # Return standardized success response
        return AgentResponse.success_response(
            response=final_response,
            actions=actions_taken,
            metadata={"iterations": iterations},
        ).to_dict()

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Roku function with proper error handling."""
        func = self.function_registry.get_function(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}

        try:
            # All service methods are async
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                # Shouldn't happen, but handle it just in case
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, func, **arguments)

            return {"result": result} if not isinstance(result, dict) else result
        except Exception as exc:
            error = {"error": str(exc), "function": function_name, "args": arguments}
            if self.logger:
                self.logger.log(
                    "ERROR", f"Error executing {function_name}", json.dumps(error)
                )
            return error
