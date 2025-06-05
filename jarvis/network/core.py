"""Legacy imports for backward compatibility."""
from .message import Message
from .capability import Capability
from .agent_network import AgentNetwork
from .base_agent import NetworkAgent

__all__ = [
    "Message",
    "Capability",
    "AgentNetwork",
    "NetworkAgent",
]
