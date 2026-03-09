"""Tests for IO layer - input handlers, output handlers, TTS, STT, wake word."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.io.base import (
    InputHandler,
    OutputHandler,
    ConsoleInput,
    ConsoleOutput,
)
from jarvis.io.input.wakeword.base import WakeWordListener
from jarvis.io.input.wakeword.mock import MockWakeWordListener
from jarvis.io.input.transcription.base import SpeechToTextEngine
from jarvis.io.output.tts.base import TextToSpeechEngine
from jarvis.io.output.tts.mock import MockTTSEngine
from jarvis.io.input.system import VoiceInputSystem


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

class TestInputHandler:
    """Test InputHandler abstract base class."""

    @pytest.mark.asyncio
    async def test_get_input_raises_not_implemented(self):
        """Test base InputHandler.get_input raises NotImplementedError."""
        handler = InputHandler()
        with pytest.raises(NotImplementedError):
            await handler.get_input("prompt> ")


class TestOutputHandler:
    """Test OutputHandler abstract base class."""

    @pytest.mark.asyncio
    async def test_send_output_raises_not_implemented(self):
        """Test base OutputHandler.send_output raises NotImplementedError."""
        handler = OutputHandler()
        with pytest.raises(NotImplementedError):
            await handler.send_output("test message")


class TestConsoleOutput:
    """Test ConsoleOutput handler."""

    @pytest.mark.asyncio
    async def test_send_output_writes_to_stdout(self):
        """Test ConsoleOutput writes message to stdout."""
        handler = ConsoleOutput()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write = MagicMock()
            mock_stdout.flush = MagicMock()
            await handler.send_output("Hello, world!")
            mock_stdout.write.assert_called_once_with("Hello, world!\n")
            mock_stdout.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_output_empty_string(self):
        """Test ConsoleOutput handles empty string."""
        handler = ConsoleOutput()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write = MagicMock()
            mock_stdout.flush = MagicMock()
            await handler.send_output("")
            mock_stdout.write.assert_called_once_with("\n")


class TestConsoleInput:
    """Test ConsoleInput handler."""

    def test_init(self):
        """Test ConsoleInput initializes without error."""
        handler = ConsoleInput()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_get_input_returns_string(self):
        """Test ConsoleInput.get_input returns user input."""
        handler = ConsoleInput()
        with patch("builtins.input", return_value="test input"):
            result = await handler.get_input("prompt> ")
            assert result == "test input"

    @pytest.mark.asyncio
    async def test_get_input_handles_eof(self):
        """Test ConsoleInput handles EOFError gracefully."""
        handler = ConsoleInput()
        with patch("builtins.input", side_effect=EOFError):
            result = await handler.get_input("prompt> ")
            assert result == ""

    @pytest.mark.asyncio
    async def test_get_input_handles_keyboard_interrupt(self):
        """Test ConsoleInput handles KeyboardInterrupt gracefully."""
        handler = ConsoleInput()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = await handler.get_input("prompt> ")
            assert result == ""


# ---------------------------------------------------------------------------
# Wake Word
# ---------------------------------------------------------------------------

class TestWakeWordListenerBase:
    """Test WakeWordListener abstract base class."""

    @pytest.mark.asyncio
    async def test_wait_for_wake_word_raises_not_implemented(self):
        """Test base WakeWordListener raises NotImplementedError."""
        # Cannot instantiate ABC directly, so use a minimal subclass
        class StubListener(WakeWordListener):
            async def wait_for_wake_word(self):
                return await super().wait_for_wake_word()

        listener = StubListener()
        with pytest.raises(NotImplementedError):
            await listener.wait_for_wake_word()


class TestMockWakeWordListener:
    """Test MockWakeWordListener."""

    @pytest.mark.asyncio
    async def test_triggers_immediately_with_zero_delay(self):
        """Test mock listener returns immediately with zero delay."""
        listener = MockWakeWordListener(delay=0.0)
        assert listener.triggered is False
        await listener.wait_for_wake_word()
        assert listener.triggered is True

    @pytest.mark.asyncio
    async def test_triggers_after_delay(self):
        """Test mock listener waits for specified delay."""
        listener = MockWakeWordListener(delay=0.05)
        assert listener.triggered is False
        await listener.wait_for_wake_word()
        assert listener.triggered is True

    def test_default_delay_is_zero(self):
        """Test default delay is 0.0."""
        listener = MockWakeWordListener()
        assert listener.delay == 0.0

    @pytest.mark.asyncio
    async def test_can_be_called_multiple_times(self):
        """Test mock listener can be triggered multiple times."""
        listener = MockWakeWordListener(delay=0.0)
        await listener.wait_for_wake_word()
        assert listener.triggered is True
        # Reset and trigger again
        listener.triggered = False
        await listener.wait_for_wake_word()
        assert listener.triggered is True


# ---------------------------------------------------------------------------
# Speech To Text
# ---------------------------------------------------------------------------

class TestSpeechToTextEngineBase:
    """Test SpeechToTextEngine abstract base class."""

    @pytest.mark.asyncio
    async def test_listen_for_speech_raises_not_implemented(self):
        """Test base SpeechToTextEngine raises NotImplementedError."""
        class StubSTT(SpeechToTextEngine):
            async def listen_for_speech(self, timeout=5.0):
                return await super().listen_for_speech(timeout)

        engine = StubSTT()
        with pytest.raises(NotImplementedError):
            await engine.listen_for_speech()


# ---------------------------------------------------------------------------
# Text To Speech
# ---------------------------------------------------------------------------

class TestTextToSpeechEngineBase:
    """Test TextToSpeechEngine abstract base class."""

    @pytest.mark.asyncio
    async def test_speak_raises_not_implemented(self):
        """Test base TextToSpeechEngine raises NotImplementedError."""
        class StubTTS(TextToSpeechEngine):
            async def speak(self, text):
                return await super().speak(text)

        engine = StubTTS()
        with pytest.raises(NotImplementedError):
            await engine.speak("Hello")


class TestMockTTSEngine:
    """Test MockTTSEngine."""

    @pytest.mark.asyncio
    async def test_speak_records_text(self):
        """Test mock TTS engine records spoken text."""
        engine = MockTTSEngine()
        await engine.speak("Hello, world!")
        assert "Hello, world!" in engine.spoken

    @pytest.mark.asyncio
    async def test_speak_multiple_texts(self):
        """Test mock TTS engine records multiple spoken texts in order."""
        engine = MockTTSEngine()
        await engine.speak("First")
        await engine.speak("Second")
        await engine.speak("Third")
        assert engine.spoken == ["First", "Second", "Third"]

    @pytest.mark.asyncio
    async def test_spoken_starts_empty(self):
        """Test spoken list starts empty."""
        engine = MockTTSEngine()
        assert engine.spoken == []

    @pytest.mark.asyncio
    async def test_speak_empty_string(self):
        """Test mock TTS engine handles empty string."""
        engine = MockTTSEngine()
        await engine.speak("")
        assert engine.spoken == [""]

    def test_init(self):
        """Test MockTTSEngine initializes correctly."""
        engine = MockTTSEngine()
        assert isinstance(engine, TextToSpeechEngine)
        assert engine.spoken == []


# ---------------------------------------------------------------------------
# VoiceInputSystem
# ---------------------------------------------------------------------------

class DummySpeechToTextEngine(SpeechToTextEngine):
    """Stub STT engine that returns predetermined text."""

    def __init__(self, text="Hello Jarvis"):
        self.text = text
        self.call_count = 0

    async def listen_for_speech(self, timeout=5.0):
        self.call_count += 1
        return self.text


class TestVoiceInputSystem:
    """Test VoiceInputSystem integration."""

    @pytest.mark.asyncio
    async def test_listen_and_respond_with_handler(self):
        """Test full flow: wake word -> STT -> handler -> TTS."""
        wake = MockWakeWordListener(delay=0.0)
        stt = DummySpeechToTextEngine(text="turn on the lights")
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)

        async def handler(text):
            return f"Done: {text}"

        await system.listen_and_respond(handler=handler)

        assert wake.triggered is True
        assert stt.call_count == 1
        assert len(tts.spoken) == 1
        assert tts.spoken[0] == "Done: turn on the lights"

    @pytest.mark.asyncio
    async def test_listen_and_respond_without_handler(self):
        """Test flow without handler echoes recognized text."""
        wake = MockWakeWordListener(delay=0.0)
        stt = DummySpeechToTextEngine(text="test input")
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)
        await system.listen_and_respond(handler=None)

        assert tts.spoken[0] == "I heard: test input"

    @pytest.mark.asyncio
    async def test_listen_and_respond_empty_speech(self):
        """Test flow when STT returns empty string."""
        wake = MockWakeWordListener(delay=0.0)
        stt = DummySpeechToTextEngine(text="")
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)
        await system.listen_and_respond(handler=None)

        assert len(tts.spoken) == 1
        assert "didn't catch that" in tts.spoken[0]

    @pytest.mark.asyncio
    async def test_listen_and_respond_handler_error(self):
        """Test flow when handler raises an exception."""
        wake = MockWakeWordListener(delay=0.0)
        stt = DummySpeechToTextEngine(text="cause error")
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)

        async def bad_handler(text):
            raise RuntimeError("Handler failure")

        await system.listen_and_respond(handler=bad_handler)

        # Should speak error message
        assert len(tts.spoken) >= 1
        assert "technical difficulties" in tts.spoken[0]

    def test_stop_sets_running_false(self):
        """Test stop method sets _running to False."""
        wake = MockWakeWordListener()
        stt = DummySpeechToTextEngine()
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)
        system._running = True
        system.stop()
        assert system._running is False

    def test_initial_state(self):
        """Test VoiceInputSystem initial state."""
        wake = MockWakeWordListener()
        stt = DummySpeechToTextEngine()
        tts = MockTTSEngine()

        system = VoiceInputSystem(wake, stt, tts)
        assert system.wake_listener is wake
        assert system.stt_engine is stt
        assert system.tts_engine is tts
        assert system._running is False


# ---------------------------------------------------------------------------
# Custom implementations conforming to interfaces
# ---------------------------------------------------------------------------

class TestCustomImplementations:
    """Test that custom implementations conform to the base interfaces."""

    def test_mock_wake_word_is_wake_word_listener(self):
        """Test MockWakeWordListener is a WakeWordListener subclass."""
        listener = MockWakeWordListener()
        assert isinstance(listener, WakeWordListener)

    def test_mock_tts_is_text_to_speech_engine(self):
        """Test MockTTSEngine is a TextToSpeechEngine subclass."""
        engine = MockTTSEngine()
        assert isinstance(engine, TextToSpeechEngine)

    def test_console_input_is_input_handler(self):
        """Test ConsoleInput is an InputHandler subclass."""
        handler = ConsoleInput()
        assert isinstance(handler, InputHandler)

    def test_console_output_is_output_handler(self):
        """Test ConsoleOutput is an OutputHandler subclass."""
        handler = ConsoleOutput()
        assert isinstance(handler, OutputHandler)

    def test_dummy_stt_is_speech_to_text_engine(self):
        """Test DummySpeechToTextEngine is a SpeechToTextEngine subclass."""
        engine = DummySpeechToTextEngine()
        assert isinstance(engine, SpeechToTextEngine)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
