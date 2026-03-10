"""Tests for jarvis.core.response_logger — ResponseLogger and RequestTimer."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.core.response_logger import RequestTimer, ResponseLogger


# ---------------------------------------------------------------------------
# RequestTimer
# ---------------------------------------------------------------------------
class TestRequestTimer:
    """Tests for the RequestTimer utility class."""

    def test_initial_state(self):
        timer = RequestTimer()
        assert timer.start_time == 0.0
        assert timer.end_time == 0.0

    def test_start_sets_start_time(self):
        timer = RequestTimer()
        timer.start()
        assert timer.start_time > 0

    def test_start_returns_self(self):
        timer = RequestTimer()
        result = timer.start()
        assert result is timer

    def test_stop_sets_end_time(self):
        timer = RequestTimer()
        timer.start()
        timer.stop()
        assert timer.end_time > 0
        assert timer.end_time >= timer.start_time

    def test_stop_returns_elapsed_ms(self):
        timer = RequestTimer()
        timer.start()
        ms = timer.stop()
        assert isinstance(ms, float)
        assert ms >= 0

    def test_elapsed_ms_before_stop(self):
        timer = RequestTimer()
        timer.start()
        ms = timer.elapsed_ms()
        assert ms >= 0
        # end_time is still 0, so it uses current time
        assert timer.end_time == 0.0

    def test_elapsed_ms_after_stop(self):
        timer = RequestTimer()
        timer.start()
        timer.stop()
        ms = timer.elapsed_ms()
        assert ms >= 0
        # Should use stored end_time
        assert timer.end_time > 0

    def test_elapsed_ms_units_are_milliseconds(self):
        timer = RequestTimer()
        timer.start_time = 1.0
        timer.end_time = 1.1  # 100 ms
        ms = timer.elapsed_ms()
        assert abs(ms - 100.0) < 1.0

    def test_context_manager(self):
        with RequestTimer() as timer:
            assert timer.start_time > 0
        assert timer.end_time > 0
        assert timer.elapsed_ms() >= 0

    def test_context_manager_returns_timer(self):
        timer = RequestTimer()
        with timer as t:
            assert t is timer

    def test_context_manager_on_exception(self):
        timer = RequestTimer()
        try:
            with timer:
                raise ValueError("test error")
        except ValueError:
            pass
        # Timer should still be stopped on exception
        assert timer.end_time > 0


# ---------------------------------------------------------------------------
# ResponseLogger
# ---------------------------------------------------------------------------
class TestResponseLogger:
    """Tests for the ResponseLogger class."""

    def _make_logger(self):
        interaction_logger = AsyncMock()
        interaction_logger.log_interaction = AsyncMock()
        interaction_logger.close = AsyncMock()
        return ResponseLogger(interaction_logger), interaction_logger

    def test_init(self):
        interaction_logger = AsyncMock()
        rl = ResponseLogger(interaction_logger)
        assert rl.interaction_logger is interaction_logger

    @pytest.mark.asyncio
    async def test_log_successful_interaction(self):
        rl, mock_il = self._make_logger()
        await rl.log_successful_interaction(
            user_input="hello",
            response="world",
            intent="chat",
            capability="chat",
            latency_ms=100.0,
            user_id=1,
        )
        # Give the background task a moment to execute
        await asyncio.sleep(0.05)
        mock_il.log_interaction.assert_awaited_once()
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["user_input"] == "hello"
        assert call_kwargs["response"] == "world"
        assert call_kwargs["success"] is True
        assert call_kwargs["intent"] == "chat"
        assert call_kwargs["latency_ms"] == 100.0
        assert call_kwargs["user_id"] == 1

    @pytest.mark.asyncio
    async def test_log_successful_interaction_minimal(self):
        rl, mock_il = self._make_logger()
        await rl.log_successful_interaction(
            user_input="test",
            response="ok",
        )
        await asyncio.sleep(0.05)
        mock_il.log_interaction.assert_awaited_once()
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["success"] is True
        assert call_kwargs["intent"] is None
        assert call_kwargs["capability"] is None
        assert call_kwargs["user_id"] is None

    @pytest.mark.asyncio
    async def test_log_failed_interaction(self):
        rl, mock_il = self._make_logger()
        await rl.log_failed_interaction(
            user_input="fail test",
            error_message="something went wrong",
            intent="error",
            latency_ms=50.0,
            user_id=2,
        )
        await asyncio.sleep(0.05)
        mock_il.log_interaction.assert_awaited_once()
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["user_input"] == "fail test"
        assert call_kwargs["response"] == "something went wrong"
        assert call_kwargs["success"] is False
        assert call_kwargs["user_id"] == 2

    @pytest.mark.asyncio
    async def test_log_failed_interaction_minimal(self):
        rl, mock_il = self._make_logger()
        await rl.log_failed_interaction(
            user_input="err",
            error_message="oops",
        )
        await asyncio.sleep(0.05)
        mock_il.log_interaction.assert_awaited_once()
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["success"] is False
        assert call_kwargs["protocol_executed"] is None

    @pytest.mark.asyncio
    async def test_log_successful_interaction_all_params(self):
        rl, mock_il = self._make_logger()
        await rl.log_successful_interaction(
            user_input="test",
            response="ok",
            intent="calendar",
            capability="create_event",
            protocol_executed="morning_routine",
            agent_results={"events": []},
            tool_calls=[{"name": "create"}],
            latency_ms=200.0,
            user_id=5,
            device="phone",
            location="home",
            source="api",
        )
        await asyncio.sleep(0.05)
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["protocol_executed"] == "morning_routine"
        assert call_kwargs["agent_results"] == {"events": []}
        assert call_kwargs["tool_calls"] == [{"name": "create"}]
        assert call_kwargs["device"] == "phone"
        assert call_kwargs["location"] == "home"
        assert call_kwargs["source"] == "api"

    @pytest.mark.asyncio
    async def test_log_failed_interaction_all_params(self):
        rl, mock_il = self._make_logger()
        await rl.log_failed_interaction(
            user_input="test",
            error_message="error",
            intent="search",
            capability="search",
            protocol_executed="check_search",
            latency_ms=150.0,
            user_id=3,
            device="laptop",
            location="office",
            source="cli",
        )
        await asyncio.sleep(0.05)
        call_kwargs = mock_il.log_interaction.call_args[1]
        assert call_kwargs["capability"] == "search"
        assert call_kwargs["device"] == "laptop"
        assert call_kwargs["source"] == "cli"

    @pytest.mark.asyncio
    async def test_close(self):
        rl, mock_il = self._make_logger()
        await rl.close()
        mock_il.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_with_none_logger(self):
        """Close should not raise if interaction_logger is falsy."""
        rl = ResponseLogger(interaction_logger=None)
        # This should not raise
        await rl.close()
