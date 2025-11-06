"""Agent implementations used within the AgentNetwork."""

from .calendar_agent.agent import CollaborativeCalendarAgent
from .task import Task
from .base import NetworkAgent
from .agent_network import AgentNetwork
from .protocol_agent import ProtocolAgent

from .weather_agent import WeatherAgent
from .memory_agent import MemoryAgent
from .chat_agent import ChatAgent

# from .canvas import CanvasAgent

__all__ = [
    "CollaborativeCalendarAgent",
    "Task",
    "NetworkAgent",
    "AgentNetwork",
    "ProtocolAgent",
    "WeatherAgent",
    "MemoryAgent",
    "ChatAgent",
    # "CanvasAgent",
]
