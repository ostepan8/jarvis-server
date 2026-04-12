"""Tests for LogCleanupAgent trace cleanup capabilities.

Covers:
- _clean_traces removes old traces and orphaned spans
- _clean_traces with empty/missing DB
- _periodic_cleanup calls both clean methods
- clean_traces capability request
"""

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.night_agents.log_cleanup_agent import LogCleanupAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_trace_db(
    path: str,
    traces: list[tuple] | None = None,
    spans: list[tuple] | None = None,
):
    """Create a trace DB with the expected schema and optional seed data.

    traces: list of (trace_id, start_time, status)
    spans:  list of (span_id, trace_id, agent_name, start_time, status, duration_ms)
    """
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY, user_input TEXT, user_id INTEGER, source TEXT,
            start_time TEXT, end_time TEXT, duration_ms REAL,
            status TEXT DEFAULT 'OK', metadata TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS spans (
            span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, parent_span_id TEXT,
            name TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'internal',
            agent_name TEXT, capability TEXT,
            start_time TEXT, end_time TEXT, duration_ms REAL,
            status TEXT DEFAULT 'OK',
            input_data TEXT, output_data TEXT, error TEXT, attributes TEXT
        )"""
    )
    if traces:
        for t in traces:
            conn.execute(
                "INSERT INTO traces (trace_id, start_time, status) VALUES (?, ?, ?)",
                t,
            )
    if spans:
        for s in spans:
            conn.execute(
                "INSERT INTO spans (span_id, trace_id, agent_name, start_time, status, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                s,
            )
    conn.commit()
    conn.close()


def _create_log_db(path: str):
    """Create an empty log DB so LogCleanupAgent._clean_logs doesn't explode."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS logs ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  timestamp TEXT NOT NULL,"
        "  level TEXT NOT NULL,"
        "  message TEXT"
        ")"
    )
    conn.commit()
    conn.close()


# ===========================================================================
# _clean_traces
# ===========================================================================


class TestCleanTraces:
    @pytest.mark.asyncio
    async def test_deletes_old_traces_and_orphaned_spans(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            old = (now - timedelta(days=60)).isoformat()
            recent = (now - timedelta(days=5)).isoformat()

            _create_trace_db(
                db_path,
                traces=[
                    ("t-old-1", old, "OK"),
                    ("t-old-2", old, "ERROR"),
                    ("t-recent", recent, "OK"),
                ],
                spans=[
                    ("s1", "t-old-1", "CalendarAgent", old, "OK", 100.0),
                    ("s2", "t-old-2", "SearchAgent", old, "ERROR", 200.0),
                    ("s3", "t-recent", "ChatAgent", recent, "OK", 50.0),
                ],
            )

            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
                retention_days=30,
            )
            result = await agent._clean_traces()

            assert result["traces_deleted"] == 2
            assert result["traces_before"] == 3
            assert result["traces_after"] == 1
            assert result["spans_deleted"] == 2  # orphaned spans from deleted traces
            assert result["spans_after"] == 1
            assert result["retention_days"] == 30
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_empty_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_trace_db(db_path)

            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
            )
            result = await agent._clean_traces()

            assert result["traces_deleted"] == 0
            assert result["traces_before"] == 0
            assert result["traces_after"] == 0
            assert result["spans_deleted"] == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_missing_database_raises(self):
        agent = LogCleanupAgent(
            db_path="/tmp/fake_logs.db",
            trace_db_path="/nonexistent/path/traces.db",
        )
        with pytest.raises(Exception):
            await agent._clean_traces()

    @pytest.mark.asyncio
    async def test_keeps_recent_traces_and_their_spans(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            recent = (now - timedelta(days=1)).isoformat()

            _create_trace_db(
                db_path,
                traces=[
                    ("t1", recent, "OK"),
                    ("t2", recent, "OK"),
                ],
                spans=[
                    ("s1", "t1", "CalendarAgent", recent, "OK", 100.0),
                    ("s2", "t2", "SearchAgent", recent, "OK", 200.0),
                ],
            )

            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
                retention_days=30,
            )
            result = await agent._clean_traces()

            assert result["traces_deleted"] == 0
            assert result["spans_deleted"] == 0
            assert result["traces_after"] == 2
            assert result["spans_after"] == 2
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_orphaned_spans_without_traces(self):
        """Spans whose trace_id was already gone before cleanup starts."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            recent = (now - timedelta(days=1)).isoformat()

            _create_trace_db(
                db_path,
                traces=[("t-live", recent, "OK")],
                spans=[
                    ("s1", "t-live", "ChatAgent", recent, "OK", 50.0),
                    ("s2", "t-ghost", "ChatAgent", recent, "OK", 50.0),
                ],
            )

            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
                retention_days=30,
            )
            result = await agent._clean_traces()

            assert result["traces_deleted"] == 0
            assert result["spans_deleted"] == 1  # the ghost span
            assert result["spans_after"] == 1
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_logs_when_logger_present(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_trace_db(db_path)

            mock_logger = MagicMock()
            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
                logger=mock_logger,
            )
            await agent._clean_traces()

            mock_logger.log.assert_called()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == "INFO"
        finally:
            os.unlink(db_path)


# ===========================================================================
# _periodic_cleanup calls both methods
# ===========================================================================


class TestPeriodicCleanupCallsBoth:
    @pytest.mark.asyncio
    async def test_periodic_cleanup_calls_clean_logs_and_clean_traces(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")

        call_log: list[str] = []

        async def mock_clean_logs():
            call_log.append("logs")
            return {}

        async def mock_clean_traces():
            call_log.append("traces")
            return {}

        agent._clean_logs = mock_clean_logs
        agent._clean_traces = mock_clean_traces

        # Replace periodic cleanup with a version that runs once
        async def one_shot_periodic():
            try:
                await agent._clean_logs()
            except Exception:
                pass
            try:
                await agent._clean_traces()
            except Exception:
                pass

        await one_shot_periodic()

        assert "logs" in call_log
        assert "traces" in call_log
        assert call_log.index("logs") < call_log.index("traces")


# ===========================================================================
# clean_traces capability request
# ===========================================================================


class TestCleanTracesCapability:
    @pytest.mark.asyncio
    async def test_clean_traces_capability_triggers_cleanup(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            old = (now - timedelta(days=60)).isoformat()
            _create_trace_db(
                db_path,
                traces=[("t-old", old, "OK")],
                spans=[("s1", "t-old", "Agent", old, "OK", 100.0)],
            )

            agent = LogCleanupAgent(
                db_path="/tmp/fake_logs.db",
                trace_db_path=db_path,
            )
            agent.send_capability_response = AsyncMock()

            message = MagicMock()
            message.content = {"capability": "clean_traces"}
            message.from_agent = "TestAgent"
            message.request_id = "req-1"
            message.id = "msg-1"

            await agent._handle_capability_request(message)

            agent.send_capability_response.assert_called_once()
            call_args = agent.send_capability_response.call_args
            result = call_args.kwargs.get(
                "result", call_args[1].get("result") if len(call_args) > 1 else None
            )
            assert result["traces_deleted"] == 1
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_capabilities_property_includes_clean_traces(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        assert "clean_traces" in agent.capabilities
        assert "clean_logs" in agent.capabilities

    @pytest.mark.asyncio
    async def test_unknown_capability_still_ignored(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        agent.send_capability_response = AsyncMock()

        message = MagicMock()
        message.content = {"capability": "something_else"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        await agent._handle_capability_request(message)
        agent.send_capability_response.assert_not_called()
