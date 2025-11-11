# jarvis/agents/weather_agent/weather_agent.py
from typing import Any, Dict, Set, Optional
import asyncio
import functools

from ..base import NetworkAgent
from ..message import Message
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient
from ...services.weather_service import WeatherService
from .function_registry import WeatherFunctionRegistry
from .command_processor import WeatherCommandProcessor
from .tools.tools import tools as weather_tools
from ..response import AgentResponse, ErrorInfo


class WeatherAgent(NetworkAgent):
    """
    Conversational weather agent that uses LLM to translate natural language
    weather requests into specific tool calls for comprehensive weather information.
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        api_key: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
        default_location: str = "Chicago",
    ) -> None:
        super().__init__("WeatherAgent", logger)
        self.ai_client = ai_client
        self.default_location = default_location

        # Initialize components
        self.weather_service = WeatherService(api_key)
        self.function_registry = WeatherFunctionRegistry(self.weather_service)
        self.command_processor = WeatherCommandProcessor(
            ai_client=ai_client,
            function_registry=self.function_registry,
            logger=logger,
            default_location=default_location,
        )

    @property
    def client(self):
        """Expose underlying HTTP client for compatibility with tests."""
        return self.weather_service.client

    def _get_current_weather(self, location: str) -> Dict[str, Any]:
        """Proxy for WeatherService.get_current_weather used in tests."""
        return self.weather_service.get_current_weather(location)

    async def _process_weather_command(self, command: str) -> Dict[str, Any]:
        """Proxy for WeatherCommandProcessor.process_command used in tests."""
        return await self.command_processor.process_command(command)

    async def close(self) -> None:
        """Clean up resources"""
        await self.weather_service.close()

    @property
    def description(self) -> str:
        return "Conversational weather agent providing comprehensive weather information and practical advice"

    @property
    def capabilities(self) -> Set[str]:
        return self.function_registry.capabilities

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a weather capability via the function registry."""
        func = self.function_registry.get_function(capability)
        if not func:
            raise NotImplementedError(
                f"Capability '{capability}' not implemented in WeatherAgent"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, **kwargs))

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests"""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        if self.logger:
            self.logger.log("INFO", f"WeatherAgent handling: {capability}")

        try:
            command = data.get("prompt", data.get("message", ""))
            if not command:
                await self.send_error(
                    message.from_agent,
                    "No weather prompt provided",
                    message.request_id,
                )
                return

            # Extract context and enhance prompt with previous results from DAG
            context_info = self._extract_context_from_message(message)
            previous_results = context_info.get("previous_results", [])

            if previous_results:
                command = self._enhance_prompt_with_context(command, previous_results)
                if self.logger:
                    self.logger.log(
                        "INFO",
                        "Enhanced weather command with previous results",
                        f"Previous steps: {len(previous_results)}",
                    )

            result = await self._process_weather_command(command)

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as e:
            if self.logger:
                self.logger.log("ERROR", f"WeatherAgent error: {e}")

            # Return standardized error response
            error_response = AgentResponse.error_response(
                response=f"I'm having trouble with weather information right now. {str(e)} Could you try again?",
                error=ErrorInfo.from_exception(e),
            ).to_dict()

            await self.send_capability_response(
                message.from_agent, error_response, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents"""
        if self.logger:
            self.logger.log(
                "DEBUG", f"WeatherAgent received response: {message.content}"
            )
