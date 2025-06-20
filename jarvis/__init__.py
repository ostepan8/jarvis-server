"""Jarvis calendar assistant package."""

from .services.calendar_service import CalendarService
from .logger import JarvisLogger
from .log_viewer import LogViewer
from .ai_clients import (
    AIClientFactory,
    BaseAIClient,
    OpenAIClient,
    AnthropicClient,
)
from .agents.agent_network import AgentNetwork
from .agents.calendar_agent import CollaborativeCalendarAgent
try:  # Optional import to avoid heavy dependencies during module import
    from .main_jarvis import JarvisSystem, create_collaborative_jarvis
except Exception:  # pragma: no cover - optional dependency may be missing
    JarvisSystem = None
    create_collaborative_jarvis = None
from .protocols import Protocol, ProtocolStep
from .protocols.registry import ProtocolRegistry
from .protocols.executor import ProtocolExecutor
from .protocols.builder import create_from_file
__all__ = [
    "CalendarService",
    "AIClientFactory",
    "BaseAIClient",
    "OpenAIClient",
    "AnthropicClient",
    "JarvisLogger",
    "LogViewer",
    "AgentNetwork",
    "CollaborativeCalendarAgent",
    "JarvisSystem",
    "create_collaborative_jarvis",
    "Protocol",
    "ProtocolStep",
    "ProtocolRegistry",
    "ProtocolExecutor",
    "create_from_file",
]
