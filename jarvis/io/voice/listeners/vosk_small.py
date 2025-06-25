from __future__ import annotations

import os
from functools import partial

from ..registry import VoiceInputRegistry
from ..vosk_listener import VoskVoiceListener

MODEL_PATH = os.path.join("models", "vosk-model-small-en-us-0.15")


def _factory() -> VoskVoiceListener:
    return VoskVoiceListener(MODEL_PATH, model_name="vosk-small")


VoiceInputRegistry.register("vosk-small", _factory)
