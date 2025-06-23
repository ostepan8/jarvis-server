"""Jarvis calendar assistant package."""

from .services.calendar_service import CalendarService
from .logger import JarvisLogger
from .config import JarvisConfig
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
from .constants import (
    DEFAULT_PORT,
    LOG_DB_PATH,
    PROTOCOL_RESPONSES,
    ExecutionResult,
)
from .performance import PerfTracker, track_async

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
    "LogViewer",
    "AgentNetwork",
    "CollaborativeCalendarAgent",
    "JarvisSystem",
    "create_collaborative_jarvis",
    "JarvisConfig",
    "Protocol",
    "ProtocolStep",
    "ProtocolRegistry",
    "ProtocolExecutor",
    "create_from_file",
    "DEFAULT_PORT",
    "LOG_DB_PATH",
    "PROTOCOL_RESPONSES",
    "ExecutionResult",
    "PerfTracker",
    "track_async",
]
