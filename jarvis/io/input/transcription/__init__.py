from .base import SpeechToTextEngine

try:  # optional heavy deps
    from .openai_whisper import OpenAISTTEngine
except Exception:  # pragma: no cover - optional deps may be missing
    OpenAISTTEngine = None

try:  # optional heavy deps
    from .vosk import VoskSTTEngine, VoskSmallEnglishSTTEngine, VoskLGraphSTTEngine
except Exception:  # pragma: no cover - optional deps may be missing
    VoskSTTEngine = None
    VoskSmallEnglishSTTEngine = None
    VoskLGraphSTTEngine = None

__all__ = [
    "SpeechToTextEngine",
    "OpenAISTTEngine",
    "VoskSTTEngine",
    "VoskSmallEnglishSTTEngine",
    "VoskLGraphSTTEngine",
]
