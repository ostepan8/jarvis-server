from __future__ import annotations

import asyncio
import os
from typing import Iterable, Sequence

import numpy as np
import sounddevice as sd
import pvporcupine

from ..logger import JarvisLogger
from .wake_word import WakeWordListener


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
        self.access_key = access_key or os.getenv("PORCUPINE_API_KEY")
        if not self.access_key:
            raise ValueError("Picovoice access key required")
        self.keyword_paths = list(keyword_paths or [])
        self.logger = logger or JarvisLogger()
        self.debug = debug

        # Initialize Porcupine with error handling
        try:
            if not self.keyword_paths:
                # Use built-in "jarvis" keyword if no custom keyword paths are provided
                self._porcupine = pvporcupine.create(
                    access_key=self.access_key, keywords=["jarvis"]
                )
            else:
                self._porcupine = pvporcupine.create(
                    access_key=self.access_key, keyword_paths=self.keyword_paths
                )
        except Exception as e:
            self.logger.log("ERROR", "Failed to initialize Porcupine", str(e))
            raise

        # Don't initialize stream in constructor - do it when needed
        self._stream = None

    def _create_stream(self):
        """Create audio input stream with error handling."""
        try:
            # Check if audio devices are available
            devices = sd.query_devices()
            if not devices:
                raise RuntimeError("No audio devices found")

            # Find default input device
            default_input = sd.default.device[0]
            if default_input is None:
                raise RuntimeError("No default input device found")

            # Create the stream
            return sd.InputStream(
                samplerate=self._porcupine.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._porcupine.frame_length,
            )
        except Exception as e:
            self.logger.log("ERROR", "Failed to create audio stream", str(e))
            raise

    async def wait_for_wake_word(self) -> None:
        """Wait until a wake word is detected."""

        def _detect() -> None:
            # Create stream fresh each time to avoid "Invalid stream pointer" errors
            stream = self._create_stream()

            try:
                with stream:
                    while True:
                        try:
                            pcm, overflowed = stream.read(self._porcupine.frame_length)
                            if overflowed:
                                self.logger.log("WARNING", "Audio buffer overflowed")

                            pcm = np.frombuffer(pcm, dtype=np.int16)
                            result = self._porcupine.process(pcm)

                            if result >= 0:
                                if self.debug:
                                    self.logger.log("DEBUG", "Wake word detected")
                                break

                        except Exception as e:
                            self.logger.log(
                                "ERROR", "Error during wake word detection", str(e)
                            )
                            # Break on any error during detection
                            break

            except Exception as e:
                self.logger.log("ERROR", "Stream context error", str(e))
                raise

        try:
            await asyncio.to_thread(_detect)
        except Exception as exc:
            self.logger.log("ERROR", "Wake word listener error", str(exc))
            # Re-raise to let the caller handle it
            raise

    def __del__(self):
        """Clean up resources."""
        if hasattr(self, "_porcupine") and self._porcupine:
            try:
                self._porcupine.delete()
            except:
                pass
