from __future__ import annotations

import asyncio
import os

from .ai_clients import AIClientFactory
from .calendar_service import CalendarService
from .logger import JarvisLogger
from .network.core import AgentNetwork
from .network.agents.calendar_agent import CollaborativeCalendarAgent


async def demo() -> None:
    ai_client = AIClientFactory.create("dummy")
    logger = JarvisLogger()
    service = CalendarService(logger=logger)

    calendar_agent = CollaborativeCalendarAgent(ai_client, service, logger=logger)
    network = AgentNetwork(logger=logger)
    network.add_agent("calendar", calendar_agent)

    result = await network.dispatch("calendar", "List today's events")
    print(result)


def run() -> None:
    asyncio.run(demo())


if __name__ == "__main__":
    run()
