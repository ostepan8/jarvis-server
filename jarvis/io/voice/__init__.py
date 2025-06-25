"""Voice input listeners and registry."""

from .base import VoiceInputInterface
from .registry import VoiceInputRegistry
from .vosk_listener import VoskVoiceListener

# Import default listener registrations
try:  # pragma: no cover - optional deps
    from . import listeners
except Exception:
    listeners = None


def input(name: str) -> VoiceInputInterface:
    """Create a registered voice listener by ``name``."""
    return VoiceInputRegistry.create(name)

__all__ = ["VoiceInputInterface", "VoiceInputRegistry", "VoskVoiceListener", "input"]
