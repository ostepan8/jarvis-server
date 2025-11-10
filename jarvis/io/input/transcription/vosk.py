from __future__ import annotations

import asyncio
import json
import os
import time
import queue
from typing import Iterable, Optional

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model
from colorama import Fore, Style

from ....logging import JarvisLogger
from ....utils.performance import get_tracker
from .base import SpeechToTextEngine


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
                # pass the list directly
                self.recognizer.SetGrammar(self.grammar)
        except Exception as e:
            self.logger.log("ERROR", "Failed to initialize Vosk model", str(e))
            raise

    async def listen_for_speech(self, timeout: float = 10.0) -> str:
        """Async wrapper around the blocking _sync_listen call."""
        tracker = get_tracker()
        if tracker and tracker.enabled:
            async with tracker.timer(
                "stt",
                metadata={"engine": "vosk", "model": self.model_name},
            ):
                return await asyncio.to_thread(self._sync_listen, timeout)
        return await asyncio.to_thread(self._sync_listen, timeout)

    def _sync_listen(self, timeout: float) -> str:
        """Blocking listen until final result or timeout, returns the recognized text."""
        q: queue.Queue[bytes] = queue.Queue()
        rec = self.recognizer
        results: list[str] = []
        last_partial = ""

        def callback(indata, frames, time_info, status):
            if status:
                self.logger.log("WARNING", "Audio input status", str(status))
            # convert indata (numpy array or buffer) to bytes
            try:
                if isinstance(indata, np.ndarray):
                    buf = (
                        indata.astype(np.int16)
                        if indata.dtype == np.int16
                        else (indata * 32767).astype(np.int16)
                    )
                    audio_bytes = buf.tobytes()
                else:
                    audio_bytes = bytes(indata)
                q.put(audio_bytes)
            except Exception as e:
                # log unexpected conversion errors
                self.logger.log("ERROR", "Audio buffer conversion failed", str(e))

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.chunk_size,
                dtype="int16",
                channels=1,
                callback=callback,
            ) as stream:
                start = time.time()
                while True:
                    # timeout?
                    if time.time() - start > timeout:
                        break

                    try:
                        data = q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if rec.AcceptWaveform(data):
                        # final chunk
                        try:
                            res = json.loads(rec.Result())
                            text = res.get("text", "")
                        except Exception:
                            text = ""
                        if text:
                            results.append(text)
                            if self.debug and self.logger:
                                self.logger.log("DEBUG", "Partial transcription", {"text": text})
                        break
                    else:
                        # partial update
                        try:
                            part = json.loads(rec.PartialResult())
                            p = part.get("partial", "")
                        except Exception:
                            p = ""
                        if self.debug and p and p != last_partial:
                            last_partial = p
                            if self.logger:
                                self.logger.log("DEBUG", "Partial transcription update", {"partial": p})

        except Exception as e:
            self.logger.log("ERROR", "Audio recording failed", str(e))
            return ""

        # ensure any buffered final result is captured
        try:
            final = json.loads(rec.FinalResult()).get("text", "")
        except Exception:
            final = ""
        if final:
            results.append(final)
            if self.debug and self.logger:
                self.logger.log("DEBUG", "Final transcription", {"text": final})

        text = " ".join(results).strip()
        if text:
            self.logger.log("INFO", "Speech transcribed", text)
        return text


class VoskSmallEnglishSTTEngine(VoskSTTEngine):
    """Convenience engine using the lightweight English model."""

    def __init__(
        self, model_path: str = "vosk-model-small-en-us-0.15", **kwargs
    ) -> None:
        super().__init__(model_path, model_name="vosk-small-en", **kwargs)


class VoskLGraphSTTEngine(VoskSTTEngine):
    """Engine using the graph-based English model with optional grammar."""

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
