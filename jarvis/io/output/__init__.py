"""Output handling components."""

from .tts.base import TextToSpeechEngine
from .tts.mock import MockTTSEngine

__all__ = ["TextToSpeechEngine", "MockTTSEngine"]
