# jarvis/network/core.py
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from ..logger import JarvisLogger


@dataclass
class Message:
    """Message passed between agents"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str = ""
    to_agent: Optional[str] = None  # None = broadcast
    message_type: str = ""
    content: Any = None
    request_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to: Optional[str] = None  # For response tracking


@dataclass
class Capability:
    """Defines a capability that an agent provides"""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


class AgentNetwork:
    """Central message broker for agent communication"""

    def __init__(self, logger: Optional[JarvisLogger] = None):
        self.agents: Dict[str, NetworkAgent] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.capability_registry: Dict[str, List[str]] = (
            {}
        )  # capability -> [agent_names]
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.logger = logger or JarvisLogger()
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None

    def register_agent(self, agent: NetworkAgent) -> None:
        """Register an agent with the network"""
        self.agents[agent.name] = agent
        agent.set_network(self)

        # Register agent's capabilities
        for capability in agent.capabilities:
            if capability not in self.capability_registry:
                self.capability_registry[capability] = []
            self.capability_registry[capability].append(agent.name)

        self.logger.log(
            "INFO",
            f"Agent registered: {agent.name}",
            f"Capabilities: {agent.capabilities}",
        )

    async def send_message(self, message: Message) -> None:
        """Send a message through the network"""
        await self.message_queue.put(message)

    async def broadcast(
        self, from_agent: str, message_type: str, content: Any, request_id: str
    ) -> None:
        """Broadcast a message to all agents"""
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
        """Request a capability and return list of agents that can provide it"""
        providers = self.capability_registry.get(capability, [])

        if not providers:
            self.logger.log("WARNING", f"No providers for capability: {capability}")
            return []

        # Send to all providers
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
        """Start the message broker"""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_messages())
        self.logger.log("INFO", "Network started")

    async def stop(self) -> None:
        """Stop the message broker"""
        self._running = False
        if self._processor_task:
            await self._processor_task
        self.logger.log("INFO", "Network stopped")

    async def _process_messages(self) -> None:
        """Process messages in the queue"""
        while self._running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=0.1)

                self.logger.log(
                    "DEBUG",
                    "Processing message",
                    f"{message.from_agent} -> {message.to_agent or 'ALL'}: "
                    f"{message.message_type}",
                )

                if message.to_agent:
                    # Direct message
                    if message.to_agent in self.agents:
                        asyncio.create_task(
                            self.agents[message.to_agent].receive_message(message)
                        )
                else:
                    # Broadcast
                    tasks = []
                    for agent_name, agent in self.agents.items():
                        if agent_name != message.from_agent:
                            tasks.append(
                                asyncio.create_task(agent.receive_message(message))
                            )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.log("ERROR", "Message processing error", str(e))


class NetworkAgent:
    """Base class for collaborative network agents"""

    def __init__(self, name: str, logger: Optional[JarvisLogger] = None):
        self._name = name
        self.network: Optional[AgentNetwork] = None
        self.logger = logger or JarvisLogger()
        self.active_tasks: Dict[str, Any] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self._setup_base_handlers()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Base network agent"

    @property
    def capabilities(self) -> Set[str]:
        """Override in subclass"""
        return set()

    @property
    def dependencies(self) -> Set[str]:
        """Override in subclass"""
        return set()

    def set_network(self, network: AgentNetwork) -> None:
        """Set the network this agent belongs to"""
        self.network = network

    def _setup_base_handlers(self) -> None:
        """Setup base message handlers"""
        self.message_handlers["capability_request"] = self._handle_capability_request
        self.message_handlers["capability_response"] = self._handle_capability_response
        self.message_handlers["error"] = self._handle_error

    async def receive_message(self, message: Message) -> None:
        """Handle incoming message"""
        handler = self.message_handlers.get(message.message_type, self._handle_unknown)

        try:
            await handler(message)
        except Exception as e:
            self.logger.log("ERROR", f"{self.name} message handling error", str(e))
            # Send error back
            await self.send_error(message.from_agent, str(e), message.request_id)

    async def _handle_unknown(self, message: Message) -> None:
        """Default handler for unknown message types"""
        self.logger.log("DEBUG", f"{self.name} unknown message", message.message_type)

    async def _handle_capability_request(self, message: Message) -> None:
        """Override in subclass to handle capability requests"""
        pass

    async def _handle_capability_response(self, message: Message) -> None:
        """Override in subclass to handle capability responses"""
        pass

    async def _handle_error(self, message: Message) -> None:
        """Handle error messages"""
        self.logger.log("ERROR", f"Error from {message.from_agent}", message.content)

    async def send_message(
        self,
        to_agent: Optional[str],
        message_type: str,
        content: Any,
        request_id: str,
        reply_to: Optional[str] = None,
    ) -> None:
        """Send a message to another agent or broadcast"""
        message = Message(
            from_agent=self.name,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            request_id=request_id,
            reply_to=reply_to,
        )
        await self.network.send_message(message)

    async def request_capability(
        self, capability: str, data: Any, request_id: Optional[str] = None
    ) -> str:
        """Request a capability from the network"""
        if not request_id:
            request_id = str(uuid.uuid4())

        providers = await self.network.request_capability(
            self.name, capability, data, request_id
        )

        if providers:
            # Store task info for tracking responses
            self.active_tasks[request_id] = {
                "capability": capability,
                "providers": providers,
                "responses": [],
                "data": data,
            }

        return request_id

    async def send_capability_response(
        self, to_agent: str, result: Any, request_id: str, original_message_id: str
    ) -> None:
        """Send capability response to requesting agent"""
        await self.send_message(
            to_agent,
            "capability_response",
            result,
            request_id,
            reply_to=original_message_id,
        )

    async def send_error(self, to_agent: str, error: str, request_id: str) -> None:
        """Send error message to another agent"""
        await self.send_message(to_agent, "error", {"error": error}, request_id)
