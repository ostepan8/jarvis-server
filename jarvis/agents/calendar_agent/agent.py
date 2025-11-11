# jarvis/agents/calendar_agent/agent.py
from typing import Any, Dict, Set
import json
import asyncio
import functools
from datetime import datetime, timezone
from ..base import NetworkAgent
from ..message import Message
from ...services.calendar_service import CalendarService
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger
from .function_registry import CalendarFunctionRegistry
from .command_processor import CalendarCommandProcessor
# Import the tools list explicitly from the tools module. Using
# `from .tools import tools` would import the submodule instead of the
# variable due to Python's import resolution order.
from .tools.tools import tools as calendar_tools


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

        # Initialize components
        self.tools = calendar_tools
        self.function_registry = CalendarFunctionRegistry(calendar_service)
        self.command_processor = CalendarCommandProcessor(
            ai_client=ai_client,
            calendar_service=calendar_service,
            function_registry=self.function_registry,
            tools=self.tools,
            logger=logger,
        )

    @property
    def description(self) -> str:
        return "Manages calendar, scheduling, and time-related operations with full CRUD capabilities"

    @property
    def capabilities(self) -> Set[str]:
        return self.function_registry.capabilities

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a calendar capability via the function registry."""
        func = self.function_registry.get_function(capability)
        if not func:
            raise NotImplementedError(
                f"Capability '{capability}' not implemented in CalendarAgent"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, **kwargs))

    def _safe_json_dumps(self, obj):
        """Safely serialize an object to JSON, handling non-serializable types"""
        try:
            return json.dumps(obj)
        except (TypeError, ValueError) as e:
            # Handle non-serializable objects
            if hasattr(obj, "__dict__"):
                try:
                    return json.dumps(obj.__dict__)
                except:
                    return str(obj)
            elif hasattr(obj, "__name__"):
                return f"<{obj.__class__.__name__}: {obj.__name__}>"
            else:
                return f"<{type(obj).__name__}: {str(obj)}>"

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        if self.logger:
            self.logger.log(
                "INFO", f"Handling {capability}", self._safe_json_dumps(data)
            )

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
            prompt = data.get("prompt")
            if not isinstance(prompt, str):
                await self.send_error(
                    message.from_agent, "Invalid prompt", message.request_id
                )
                return

            # Extract context and enhance prompt with previous results from DAG
            context_info = self._extract_context_from_message(message)
            previous_results = context_info.get("previous_results", [])
            
            if previous_results:
                enhanced_prompt = self._enhance_prompt_with_context(
                    prompt, previous_results
                )
                if self.logger:
                    self.logger.log(
                        "INFO",
                        "Enhanced prompt with previous results",
                        f"Original: {prompt[:50]}... | Previous steps: {len(previous_results)}",
                    )
                prompt = enhanced_prompt
            else:
                if self.logger:
                    self.logger.log("INFO", "Processing prompt", prompt)

            result = await self.command_processor.process_command(prompt)

            if result:
                await self.send_capability_response(
                    message.from_agent, result, message.request_id, message.id
                )

        except Exception as e:
            error_msg = str(e)
            if self.logger:
                self.logger.log("ERROR", f"Error processing command", error_msg)
            await self.send_error(message.from_agent, error_msg, message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents"""
        request_id = message.request_id

        if request_id not in self.active_tasks:
            if self.logger:
                self.logger.log(
                    "WARNING",
                    "Received capability response for unknown request_id",
                    request_id,
                )
            return

        task = self.active_tasks[request_id]
        if self.logger:
            self.logger.log(
                "INFO",
                "Capability response received",
                self._safe_json_dumps(
                    {"request_id": request_id, "data": message.content}
                ),
            )

        # Store the response for potential aggregation
        task["responses"].append(
            {
                "from_agent": message.from_agent,
                "content": message.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def send_error(self, to_agent: str, error: str, request_id: str) -> None:
        """Override base send_error to handle serialization issues"""
        try:
            # Convert error to string to avoid serialization issues
            safe_error_msg = str(error)
            if self.logger:
                self.logger.log("ERROR", f"Sending error to {to_agent}", safe_error_msg)

            # Create a simple error response
            error_content = {"error": safe_error_msg}

            # Send the error message
            await self.send_message(to_agent, "error", error_content, request_id)

        except Exception as e:
            # If we can't send the error, just log it
            if self.logger:
                self.logger.log("ERROR", f"Failed to send error to {to_agent}", str(e))

    async def _safe_send_error(
        self, to_agent: str, error_msg: str, request_id: str
    ) -> None:
        """Safely send an error message without risking serialization issues"""
        try:
            # Convert error message to string to avoid serialization issues
            safe_error_msg = str(error_msg)
            if self.logger:
                self.logger.log("ERROR", f"Sending error to {to_agent}", safe_error_msg)

            # Create a simple error response
            error_response = {
                "error": safe_error_msg,
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Send the error response
            await self.send_capability_response(
                to_agent, error_response, request_id, None
            )

        except Exception as e:
            # If we can't send the error, just log it
            if self.logger:
                self.logger.log("ERROR", f"Failed to send error to {to_agent}", str(e))

    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all active tasks for debugging/monitoring"""
        return self.active_tasks.copy()
