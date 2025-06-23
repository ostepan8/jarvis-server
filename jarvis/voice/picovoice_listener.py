from __future__ import annotations

import asyncio
import os
from typing import Iterable, Sequence

import numpy as np
import sounddevice as sd
import pvporcupine

from ..logger import JarvisLogger
from ..interfaces import WakeWordListener


class PicovoiceWakeWordListener(WakeWordListener):
    """Wake word listener using Picovoice Porcupine."""

    def __init__(
        self,
        access_key: str | None = None,
        keyword_paths: Sequence[str] | None = None,
        *,
        debug: bool = False,
        logger: JarvisLogger | None = None,
    ) -> None:
        self.access_key = access_key or os.getenv("PICOVOICE_ACCESS_KEY")
        if not self.access_key:
            raise ValueError("Picovoice access key required")
        self.keyword_paths = list(keyword_paths or [])
        self.logger = logger or JarvisLogger()
        self.debug = debug
        self._porcupine = pvporcupine.create(
            access_key=self.access_key, keyword_paths=self.keyword_paths or None
        )
        self._stream = sd.InputStream(
            samplerate=self._porcupine.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._porcupine.frame_length,
        )

    async def wait_for_wake_word(self) -> None:  # noqa: D401 - interface impl
        """Wait until a wake word is detected."""

        def _detect() -> None:
            with self._stream:
                for pcm, _ in self._stream.read_iter(self._porcupine.frame_length):
                    pcm = np.frombuffer(pcm, dtype=np.int16)
                    result = self._porcupine.process(pcm)
                    if result >= 0:
                        if self.debug:
                            self.logger.log("DEBUG", "Wake word detected")
                        break
        try:
            await asyncio.to_thread(_detect)
        except Exception as exc:  # pragma: no cover - hardware errors
            self.logger.log("ERROR", "Wake word listener error", str(exc))

