from __future__ import annotations

import asyncio
import json
import os
from typing import Iterable, Optional

import sounddevice as sd
from vosk import KaldiRecognizer, Model
from colorama import Fore, Style

from ....logger import JarvisLogger
from .base import SpeechToTextEngine
from ....performance import get_tracker


class VoskSTTEngine(SpeechToTextEngine):
    """Speech-to-text engine using a local Vosk model."""

    def __init__(
        self,
        model_path: str,
        *,
        sample_rate: int = 16000,
        chunk_size: int = 8000,
        grammar: Optional[Iterable[str]] = None,
        model_name: Optional[str] = None,
        debug: bool = False,
        logger: JarvisLogger | None = None,
    ) -> None:
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.grammar = list(grammar) if grammar else None
        self.model_name = model_name or os.path.basename(model_path)
        self.debug = debug
        self.logger = logger or JarvisLogger()

        try:
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
            if self.grammar:
                self.recognizer.SetGrammar(json.dumps(self.grammar))
        except Exception as e:  # pragma: no cover - model init errors
            self.logger.log("ERROR", "Failed to initialize Vosk model", str(e))
            raise

    async def listen_for_speech(self, timeout: float = 10.0) -> str:  # noqa: D401 - interface impl
        """Listen for speech from the microphone and return the transcribed text."""

        async def _run() -> str:
            results: list[str] = []
            last_partial = ""

            def callback(indata, frames, time_, status):
                nonlocal last_partial
                if status:
                    self.logger.log("WARNING", "Audio input status", str(status))
                if self.recognizer.AcceptWaveform(indata):
                    try:
                        res = json.loads(self.recognizer.Result())
                        text = res.get("text", "")
                    except Exception:
                        text = ""
                    if text:
                        results.append(text)
                        if self.debug:
                            print(Fore.GREEN + text + Style.RESET_ALL)
                    raise sd.CallbackStop()
                else:
                    try:
                        partial = json.loads(self.recognizer.PartialResult()).get(
                            "partial", ""
                        )
                    except Exception:
                        partial = ""
                    if self.debug and partial and partial != last_partial:
                        last_partial = partial
                        print(Fore.YELLOW + partial + Style.RESET_ALL)

            try:
                stream = sd.RawInputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.chunk_size,
                    dtype="int16",
                    channels=1,
                    callback=callback,
                )
                with stream:
                    await asyncio.sleep(timeout)
            except sd.CallbackStop:
                pass
            except Exception as e:  # pragma: no cover - unexpected errors
                self.logger.log("ERROR", "Audio recording failed", str(e))
                return ""

            try:
                final = json.loads(self.recognizer.FinalResult()).get("text", "")
            except Exception:
                final = ""
            if final:
                results.append(final)
                if self.debug:
                    print(Fore.GREEN + final + Style.RESET_ALL)

            text = " ".join(results).strip()
            if text:
                self.logger.log("INFO", "Speech transcribed", text)
            return text

        tracker = get_tracker()
        if tracker and tracker.enabled:
            async with tracker.timer(
                "stt",
                metadata={"engine": "vosk", "model": self.model_name},
            ):
                return await _run()
        return await _run()


class VoskSmallEnglishSTTEngine(VoskSTTEngine):
    """Convenience engine using the lightweight English model."""

    def __init__(self, model_path: str = "vosk-model-small-en-us-0.15", **kwargs) -> None:
        super().__init__(model_path, model_name="vosk-small-en", **kwargs)


class VoskLGraphSTTEngine(VoskSTTEngine):
    """Engine using the graph-based large English model with optional grammar."""

    def __init__(
        self,
        model_path: str = "vosk-model-en-us-0.22-lgraph",
        *,
        grammar: Optional[Iterable[str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            model_path,
            model_name="vosk-lgraph",
            grammar=grammar,
            **kwargs,
        )


__all__ = [
    "VoskSTTEngine",
    "VoskSmallEnglishSTTEngine",
    "VoskLGraphSTTEngine",
]
