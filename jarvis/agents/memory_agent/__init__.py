from __future__ import annotations

from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.vector_memory import VectorMemoryService
from ...logger import JarvisLogger


class MemoryAgent(NetworkAgent):
    """Agent providing shared vector memory services."""

    def __init__(
        self,
        memory_service: VectorMemoryService,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__("MemoryAgent", logger, memory=memory_service)
        self.vector_memory = memory_service

    @property
    def description(self) -> str:
        return "Stores and retrieves memories for other agents"

    @property
    def capabilities(self) -> Set[str]:
        return {"store_memory", "search_memory"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability == "store_memory":
            command = data.get("command")
            metadata = data.get("metadata")
            if not command:
                await self.send_error(
                    message.from_agent, "No command provided", message.request_id
                )
                return
            try:
                mem_id = await self.vector_memory.add_memory(command, metadata)
                await self.send_capability_response(
                    message.from_agent, mem_id, message.request_id, message.id
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)
        elif capability == "search_memory":
            print(data, "DATA IN MEMORY AGENT")
            command = data.get("command")
            top_k = data.get("top_k", 3)
            if not command:
                await self.send_error(
                    message.from_agent,
                    "No command provided",
                    message.request_id,
                )
                return
            try:
                results = await self.vector_memory.similarity_search(
                    command, top_k=top_k
                )
                await self.send_capability_response(
                    message.from_agent, results, message.request_id, message.id
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        # MemoryAgent does not currently send capability requests
        pass
