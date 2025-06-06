"""Agent implementations used within the AgentNetwork."""

from .calendar_agent import CollaborativeCalendarAgent
from .ui_agent import UIAgent
from .base import NetworkAgent
from .agent_network import AgentNetwork

__all__ = [
    "CollaborativeCalendarAgent",
    "UIAgent",
    "NetworkAgent",
    "AgentNetwork",
]
