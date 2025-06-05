from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from ..logger import JarvisLogger
from .message import Message


class AgentNetwork:
    """Central message broker for agent communication."""

    def __init__(self, logger: Optional[JarvisLogger] = None) -> None:
        from .base_agent import NetworkAgent  # lazy import to avoid circular dep

        self.agents: Dict[str, NetworkAgent] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.capability_registry: Dict[str, List[str]] = {}
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.logger = logger or JarvisLogger()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

    def register_agent(self, agent: "NetworkAgent") -> None:
        self.agents[agent.name] = agent
        agent.set_network(self)

        for capability in agent.capabilities:
            self.capability_registry.setdefault(capability, []).append(agent.name)

        self.logger.log(
            "INFO",
            f"Agent registered: {agent.name}",
            f"Capabilities: {agent.capabilities}",
        )

    async def send_message(self, message: Message) -> None:
        await self.message_queue.put(message)

    async def broadcast(
        self, from_agent: str, message_type: str, content: Any, request_id: str
    ) -> None:
        message = Message(
            from_agent=from_agent,
            to_agent=None,
            message_type=message_type,
            content=content,
            request_id=request_id,
        )
        await self.send_message(message)

    async def request_capability(
        self, from_agent: str, capability: str, data: Any, request_id: str
    ) -> List[str]:
        providers = self.capability_registry.get(capability, [])
        if not providers:
            self.logger.log("WARNING", f"No providers for capability: {capability}")
            return []
        for provider in providers:
            message = Message(
                from_agent=from_agent,
                to_agent=provider,
                message_type="capability_request",
                content={"capability": capability, "data": data},
                request_id=request_id,
            )
            await self.send_message(message)
        return providers

    async def start(self) -> None:
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        self.logger.log("INFO", "Network started")

    async def stop(self) -> None:
        self._running = False
        if self._processor_task:
            await self._processor_task
        self.logger.log("INFO", "Network stopped")

    async def _process_messages(self) -> None:
        while self._running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=0.1)
                self.logger.log(
                    "DEBUG",
                    "Processing message",
                    f"{message.from_agent} -> {message.to_agent or 'ALL'}: {message.message_type}",
                )
                if message.to_agent:
                    if message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                else:
                    for agent_name, agent in self.agents.items():
                        if agent_name != message.from_agent:
                            asyncio.create_task(agent.receive_message(message))
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                self.logger.log("ERROR", "Message processing error", str(exc))

