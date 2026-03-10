"""Tests for the feedback loop self-healing system."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from jarvis.core.feedback import FeedbackCollector
from jarvis.core.orchestrator import RequestOrchestrator
from jarvis.core.response_logger import ResponseLogger
from jarvis.agents.chat_agent.agent import ChatAgent
from jarvis.ai_clients.base import BaseAIClient
from jarvis.logging import JarvisLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyAIClient(BaseAIClient):
    def __init__(self, response_text="dummy"):
        self._response_text = response_text

    async def strong_chat(self, messages, tools=None):
        msg = type("Msg", (), {"content": self._response_text})()
        return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = type("Msg", (), {"content": self._response_text})()
        return msg, None


def _make_mock_response_logger():
    logger = AsyncMock(spec=ResponseLogger)
    logger.log_successful_interaction = AsyncMock()
    logger.log_failed_interaction = AsyncMock()
    return logger


# ---------------------------------------------------------------------------
# FeedbackCollector unit tests
# ---------------------------------------------------------------------------

class TestIsNegativeFeedback:
    def test_detects_exact_triggers(self):
        assert FeedbackCollector.is_negative_feedback("bad!") is True
        assert FeedbackCollector.is_negative_feedback("wrong") is True
        assert FeedbackCollector.is_negative_feedback("terrible") is True
        assert FeedbackCollector.is_negative_feedback("awful") is True
        assert FeedbackCollector.is_negative_feedback("no!") is True
        assert FeedbackCollector.is_negative_feedback("that's wrong") is True
        assert FeedbackCollector.is_negative_feedback("incorrect") is True

    def test_case_insensitive(self):
        assert FeedbackCollector.is_negative_feedback("BAD!") is True
        assert FeedbackCollector.is_negative_feedback("Wrong") is True
        assert FeedbackCollector.is_negative_feedback("TERRIBLE") is True

    def test_strips_whitespace(self):
        assert FeedbackCollector.is_negative_feedback("  bad!  ") is True
        assert FeedbackCollector.is_negative_feedback("\twrong\n") is True

    def test_ignores_normal_input(self):
        assert FeedbackCollector.is_negative_feedback("what's the weather?") is False
        assert FeedbackCollector.is_negative_feedback("that's a bad idea actually") is False
        assert FeedbackCollector.is_negative_feedback("tell me something") is False
        assert FeedbackCollector.is_negative_feedback("") is False


class TestLogCorrection:
    def test_creates_file_and_appends(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        cid = fc.log_correction(
            user_id=1,
            original_input="what time is it?",
            bad_response="It is banana o'clock.",
            feedback_text="bad!",
            intent="chat",
            capability="chat",
        )
        assert cid  # non-empty UUID string
        assert fc.corrections_file.exists()

        with open(fc.corrections_file) as f:
            record = json.loads(f.readline())
        assert record["id"] == cid
        assert record["user_id"] == 1
        assert record["original_input"] == "what time is it?"
        assert record["bad_response"] == "It is banana o'clock."
        assert record["resolved"] is False

    def test_appends_multiple(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        fc.log_correction(1, "q1", "a1", "bad!")
        fc.log_correction(1, "q2", "a2", "wrong")

        with open(fc.corrections_file) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 2


class TestGetCorrections:
    def test_returns_recent(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        fc.log_correction(1, "q1", "a1", "bad!")
        fc.log_correction(1, "q2", "a2", "wrong")
        fc.log_correction(2, "q3", "a3", "terrible")

        corrections = fc.get_corrections(limit=20)
        assert len(corrections) == 3

    def test_filters_by_user(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        fc.log_correction(1, "q1", "a1", "bad!")
        fc.log_correction(2, "q2", "a2", "wrong")

        corrections = fc.get_corrections(user_id=1)
        assert len(corrections) == 1
        assert corrections[0]["user_id"] == 1

    def test_respects_limit(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        for i in range(5):
            fc.log_correction(1, f"q{i}", f"a{i}", "bad!")

        corrections = fc.get_corrections(limit=2)
        assert len(corrections) == 2
        # Should be the two most recent
        assert corrections[0]["original_input"] == "q3"
        assert corrections[1]["original_input"] == "q4"

    def test_excludes_resolved(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        cid = fc.log_correction(1, "q1", "a1", "bad!")
        fc.log_correction(1, "q2", "a2", "wrong")
        fc.mark_resolved(cid)

        corrections = fc.get_corrections()
        assert len(corrections) == 1
        assert corrections[0]["original_input"] == "q2"

    def test_empty_when_no_file(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "nope"))
        assert fc.get_corrections() == []


class TestMarkResolved:
    def test_marks_and_persists(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        cid = fc.log_correction(1, "q1", "a1", "bad!")
        assert fc.mark_resolved(cid) is True

        # Re-read from disk
        with open(fc.corrections_file) as f:
            record = json.loads(f.readline())
        assert record["resolved"] is True

    def test_returns_false_for_missing_id(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        fc.log_correction(1, "q1", "a1", "bad!")
        assert fc.mark_resolved("nonexistent-id") is False


# ---------------------------------------------------------------------------
# Orchestrator intercept
# ---------------------------------------------------------------------------

class TestOrchestratorInterceptsFeedback:
    @pytest.mark.asyncio
    async def test_feedback_intercepts_and_logs(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        logger = JarvisLogger()
        network = MagicMock()
        network.agents = {}

        orchestrator = RequestOrchestrator(
            network=network,
            protocol_runtime=None,
            response_logger=_make_mock_response_logger(),
            logger=logger,
            feedback_collector=fc,
        )

        # Seed conversation history so there's something to flag
        orchestrator.conversation_history[1] = [
            {"user": "what time is it?", "assistant": "It is banana o'clock."}
        ]

        result = await orchestrator.process_request(
            "bad!", "UTC", metadata={"user_id": 1}
        )

        assert "flagged" in result["response"].lower()
        corrections = fc.get_corrections()
        assert len(corrections) == 1
        assert corrections[0]["original_input"] == "what time is it?"

    @pytest.mark.asyncio
    async def test_no_intercept_without_history(self, tmp_path):
        """Without prior conversation, feedback falls through (no crash)."""
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        logger = JarvisLogger()
        network = MagicMock()
        network.agents = {}
        network.capability_registry = {}
        network.request_capability = AsyncMock()
        network.wait_for_response = AsyncMock(
            return_value={"response": "hello", "success": True}
        )

        orchestrator = RequestOrchestrator(
            network=network,
            protocol_runtime=None,
            response_logger=_make_mock_response_logger(),
            logger=logger,
            feedback_collector=fc,
        )

        # No conversation history — feedback check returns None, falls to NLU
        result = await orchestrator.process_request(
            "bad!", "UTC", metadata={"user_id": 1}
        )
        # Should NOT have logged a correction (no history to reference)
        assert fc.get_corrections() == []


# ---------------------------------------------------------------------------
# ChatAgent correction injection
# ---------------------------------------------------------------------------

class TestCorrectionsInjectedIntoChatPrompt:
    @pytest.mark.asyncio
    async def test_correction_block_appears_in_prompt(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))
        fc.log_correction(1, "what time is it?", "It is banana o'clock.", "bad!")

        ai = DummyAIClient("Noted.")
        agent = ChatAgent(ai)
        agent.feedback_collector = fc
        agent.current_user_id = 1

        # Call _process_chat and inspect messages sent to AI
        captured_messages = []
        original_strong_chat = ai.strong_chat

        async def spy_strong_chat(messages, tools=None):
            captured_messages.extend(messages)
            return await original_strong_chat(messages, tools)

        ai.strong_chat = spy_strong_chat

        await agent._process_chat("hello", [])

        system_msg = captured_messages[0]["content"]
        assert "CORRECTION LOG" in system_msg
        assert "banana o'clock" in system_msg
        assert "WRONG" in system_msg

    @pytest.mark.asyncio
    async def test_no_correction_block_when_empty(self, tmp_path):
        fc = FeedbackCollector(feedback_dir=str(tmp_path / "feedback"))

        ai = DummyAIClient("Hello there.")
        agent = ChatAgent(ai)
        agent.feedback_collector = fc

        captured_messages = []
        original_strong_chat = ai.strong_chat

        async def spy_strong_chat(messages, tools=None):
            captured_messages.extend(messages)
            return await original_strong_chat(messages, tools)

        ai.strong_chat = spy_strong_chat

        await agent._process_chat("hi", [])

        system_msg = captured_messages[0]["content"]
        assert "CORRECTION LOG" not in system_msg
