from __future__ import annotations

import asyncio
import json
import queue
from typing import AsyncIterator, List, Optional

import sounddevice as sd
import vosk
from colorama import Fore, Style

from .base import VoiceInputInterface


class VoskVoiceListener(VoiceInputInterface):
    """Real-time speech recognition using a Vosk model."""

    def __init__(
        self,
        model_path: str,
        *,
        sample_rate: int = 16000,
        chunk_size: int = 8000,
        model_name: str = "vosk",
        grammar: Optional[List[str]] = None,
        debug: bool = True,
        device: Optional[int] = None,
    ) -> None:
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.model_name = model_name
        self.grammar = grammar
        self.debug = debug
        self.device = device
        self.model = vosk.Model(model_path)

    def set_grammar(self, phrases: List[str]) -> None:
        """Update recognizer grammar phrases."""
        self.grammar = phrases

    async def listen(self) -> AsyncIterator[str]:  # noqa: D401
        """Yield transcription chunks from microphone input."""
        audio_q: queue.Queue[bytes] = queue.Queue()

        def callback(indata, frames, time, status):
            if status and self.debug:
                print(f"[{self.model_name}] {status}")
            audio_q.put(bytes(indata))

        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        recognizer.SetWords(True)
        if self.grammar:
            recognizer.SetGrammar(json.dumps(self.grammar))

        stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.chunk_size,
            dtype="int16",
            channels=1,
            callback=callback,
            device=self.device,
        )

        last_partial = ""
        with stream:
            try:
                while True:
                    data = await asyncio.to_thread(audio_q.get)
                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "")
                        if text:
                            if self.debug:
                                print(Fore.GREEN + text + Style.RESET_ALL)
                            yield text
                        break
                    else:
                        partial = json.loads(recognizer.PartialResult()).get(
                            "partial", ""
                        )
                        if partial and partial != last_partial:
                            last_partial = partial
                            if self.debug:
                                print(Fore.CYAN + partial + Style.RESET_ALL)
                            yield partial
            except KeyboardInterrupt:
                if self.debug:
                    print("\nStopping voice listener")
            finally:
                if self.debug:
                    print("Listener exited")
