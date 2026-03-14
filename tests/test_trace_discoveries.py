"""Tests for SystemAnalyzer.analyze_traces — trace-based discovery engine.

Covers:
- High error rate detection
- Slow agent detection
- Missing DB (graceful fallback)
- Clean data (no issues surfaced)
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from jarvis.services.system_analyzer import (
    Discovery,
    DiscoveryType,
    SystemAnalyzer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_trace_db(
    path: str,
    traces: list[tuple] | None = None,
    spans: list[tuple] | None = None,
):
    """Create a trace DB with seed data.

    traces: (trace_id, start_time, status)
    spans:  (span_id, trace_id, agent_name, start_time, status, duration_ms)
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


def _recent_iso(hours_ago: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


# ===========================================================================
# High error rate
# ===========================================================================


class TestTraceErrorRate:
    @pytest.mark.asyncio
    async def test_detects_high_error_rate_agent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            # 4 errors out of 5 spans = 80% error rate
            traces = [(f"t{i}", ts, "OK") for i in range(5)]
            spans = [
                (f"s{i}", f"t{i}", "BadAgent", ts, "ERROR" if i < 4 else "OK", 100.0)
                for i in range(5)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            assert len(discoveries) == 1
            d = discoveries[0]
            assert d.discovery_type == DiscoveryType.TRACE_ERROR_RATE
            assert "BadAgent" in d.title
            assert "80%" in d.title
            assert d.priority == "high"  # >50%
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_medium_priority_for_moderate_error_rate(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            # 2 errors out of 5 = 40% (above 20% threshold, but below 50%)
            traces = [(f"t{i}", ts, "OK") for i in range(5)]
            spans = [
                (f"s{i}", f"t{i}", "WobblyAgent", ts, "ERROR" if i < 2 else "OK", 100.0)
                for i in range(5)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            assert len(discoveries) == 1
            assert discoveries[0].priority == "medium"
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ignores_agents_below_threshold(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            # 1 error out of 5 = 20% — exactly at boundary, should not trigger (> not >=)
            traces = [(f"t{i}", ts, "OK") for i in range(5)]
            spans = [
                (f"s{i}", f"t{i}", "OkAgent", ts, "ERROR" if i == 0 else "OK", 100.0)
                for i in range(5)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            error_discoveries = [
                d for d in discoveries
                if d.discovery_type == DiscoveryType.TRACE_ERROR_RATE
            ]
            assert len(error_discoveries) == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ignores_agents_with_few_spans(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            # 3 out of 4 errors but only 4 spans — below HAVING total >= 5
            traces = [(f"t{i}", ts, "OK") for i in range(4)]
            spans = [
                (f"s{i}", f"t{i}", "SmallAgent", ts, "ERROR" if i < 3 else "OK", 100.0)
                for i in range(4)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            error_discoveries = [
                d for d in discoveries
                if d.discovery_type == DiscoveryType.TRACE_ERROR_RATE
            ]
            assert len(error_discoveries) == 0
        finally:
            os.unlink(db_path)


# ===========================================================================
# Slow agents
# ===========================================================================


class TestTraceSlowAgent:
    @pytest.mark.asyncio
    async def test_detects_slow_agent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            traces = [(f"t{i}", ts, "OK") for i in range(3)]
            # avg duration = 6000ms (> 5000ms threshold)
            spans = [
                (f"s{i}", f"t{i}", "SlowAgent", ts, "OK", 6000.0)
                for i in range(3)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            slow_discoveries = [
                d for d in discoveries
                if d.discovery_type == DiscoveryType.TRACE_SLOW_AGENT
            ]
            assert len(slow_discoveries) == 1
            assert "SlowAgent" in slow_discoveries[0].title
            assert "6000" in slow_discoveries[0].title
            assert slow_discoveries[0].priority == "medium"
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ignores_fast_agents(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            traces = [(f"t{i}", ts, "OK") for i in range(5)]
            # avg = 100ms — well under threshold
            spans = [
                (f"s{i}", f"t{i}", "FastAgent", ts, "OK", 100.0)
                for i in range(5)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            slow_discoveries = [
                d for d in discoveries
                if d.discovery_type == DiscoveryType.TRACE_SLOW_AGENT
            ]
            assert len(slow_discoveries) == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_ignores_slow_agents_with_too_few_spans(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            traces = [(f"t{i}", ts, "OK") for i in range(2)]
            # Only 2 spans — below HAVING total >= 3
            spans = [
                (f"s{i}", f"t{i}", "SlowButRare", ts, "OK", 10000.0)
                for i in range(2)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            slow_discoveries = [
                d for d in discoveries
                if d.discovery_type == DiscoveryType.TRACE_SLOW_AGENT
            ]
            assert len(slow_discoveries) == 0
        finally:
            os.unlink(db_path)


# ===========================================================================
# Missing DB / clean data
# ===========================================================================


class TestTraceEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_db_returns_empty(self):
        analyzer = SystemAnalyzer(
            project_root="/tmp",
            log_db_path="/tmp/fake.db",
            trace_db_path="/nonexistent/path/traces.db",
        )
        discoveries = await analyzer.analyze_traces(lookback_hours=24)
        assert discoveries == []

    @pytest.mark.asyncio
    async def test_clean_data_returns_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            # All OK, all fast, plenty of spans
            traces = [(f"t{i}", ts, "OK") for i in range(10)]
            spans = [
                (f"s{i}", f"t{i}", "GoodAgent", ts, "OK", 200.0)
                for i in range(10)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            assert len(discoveries) == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_trace_db(db_path)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            assert len(discoveries) == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_both_error_and_slow_detected_simultaneously(self):
        """An agent can be both error-prone and slow."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            ts = _recent_iso(1)
            traces = [(f"t{i}", ts, "OK") for i in range(5)]
            # 3 errors out of 5 = 60%, avg duration = 7000ms
            spans = [
                (f"s{i}", f"t{i}", "TroubledAgent", ts, "ERROR" if i < 3 else "OK", 7000.0)
                for i in range(5)
            ]
            _create_trace_db(db_path, traces=traces, spans=spans)

            analyzer = SystemAnalyzer(
                project_root="/tmp",
                log_db_path="/tmp/fake.db",
                trace_db_path=db_path,
            )
            discoveries = await analyzer.analyze_traces(lookback_hours=24)

            types = {d.discovery_type for d in discoveries}
            assert DiscoveryType.TRACE_ERROR_RATE in types
            assert DiscoveryType.TRACE_SLOW_AGENT in types
        finally:
            os.unlink(db_path)
