# agents/agent_network.py

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..logger import JarvisLogger
from .message import Message

if TYPE_CHECKING:
    from .base import NetworkAgent  # for type hints only


class AgentNetwork:
    """Central message broker for agent communication."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        queue_maxsize: int = 1000,
    ) -> None:
        self.agents: Dict[str, NetworkAgent] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self.capability_registry: Dict[str, List[str]] = {}
        self.logger = logger or JarvisLogger()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

        # For tracking in-flight request futures
        self._response_futures: Dict[str, asyncio.Future] = {}

        # Reusable JARVIS protocols registry
        self.protocol_registry: List[str] = []

    def register_agent(self, agent: NetworkAgent) -> None:
        """Register an agent, its capabilities, and let it join the network."""
        self.agents[agent.name] = agent
        agent.set_network(self)

        for capability in agent.capabilities:
            self.capability_registry.setdefault(capability, []).append(agent.name)

        self.logger.log(
            "INFO",
            f"Agent registered: {agent.name}",
            f"Capabilities: {agent.capabilities}",
        )

        # If this agent has a 'protocols' attribute, register them
        if hasattr(agent, "protocols"):
            self.protocol_registry = list(getattr(agent, "protocols").keys())

    async def send_message(self, message: Message) -> None:
        """Enqueue a message for delivery."""
        await self.message_queue.put(message)

    async def start(self) -> None:
        """Start the message processing loop."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        self.logger.log("INFO", "Network started")

    async def stop(self) -> None:
        """Stop the message loop and wait for it to finish."""
        self._running = False
        if self._processor_task:
            await self._processor_task
        self.logger.log("INFO", "Network stopped")

    async def _process_messages(self) -> None:
        """Internal loop: dispatch messages, broadcast requests, fulfill responses."""
        while self._running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=0.1)
                self.logger.log(
                    "DEBUG",
                    "Processing message",
                    f"{message.from_agent} -> {message.to_agent or 'ALL'}: {message.message_type}",
                )

                # 1) If it's a response to a capability_request, fulfill the Future
                if message.message_type == "capability_response":
                    fut = self._response_futures.get(message.request_id)
                    if fut and not fut.done():
                        fut.set_result(message.content)
                    if message.to_agent and message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                    continue

                # 2) If it's an error reply, treat it as a response too
                if message.message_type == "error":
                    fut = self._response_futures.get(message.request_id)
                    if fut and not fut.done():
                        # you can choose to set_exception instead
                        fut.set_result({"error": message.content.get("error")})
                    if message.to_agent and message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                    continue

                # 3) Direct message: deliver to the specified agent
                if message.to_agent:
                    if message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                    continue

                # 4) Broadcast capability_request to all providers
                if message.message_type == "capability_request":
                    capability = message.content.get("capability")
                    providers = self.capability_registry.get(capability, [])
                    for provider in providers:
                        cloned = Message(
                            from_agent=message.from_agent,
                            to_agent=provider,
                            message_type=message.message_type,
                            content=message.content,
                            request_id=message.request_id,
                            reply_to=message.reply_to,
                        )
                        asyncio.create_task(
                            self.agents[provider].receive_message(cloned)
                        )
                    continue

            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                self.logger.log("ERROR", "Message processing error", str(exc))

    async def request_capability(
        self,
        from_agent: str,
        capability: str,
        data: Any,
        request_id: Optional[str] = None,
    ) -> List[str]:
        """
        Broadcast a capability_request and return the list of providers.
        Also registers a Future for the response.
        """
        if request_id is None:
            request_id = str(asyncio.get_event_loop().time())

        self.logger.log(
            "DEBUG",
            f"Capability request initiated",
            f"From: {from_agent}, Capability: {capability}, Request ID: {request_id}",
        )

        # Create and store the Future
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._response_futures[request_id] = fut

        # Broadcast the capability_request
        msg = Message(
            from_agent=from_agent,
            to_agent=None,
            message_type="capability_request",
            content={"capability": capability, "data": data},
            request_id=request_id,
        )
        await self.send_message(msg)

        # Get providers and log them
        providers = self.capability_registry.get(capability, [])
        self.logger.log(
            "INFO",
            f"Capability request broadcast",
            f"Capability: {capability}, Potential providers: {len(providers)}",
        )

        if not providers:
            self.logger.log(
                "WARNING",
                f"No providers found for capability",
                f"Capability: {capability}",
            )

        # Return who *could* handle it
        return providers

    async def wait_for_response(self, request_id: str, timeout: float = None) -> Any:
        """
        Await and return the result for a previously requested capability_response.
        """
        fut = self._response_futures.get(request_id)
        if not fut:
            raise KeyError(f"No pending request with id {request_id}")
        result = await asyncio.wait_for(fut, timeout)
        # Clean up
        del self._response_futures[request_id]
        return result
