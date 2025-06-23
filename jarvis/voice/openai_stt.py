# openai_stt.py
import asyncio
import io
import os
import tempfile
import wave
from typing import Optional

import numpy as np
import sounddevice as sd
import openai

from ..logger import JarvisLogger
from .speech_to_text import SpeechToTextEngine


class OpenAISTTEngine(SpeechToTextEngine):
    """Speech-to-text engine using OpenAI's Whisper API."""

    def __init__(
        self,
        model: str = "whisper-1",
        api_key: str | None = None,
        *,
        logger: JarvisLogger | None = None,
        sample_rate: int = 16000,
        silence_threshold: float = 0.01,
        silence_duration: float = 2.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.logger = logger or JarvisLogger()
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration

    async def listen_for_speech(self, timeout: float = 10.0) -> str:
        """Listen for speech and return transcribed text."""
        try:
            # Record audio - properly await the coroutine
            audio_data = await self._record_audio_with_silence_detection(timeout)

            if len(audio_data) == 0:
                return ""

            # Save to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                self._save_wav(audio_data, temp_file.name)

                # Transcribe using OpenAI Whisper
                with open(temp_file.name, "rb") as audio_file:
                    transcript = await self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        language="en",  # Specify language for better accuracy
                    )

                # Clean up temp file
                os.unlink(temp_file.name)

                result = transcript.text.strip()
                self.logger.log("INFO", "Speech transcribed", f"'{result}'")
                return result

        except Exception as exc:
            self.logger.log("ERROR", "Speech recognition error", str(exc))
            return ""

    async def _record_audio_with_silence_detection(self, timeout: float) -> np.ndarray:
        """Record audio until silence is detected or timeout."""
        # Check if audio devices are available
        try:
            devices = sd.query_devices()
            if not devices:
                self.logger.log("ERROR", "No audio devices found")
                return np.array([])

            # Find default input device
            default_input = sd.default.device[0]
            if default_input is None:
                self.logger.log("ERROR", "No default input device found")
                return np.array([])

        except Exception as e:
            self.logger.log("ERROR", "Audio device check failed", str(e))
            return np.array([])

        audio_data = []
        silence_start = None
        recording_started = False
        stream_error = False

        def audio_callback(indata, frames, time, status):
            nonlocal silence_start, recording_started, stream_error

            # Handle status flags first
            if status:
                status_msg = []
                if status.input_underflow:
                    status_msg.append("input_underflow")
                if status.input_overflow:
                    status_msg.append("input_overflow")
                if status.output_underflow:
                    status_msg.append("output_underflow")
                if status.output_overflow:
                    status_msg.append("output_overflow")
                if status.priming_output:
                    status_msg.append("priming_output")

                status_str = "|".join(status_msg) if status_msg else str(status)
                self.logger.log("WARNING", "Audio input status", status_str)

                # Only treat certain status conditions as fatal
                if status.input_overflow or status.output_overflow:
                    stream_error = True
                    raise sd.CallbackStop()

            try:
                # Validate input data
                if indata is None or len(indata) == 0:
                    return  # Skip this frame

                # Ensure indata is the right shape
                if indata.ndim != 2 or indata.shape[1] != 1:
                    self.logger.log(
                        "WARNING",
                        "Unexpected audio data shape",
                        f"Shape: {indata.shape}",
                    )
                    return

                # Calculate RMS (volume level) safely
                try:
                    # Flatten to 1D for RMS calculation
                    audio_1d = indata.flatten()
                    volume_norm = np.sqrt(np.mean(audio_1d**2))
                except (ValueError, FloatingPointError) as e:
                    self.logger.log("WARNING", "RMS calculation error", str(e))
                    volume_norm = 0.0

                # Start recording when we detect sound
                if volume_norm > self.silence_threshold:
                    if not recording_started:
                        self.logger.log(
                            "DEBUG",
                            "Started recording speech",
                            f"Volume: {volume_norm:.4f}",
                        )
                        recording_started = True
                    silence_start = None
                    # Store copy of the audio data
                    audio_data.extend(indata.copy())
                else:
                    # We're in silence
                    if recording_started:
                        # Still add the silence data to avoid cutting off words
                        audio_data.extend(indata.copy())

                        if silence_start is None:
                            silence_start = time.inputBufferAdcTime
                        elif (
                            time.inputBufferAdcTime - silence_start
                            > self.silence_duration
                        ):
                            # End recording after silence
                            self.logger.log(
                                "DEBUG", "Silence detected, stopping recording"
                            )
                            raise sd.CallbackStop()

            except sd.CallbackStop:
                # Re-raise this specific exception
                raise
            except Exception as e:
                # Capture more detailed error information
                import traceback

                error_details = f"Type: {type(e).__name__}, Message: {str(e)}, Traceback: {traceback.format_exc()[:500]}"
                self.logger.log("ERROR", "Audio callback error", error_details)
                stream_error = True
                raise sd.CallbackStop()

        try:
            # Create and start the stream with error handling
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                callback=audio_callback,
                blocksize=1024,
            )

            with stream:
                # Wait for recording to complete or timeout
                await asyncio.sleep(timeout)

        except sd.CallbackStop:
            # Normal end of recording due to silence or error
            if stream_error:
                self.logger.log("ERROR", "Audio stream error during recording")
                return np.array([])
        except Exception as e:
            self.logger.log("ERROR", "Audio recording failed", str(e))
            return np.array([])

        if audio_data:
            return np.concatenate(audio_data)
        return np.array([])

    def _save_wav(self, audio_data: np.ndarray, filename: str) -> None:
        """Save audio data as WAV file."""
        # Convert float32 to int16
        audio_int16 = (audio_data * 32767).astype(np.int16)

        with wave.open(filename, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes per sample (int16)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
