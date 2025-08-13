from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional

from ..agents.base import NetworkAgent
from ..logging import JarvisLogger


class NightAgent(NetworkAgent):
    """Base class for agents that run background tasks during night mode."""

    def __init__(self, name: str, logger: Optional[JarvisLogger] = None) -> None:
        super().__init__(name, logger)
        self._background_tasks: list[asyncio.Task] = []

    async def start_background_tasks(self) -> None:
        """Start background work. Override in subclass."""
        return None

    async def stop_background_tasks(self) -> None:
        """Stop all running background tasks."""
        if not self._background_tasks:
            return None

        # First signal all tasks to cancel
        for task in self._background_tasks:
            task.cancel()

        # Wait for the tasks to finish without propagating cancellation
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

    def _create_background_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)

    def activate_capabilities(self) -> None:
        """Expose this agent's capabilities on the network."""
        if self.network:
            self.network.add_agent_capabilities(self)

    def deactivate_capabilities(self) -> None:
        """Hide this agent's capabilities from the network."""
        if self.network:
            self.network.remove_agent_capabilities(self)
