from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...protocols import Protocol, ProtocolStep
from ...protocols.registry import ProtocolRegistry
from ...protocols.executor import ProtocolExecutor


class ProtocolAgent(NetworkAgent):
    """Agent that manages multi-step protocols."""

    STORAGE_PATH = "protocols.db"

    def __init__(self, logger: Optional[JarvisLogger] = None) -> None:
        super().__init__("ProtocolAgent", logger)
        self.registry = ProtocolRegistry(self.STORAGE_PATH)
        self.executor: Optional[ProtocolExecutor] = None

    def set_network(self, network) -> None:  # type: ignore[override]
        super().set_network(network)
        self.executor = ProtocolExecutor(network, self.logger)
        self._sync_registry()

    @property
    def description(self) -> str:
        return "Stores, describes, and executes named protocols"

    @property
    def capabilities(self) -> Set[str]:
        return {"define_protocol", "list_protocols", "describe_protocol", "run_protocol"}

    def _sync_registry(self) -> None:
        if self.network:
            self.network.protocol_registry = list(self.registry.list_ids())

    async def _handle_capability_request(self, message: Message) -> None:
        cap = message.content.get("capability")
        data = message.content.get("data", {}) or {}

        if cap == "define_protocol":
            await self._handle_define(message, data)
        elif cap == "list_protocols":
            await self._handle_list(message)
        elif cap == "describe_protocol":
            await self._handle_describe(message, data)
        elif cap == "run_protocol":
            await self._handle_run(message, data)

    async def _handle_define(self, message: Message, data: Dict[str, Any]) -> None:
        name = data.get("name")
        description = data.get("description", "")
        raw_steps = data.get("steps", [])
        if not name or not isinstance(raw_steps, list):
            await self.send_error(message.from_agent, "Invalid protocol definition", message.request_id)
            return

        steps = [ProtocolStep(intent=s.get("intent"), parameters=s.get("parameters", {})) for s in raw_steps]
        proto = Protocol(id=str(uuid.uuid4()), name=name, description=description, steps=steps)
        self.registry.register(proto)
        self._sync_registry()
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"status": "ok", "id": proto.id},
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_list(self, message: Message) -> None:
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"protocols": list(self.registry.list_ids())},
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_describe(self, message: Message, data: Dict[str, Any]) -> None:
        ident = data.get("protocol_name")
        proto = self.registry.get(ident)
        if not proto:
            await self.send_error(message.from_agent, f"Unknown protocol '{ident}'", message.request_id)
            return

        await self.send_capability_response(
            to_agent=message.from_agent,
            result={
                "id": proto.id,
                "name": proto.name,
                "description": proto.description,
                "steps": [step.__dict__ for step in proto.steps],
            },
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_run(self, message: Message, data: Dict[str, Any]) -> None:
        ident = data.get("protocol_name")
        args = data.get("args", {}) or {}
        proto = self.registry.get(ident)
        if not proto or not self.executor:
            await self.send_error(message.from_agent, f"Unknown protocol '{ident}'", message.request_id)
            return

        results = await self.executor.execute(proto, args)
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"protocol": proto.name, "results": results},
            request_id=message.request_id,
            original_message_id=message.id,
        )
