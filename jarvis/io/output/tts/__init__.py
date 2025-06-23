from .base import TextToSpeechEngine
from .mock import MockTTSEngine

try:  # optional heavy deps
    from .openai import OpenAITTSEngine
    from .elevenlabs import ElevenLabsTTSEngine
except Exception:  # pragma: no cover - optional deps may be missing
    OpenAITTSEngine = None
    ElevenLabsTTSEngine = None

__all__ = [
    "TextToSpeechEngine",
    "MockTTSEngine",
    "OpenAITTSEngine",
    "ElevenLabsTTSEngine",
]
