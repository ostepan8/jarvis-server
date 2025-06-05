from __future__ import annotations

from typing import Any, Dict

from ...agent import AICalendarAgent


class CollaborativeCalendarAgent(AICalendarAgent):
    """Calendar agent adapted for use within an AgentNetwork."""

    async def collaborate(self, command: str) -> Dict[str, Any]:
        """Process a command and return a structured result."""
        response, actions = await self.process_request(command)
        return {"response": response, "actions": actions}
