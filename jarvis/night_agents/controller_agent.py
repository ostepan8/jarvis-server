from __future__ import annotations

from typing import Any, Optional, Set, TYPE_CHECKING

from ..agents.base import NetworkAgent
from ..agents.message import Message
from ..logger import JarvisLogger

if TYPE_CHECKING:
    from ..main_jarvis import JarvisSystem


class NightModeControllerAgent(NetworkAgent):
    """Agent that toggles Jarvis night mode."""

    def __init__(
        self, system: "JarvisSystem", logger: Optional[JarvisLogger] = None
    ) -> None:
        super().__init__("NightModeControllerAgent", logger)
        self.system = system

    @property
    def description(self) -> str:
        return "Controls entry and exit from night mode"

    @property
    def capabilities(self) -> Set[str]:
        return {"start_night_mode", "stop_night_mode"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability == "start_night_mode":
            await self.system.enter_night_mode()
            await self.send_capability_response(
                message.from_agent,
                {"status": "night_mode_enabled"},
                message.request_id,
                message.id,
            )
        elif capability == "stop_night_mode":
            await self.system.exit_night_mode()
            await self.send_capability_response(
                message.from_agent,
                {"status": "night_mode_disabled"},
                message.request_id,
                message.id,
            )

    async def _handle_capability_response(self, message: Message) -> None:
        # Controller does not expect capability responses
        # Using _ to indicate intentionally unused parameter
        _ = message
        return None

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a capability using the agent's function map.

        Subclasses can override this to provide custom execution logic.
        """
        if capability == "start_night_mode":
            return await self.system.enter_night_mode()
        elif capability == "stop_night_mode":
            return await self.system.exit_night_mode()
        else:
            raise NotImplementedError(
                f"Capability '{capability}' not implemented in NightModeControllerAgent"
            )
