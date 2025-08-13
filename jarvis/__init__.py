"""Jarvis calendar assistant package."""

from .services.calendar_service import CalendarService
from .logging import JarvisLogger, LogViewerGUI
from .core import (
    JarvisConfig,
    JarvisSystem,
    DEFAULT_PORT,
    LOG_DB_PATH,
    ExecutionResult,
    BaseRegistry,
    FunctionRegistry,
)
from .ai_clients import (
    AIClientFactory,
    BaseAIClient,
    OpenAIClient,
    AnthropicClient,
)
from .agents.agent_network import AgentNetwork
from .agents.calendar_agent import CollaborativeCalendarAgent
from .protocols import Protocol, ProtocolStep
from .protocols.registry import ProtocolRegistry
from .protocols.executor import ProtocolExecutor
from .protocols.builder import create_from_file
from .utils.performance import PerfTracker, track_async

PicovoiceWakeWordListener = None
OpenAITTSEngine = None
ElevenLabsTTSEngine = None
VoiceInputSystem = None

__all__ = [
    "CalendarService",
    "AIClientFactory",
    "BaseAIClient",
    "OpenAIClient",
    "AnthropicClient",
    "JarvisLogger",
    "LogViewerGUI",
    "AgentNetwork",
    "CollaborativeCalendarAgent",
    "JarvisSystem",
    "JarvisConfig",
    "Protocol",
    "ProtocolStep",
    "ProtocolRegistry",
    "BaseRegistry",
    "FunctionRegistry",
    "ProtocolExecutor",
    "create_from_file",
    "DEFAULT_PORT",
    "LOG_DB_PATH",
    "ExecutionResult",
    "PerfTracker",
    "track_async",
]
