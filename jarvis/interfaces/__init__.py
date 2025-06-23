"""Common interfaces for voice input and output."""

from .wake_word import WakeWordListener
from .text_to_speech import TextToSpeechEngine

__all__ = [
    "WakeWordListener",
    "TextToSpeechEngine",
]
