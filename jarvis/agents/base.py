from __future__ import annotations

import uuid
import asyncio
from functools import partial
from typing import Any, Callable, Dict, Optional, Set

from ..profile import AgentProfile
from ..services.vector_memory import VectorMemoryService

from .message import Message
from .agent_network import AgentNetwork
from ..logger import JarvisLogger


class NetworkAgent:
    """Base class for collaborative network agents."""

    def __init__(
        self,
        name: str,
        logger: Optional[JarvisLogger] = None,
        memory: Optional[VectorMemoryService] = None,
        profile: Optional[AgentProfile] = None,
    ) -> None:
        self._name = name
        self.network: Optional[AgentNetwork] = None
        self.logger = logger or JarvisLogger()
        self.active_tasks: Dict[str, Any] = {}
        self.message_handlers: Dict[str, Callable] = {}
        # Map intent names to bound methods for direct invocation
        self.intent_map: Dict[str, Callable] = {}
        self.memory = memory
        self.profile = profile or AgentProfile()
        self._setup_base_handlers()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Base network agent"

    @property
    def capabilities(self) -> Set[str]:
        """Override in subclass."""
        return set()

    def set_network(self, network: AgentNetwork) -> None:
        """Set the network this agent belongs to."""
        self.network = network

    def _setup_base_handlers(self) -> None:
        """Setup base message handlers."""
        self.message_handlers["capability_request"] = self._handle_capability_request
        self.message_handlers["capability_response"] = self._handle_capability_response
        self.message_handlers["error"] = self._handle_error

    async def receive_message(self, message: Message) -> None:
        """Handle an incoming message."""
        self.logger.log(
            "DEBUG",
            f"{self.name} received",
            f"{message.message_type} from {message.from_agent}",
        )
        handler = self.message_handlers.get(message.message_type, self._handle_unknown)
        try:
            await handler(message)
        except Exception as exc:
            self.logger.log("ERROR", f"{self.name} message handling error", str(exc))
            await self.send_error(message.from_agent, str(exc), message.request_id)

    async def _handle_unknown(self, message: Message) -> None:
        self.logger.log("DEBUG", f"{self.name} unknown message", message.message_type)

    async def _handle_capability_request(self, message: Message) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _handle_capability_request"
        )

    async def _handle_capability_response(self, message: Message) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _handle_capability_response"
        )

    async def _handle_error(self, message: Message) -> None:
        self.logger.log("ERROR", f"Error from {message.from_agent}", message.content)

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a capability using the agent's function map.

        Subclasses can override this to provide custom execution logic.
        """
        func = self.intent_map.get(capability)
        if not func:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not implement capability '{capability}'"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, **kwargs))

    async def send_message(
        self,
        to_agent: Optional[str],
        message_type: str,
        content: Any,
        request_id: str,
        reply_to: Optional[str] = None,
    ) -> None:
        message = Message(
            from_agent=self.name,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            request_id=request_id,
            reply_to=reply_to,
        )
        self.logger.log(
            "DEBUG",
            "Send message",
            f"{self.name} -> {to_agent or 'ALL'}: {message_type}",
        )
        await self.network.send_message(message)

    async def request_capability(
        self, capability: str, data: Any, request_id: Optional[str] = None
    ) -> str:
        if not request_id:
            request_id = str(uuid.uuid4())
        providers = await self.network.request_capability(
            self.name, capability, data, request_id
        )
        self.logger.log(
            "INFO",
            f"Request capability {capability}",
            f"providers={providers} data={data}",
        )
        if providers:
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
        self.logger.log(
            "DEBUG",
            "Send capability response",
            f"to {to_agent} req={request_id}",
        )
        await self.send_message(
            to_agent,
            "capability_response",
            result,
            request_id,
            reply_to=original_message_id,
        )

    async def send_error(self, to_agent: str, error: str, request_id: str) -> None:
        self.logger.log(
            "ERROR",
            f"Sending error to {to_agent}",
            error,
        )
        await self.send_message(to_agent, "error", {"error": error}, request_id)

    # ------------------------------------------------------------------
    # Shared tools
    # ------------------------------------------------------------------
    async def store_memory(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Add a piece of text to the shared vector memory via MemoryAgent."""
        if not self.network:
            return None
        req_id = await self.request_capability(
            "store_memory", {"text": text, "metadata": metadata}
        )
        result = await self.network.wait_for_response(req_id)
        if isinstance(result, str):
            return result
        if isinstance(result, dict) and "id" in result:
            return result["id"]
        return None

    async def search_memory(self, query: str, top_k: int = 3) -> list[Dict[str, Any]]:
        """Search the shared vector memory via MemoryAgent."""
        if not self.network:
            return []
        req_id = await self.request_capability(
            "search_memory", {"query": query, "top_k": top_k}
        )
        result = await self.network.wait_for_response(req_id)
        if isinstance(result, list):
            return result
        return []

    def update_profile(self, **fields: Any) -> None:
        """Update the agent's profile in-place."""
        if not self.profile:
            self.profile = AgentProfile()
        for key, value in fields.items():
            if hasattr(self.profile, key):
                setattr(self.profile, key, value)
