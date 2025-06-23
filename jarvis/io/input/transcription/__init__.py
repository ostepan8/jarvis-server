from .base import SpeechToTextEngine

try:  # optional heavy deps
    from .openai_whisper import OpenAISTTEngine
except Exception:  # pragma: no cover - optional deps may be missing
    OpenAISTTEngine = None

__all__ = ["SpeechToTextEngine", "OpenAISTTEngine"]
