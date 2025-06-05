from __future__ import annotations

from typing import Optional

from .agent import AICalendarAgent
from .main_agent import AIMainAgent
from .calendar_service import CalendarService
from .logger import JarvisLogger
from .ai_clients import BaseAIClient


class AgentFactory:
    """Factory to create agent instances based on a type string."""

    @staticmethod
    def create(
        agent_type: str,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
    ) -> AICalendarAgent | AIMainAgent:
        agent_type = agent_type.lower()
        if agent_type in {"calendar", "calendar_agent", "aicalendaragent"}:
            service = CalendarService(logger=logger)
            return AICalendarAgent(ai_client, service, logger=logger)
        if agent_type in {"jarvis", "main", "main_agent"}:
            service = CalendarService(logger=logger)
            calendar_agent = AICalendarAgent(ai_client, service, logger=logger)
            return AIMainAgent(ai_client, {"calendar": calendar_agent}, logger=logger)
        raise ValueError(f"Unsupported agent type: {agent_type}")
