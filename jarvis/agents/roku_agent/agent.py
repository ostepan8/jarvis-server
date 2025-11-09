# jarvis/agents/roku_agent/agent.py
"""
Roku Agent - Controls Roku TV devices via External Control Protocol (ECP)
"""
from typing import Any, Dict, Set, Optional
import asyncio
import functools

from ..base import NetworkAgent
from ..message import Message
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient
from ...services.roku_service import RokuService
from .function_registry import RokuFunctionRegistry
from .command_processor import RokuCommandProcessor
from ..response import AgentResponse, ErrorInfo


class RokuAgent(NetworkAgent):
    """
    Conversational Roku control agent that uses LLM to translate natural language
    commands into Roku device control actions via the External Control Protocol.
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        device_ip: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        """
        Initialize the Roku agent.

        Args:
            ai_client: AI client for natural language processing
            device_ip: IP address of the Roku device
            username: Optional username for authentication
            password: Optional password for authentication
            logger: Optional logger instance
        """
        super().__init__("RokuAgent", logger)
        self.ai_client = ai_client
        self.device_ip = device_ip
        self.username = username
        self.password = password

        # Initialize components
        self.roku_service = RokuService(
            device_ip=device_ip,
            username=username,
            password=password,
        )
        self.function_registry = RokuFunctionRegistry(self.roku_service)
        self.command_processor = RokuCommandProcessor(
            ai_client=ai_client,
            function_registry=self.function_registry,
            logger=logger,
        )

    async def _process_roku_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language Roku command."""
        return await self.command_processor.process_command(command)

    async def close(self) -> None:
        """Clean up resources."""
        await self.roku_service.close()

    @property
    def description(self) -> str:
        return "Conversational Roku TV control agent with comprehensive device control capabilities"

    @property
    def capabilities(self) -> Set[str]:
        return self.function_registry.capabilities

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a Roku capability via the function registry."""
        func = self.function_registry.get_function(capability.replace("roku_", ""))
        if not func:
            raise NotImplementedError(
                f"Capability '{capability}' not implemented in RokuAgent"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, **kwargs))

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        if self.logger:
            self.logger.log("INFO", f"RokuAgent handling: {capability}")

        try:
            command = data.get("prompt", data.get("message", ""))
            if not command:
                await self.send_error(
                    message.from_agent,
                    "No Roku command provided",
                    message.request_id,
                )
                return

            result = await self._process_roku_command(command)

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as e:
            if self.logger:
                self.logger.log("ERROR", f"RokuAgent error: {e}")

            # Return standardized error response
            error_response = AgentResponse.error_response(
                response=f"I'm having trouble controlling the Roku device. {str(e)} Could you try again?",
                error=ErrorInfo.from_exception(e),
            ).to_dict()

            await self.send_capability_response(
                message.from_agent, error_response, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents."""
        if self.logger:
            self.logger.log("DEBUG", f"RokuAgent received response: {message.content}")
