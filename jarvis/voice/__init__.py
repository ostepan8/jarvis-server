"""Voice input/output related implementations."""

from .voice_input_system import VoiceInputSystem
from .mocks import MockWakeWordListener, MockTTSEngine

try:  # optional heavy deps
    from .picovoice_listener import PicovoiceWakeWordListener
    from .openai_tts import OpenAITTSEngine
    from .elevenlabs_tts import ElevenLabsTTSEngine
except Exception:  # pragma: no cover - optional deps may be missing
    PicovoiceWakeWordListener = None
    OpenAITTSEngine = None
    ElevenLabsTTSEngine = None

__all__ = [
    "PicovoiceWakeWordListener",
    "OpenAITTSEngine",
    "ElevenLabsTTSEngine",
    "VoiceInputSystem",
    "MockWakeWordListener",
    "MockTTSEngine",
]

