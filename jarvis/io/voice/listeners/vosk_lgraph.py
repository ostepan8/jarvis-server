from __future__ import annotations

import os

from ..registry import VoiceInputRegistry
from ..vosk_listener import VoskVoiceListener

MODEL_PATH = os.path.join("models", "vosk-model-en-us-0.22-lgraph")


def _factory() -> VoskVoiceListener:
    return VoskVoiceListener(MODEL_PATH, model_name="vosk-lgraph")


VoiceInputRegistry.register("vosk-lgraph", _factory)
