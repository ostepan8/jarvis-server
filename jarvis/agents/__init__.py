"""Agent implementations used within the AgentNetwork."""

from .calendar_agent.agent import CollaborativeCalendarAgent
from .orchestrator_agent import OrchestratorAgent
from .task import Task
from .base import NetworkAgent
from .agent_network import AgentNetwork
from .protocol_agent import ProtocolAgent
from .software_engineering_agent import SoftwareEngineeringAgent
from .weather_agent import WeatherAgent
from .memory_agent import MemoryAgent

# from .canvas import CanvasAgent

__all__ = [
    "CollaborativeCalendarAgent",
    "OrchestratorAgent",
    "Task",
    "NetworkAgent",
    "AgentNetwork",
    "ProtocolAgent",
    "SoftwareEngineeringAgent",
    "WeatherAgent",
    "MemoryAgent",
    # "CanvasAgent",
]
