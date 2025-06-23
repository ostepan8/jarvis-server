from __future__ import annotations

import asyncio

from .base import WakeWordListener


class MockWakeWordListener(WakeWordListener):
    """Mock listener that triggers immediately for tests."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.triggered = False

    async def wait_for_wake_word(self) -> None:
        await asyncio.sleep(self.delay)
        self.triggered = True
