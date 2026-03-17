"""Tests for TraceAnalysisService and TraceAnalysisNightAgent.

Covers analytics calculations (avg, p95, p99), agent performance
aggregation, capability stats, error detection, empty-DB edge case,
agent capabilities, and report save/load.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jarvis.logging.trace_store import TraceStore
from jarvis.logging.tracer import Trace, Span, SpanKind
from jarvis.services.trace_analysis_service import (
    TraceAnalysisService,
    TraceAnalysisReport,
    AgentPerformance,
    CapabilityStats,
    _percentile,
)
from jarvis.night_agents.trace_analysis_agent import TraceAnalysisNightAgent


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def trace_db(tmp_path):
    """Create a fresh TraceStore backed by a temp DB."""
    store = TraceStore(db_path=str(tmp_path / "test_traces.db"))
    yield store
    store.close()


@pytest.fixture
def db_path(trace_db):
    """Return the path string for the temp DB."""
    return trace_db.db_path


@pytest.fixture
def populated_db(trace_db, db_path):
    """Populate the DB with realistic test data and return the path.

    Timestamps are relative to *now* so they always fall within the
    48-hour lookback window used by the tests.
    """
    _utc = timezone.utc
    base = datetime.now(_utc) - timedelta(hours=2)

    def _ts(hour_offset: int, ms_offset: int = 0) -> str:
        dt = base + timedelta(hours=hour_offset, milliseconds=ms_offset)
        return dt.isoformat()

    # Trace 1: fast, OK
    trace_db.save_trace(
        Trace(
            trace_id="t-fast-1",
            user_input="turn on lights",
            start_time=_ts(0),
            end_time=_ts(0, 100),
            duration_ms=100.0,
            status="OK",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-fast-1a",
            trace_id="t-fast-1",
            name="agent.toggle_lights",
            kind=SpanKind.AGENT.value,
            agent_name="LightingAgent",
            capability="toggle_lights",
            start_time=_ts(0),
            end_time=_ts(0, 80),
            duration_ms=80.0,
            status="OK",
        )
    )

    # Trace 2: medium, OK
    trace_db.save_trace(
        Trace(
            trace_id="t-med-1",
            user_input="what is the weather",
            start_time=_ts(1),
            end_time=_ts(1, 500),
            duration_ms=500.0,
            status="OK",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-med-1a",
            trace_id="t-med-1",
            name="agent.search",
            kind=SpanKind.AGENT.value,
            agent_name="SearchAgent",
            capability="search",
            start_time=_ts(1),
            end_time=_ts(1, 400),
            duration_ms=400.0,
            status="OK",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-med-1b",
            trace_id="t-med-1",
            name="llm.classify",
            kind=SpanKind.LLM.value,
            agent_name="NLUAgent",
            start_time=_ts(1),
            end_time=_ts(1, 50),
            duration_ms=50.0,
            status="OK",
        )
    )

    # Trace 3: slow, OK
    trace_db.save_trace(
        Trace(
            trace_id="t-slow-1",
            user_input="search for python tutorials",
            start_time=_ts(2),
            end_time=_ts(2, 2000),
            duration_ms=2000.0,
            status="OK",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-slow-1a",
            trace_id="t-slow-1",
            name="agent.search",
            kind=SpanKind.AGENT.value,
            agent_name="SearchAgent",
            capability="search",
            start_time=_ts(2),
            end_time=_ts(2, 1800),
            duration_ms=1800.0,
            status="OK",
        )
    )

    # Trace 4: error trace
    trace_db.save_trace(
        Trace(
            trace_id="t-err-1",
            user_input="create meeting tomorrow",
            start_time=_ts(3),
            end_time=_ts(3, 1000),
            duration_ms=1000.0,
            status="ERROR",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-err-1a",
            trace_id="t-err-1",
            name="agent.create_event",
            kind=SpanKind.AGENT.value,
            agent_name="CalendarAgent",
            capability="create_event",
            start_time=_ts(3),
            end_time=_ts(3, 900),
            duration_ms=900.0,
            status="ERROR",
            error="CalendarAPIError: upstream timeout",
        )
    )

    # Trace 5: another error, different agent
    trace_db.save_trace(
        Trace(
            trace_id="t-err-2",
            user_input="play netflix",
            start_time=_ts(4),
            end_time=_ts(4, 300),
            duration_ms=300.0,
            status="ERROR",
        )
    )
    trace_db.save_span(
        Span(
            span_id="s-err-2a",
            trace_id="t-err-2",
            name="agent.play_app",
            kind=SpanKind.AGENT.value,
            agent_name="RokuAgent",
            capability="play_app",
            start_time=_ts(4),
            end_time=_ts(4, 250),
            duration_ms=250.0,
            status="ERROR",
            error="ConnectionError: device unreachable",
        )
    )

    return db_path


# ------------------------------------------------------------------
# Percentile helper
# ------------------------------------------------------------------


class TestPercentile:
    def test_empty_list_returns_zero(self):
        assert _percentile([], 0.95) == 0.0

    def test_single_element(self):
        assert _percentile([42.0], 0.95) == 42.0

    def test_p95_of_sorted_list(self):
        values = list(range(1, 101))  # 1..100
        result = _percentile(values, 0.95)
        assert result == 95

    def test_p99_of_sorted_list(self):
        values = list(range(1, 101))
        result = _percentile(values, 0.99)
        assert result == 99


# ------------------------------------------------------------------
# TraceAnalysisService
# ------------------------------------------------------------------


class TestTraceAnalysisService:
    @pytest.mark.asyncio
    async def test_analyze_populated_db(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        assert isinstance(report, TraceAnalysisReport)
        assert report.total_traces == 5
        assert report.total_spans == 6
        assert report.total_errors == 2

    @pytest.mark.asyncio
    async def test_avg_duration(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        # durations: 100, 300, 500, 1000, 2000 -> avg = 780
        expected_avg = (100 + 300 + 500 + 1000 + 2000) / 5
        assert abs(report.avg_trace_duration_ms - expected_avg) < 0.1

    @pytest.mark.asyncio
    async def test_p95_p99_durations(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        # sorted durations: [100, 300, 500, 1000, 2000]
        # p95: index = int(5 * 0.95) - 1 = 3 -> 1000
        # p99: index = int(5 * 0.99) - 1 = 3 -> 1000
        assert report.p95_trace_duration_ms == 1000.0
        assert report.p99_trace_duration_ms == 1000.0

    @pytest.mark.asyncio
    async def test_slowest_traces(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        assert len(report.slowest_traces) == 5
        # First should be the slowest
        assert report.slowest_traces[0]["trace_id"] == "t-slow-1"
        assert report.slowest_traces[0]["duration_ms"] == 2000.0

    @pytest.mark.asyncio
    async def test_error_traces(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        assert len(report.error_traces) == 2
        trace_ids = {t["trace_id"] for t in report.error_traces}
        assert "t-err-1" in trace_ids
        assert "t-err-2" in trace_ids

        # Check error spans are included
        err1 = next(t for t in report.error_traces if t["trace_id"] == "t-err-1")
        assert len(err1["error_spans"]) == 1
        assert "upstream timeout" in err1["error_spans"][0]["error"]

    @pytest.mark.asyncio
    async def test_agent_performance(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        agent_names = {a.agent_name for a in report.agent_performance}
        assert "LightingAgent" in agent_names
        assert "SearchAgent" in agent_names
        assert "CalendarAgent" in agent_names
        assert "RokuAgent" in agent_names

        calendar = next(
            a for a in report.agent_performance if a.agent_name == "CalendarAgent"
        )
        assert calendar.span_count == 1
        assert calendar.error_count == 1
        assert calendar.error_rate == 1.0

        lighting = next(
            a for a in report.agent_performance if a.agent_name == "LightingAgent"
        )
        assert lighting.error_count == 0
        assert lighting.error_rate == 0.0

    @pytest.mark.asyncio
    async def test_capability_stats(self, populated_db):
        service = TraceAnalysisService(trace_db_path=populated_db)
        report = await service.analyze(lookback_hours=48)

        cap_names = {c.capability for c in report.capability_stats}
        assert "toggle_lights" in cap_names
        assert "search" in cap_names
        assert "create_event" in cap_names
        assert "play_app" in cap_names

        search = next(
            c for c in report.capability_stats if c.capability == "search"
        )
        assert search.call_count == 2
        assert search.avg_duration_ms == 1100.0

    @pytest.mark.asyncio
    async def test_empty_database(self, db_path):
        service = TraceAnalysisService(trace_db_path=db_path)
        report = await service.analyze(lookback_hours=24)

        assert report.total_traces == 0
        assert report.total_spans == 0
        assert report.total_errors == 0
        assert report.avg_trace_duration_ms == 0.0
        assert report.p95_trace_duration_ms == 0.0
        assert report.p99_trace_duration_ms == 0.0
        assert report.slowest_traces == []
        assert report.error_traces == []
        assert report.agent_performance == []
        assert report.capability_stats == []


# ------------------------------------------------------------------
# TraceAnalysisReport serialization
# ------------------------------------------------------------------


class TestTraceAnalysisReport:
    def test_to_dict_round_trip(self):
        report = TraceAnalysisReport(
            lookback_hours=24,
            analyzed_at="2026-03-14T06:00:00+00:00",
            total_traces=10,
            total_spans=25,
            total_errors=2,
            avg_trace_duration_ms=350.123,
            p95_trace_duration_ms=900.0,
            p99_trace_duration_ms=1200.0,
            agent_performance=[
                AgentPerformance(
                    agent_name="TestAgent",
                    span_count=5,
                    avg_duration_ms=200.0,
                    max_duration_ms=500.0,
                    error_count=1,
                    error_rate=0.2,
                )
            ],
            capability_stats=[
                CapabilityStats(
                    capability="test_cap",
                    call_count=3,
                    avg_duration_ms=150.0,
                    max_duration_ms=300.0,
                    error_count=0,
                )
            ],
        )

        d = report.to_dict()
        assert d["total_traces"] == 10
        assert d["avg_trace_duration_ms"] == 350.12
        assert len(d["agent_performance"]) == 1
        assert d["agent_performance"][0]["agent_name"] == "TestAgent"
        assert len(d["capability_stats"]) == 1

        # Ensure JSON-serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["total_spans"] == 25

    def test_to_summary_text_nonempty(self):
        report = TraceAnalysisReport(
            lookback_hours=24,
            analyzed_at="2026-03-14T06:00:00+00:00",
            total_traces=5,
            total_spans=10,
            total_errors=1,
            avg_trace_duration_ms=500.0,
            p95_trace_duration_ms=1000.0,
            p99_trace_duration_ms=1500.0,
            slowest_traces=[
                {
                    "trace_id": "abc123def456",
                    "user_input": "hello world",
                    "duration_ms": 2000.0,
                    "status": "OK",
                }
            ],
            agent_performance=[
                AgentPerformance(
                    agent_name="SlowAgent",
                    span_count=3,
                    avg_duration_ms=800.0,
                    max_duration_ms=1200.0,
                    error_count=1,
                    error_rate=0.333,
                )
            ],
        )

        text = report.to_summary_text()
        assert "24h lookback" in text
        assert "Traces: 5" in text
        assert "Errors: 1" in text
        assert "avg=500.0ms" in text
        assert "p95=1000.0ms" in text
        assert "SlowAgent" in text

    def test_to_summary_text_empty(self):
        report = TraceAnalysisReport(
            lookback_hours=24,
            analyzed_at="2026-03-14T06:00:00+00:00",
            total_traces=0,
            total_spans=0,
            total_errors=0,
            avg_trace_duration_ms=0.0,
            p95_trace_duration_ms=0.0,
            p99_trace_duration_ms=0.0,
        )
        text = report.to_summary_text()
        assert "Traces: 0" in text


# ------------------------------------------------------------------
# TraceAnalysisNightAgent
# ------------------------------------------------------------------


class TestTraceAnalysisNightAgent:
    def test_agent_properties(self):
        agent = TraceAnalysisNightAgent()
        assert agent.name == "TraceAnalysisAgent"
        assert "analyze_traces" in agent.capabilities
        assert "get_trace_report" in agent.capabilities
        assert "performance" in agent.description.lower() or "traces" in agent.description.lower()

    @pytest.mark.asyncio
    async def test_analyze_traces_capability(self, populated_db, tmp_path):
        agent = TraceAnalysisNightAgent(
            trace_db_path=populated_db,
            report_dir=str(tmp_path / "reports"),
        )

        report = await agent._run_analysis()

        assert isinstance(report, TraceAnalysisReport)
        assert report.total_traces == 5
        assert report.total_errors == 2
        assert agent._last_report is report

    @pytest.mark.asyncio
    async def test_report_saved_to_disk(self, populated_db, tmp_path):
        report_dir = tmp_path / "reports"
        agent = TraceAnalysisNightAgent(
            trace_db_path=populated_db,
            report_dir=str(report_dir),
        )

        await agent._run_analysis()

        files = list(report_dir.glob("*.json"))
        assert len(files) == 1

        data = json.loads(files[0].read_text())
        assert data["total_traces"] == 5
        assert data["total_errors"] == 2

    @pytest.mark.asyncio
    async def test_load_latest_report_from_cache(self, populated_db, tmp_path):
        agent = TraceAnalysisNightAgent(
            trace_db_path=populated_db,
            report_dir=str(tmp_path / "reports"),
        )

        await agent._run_analysis()
        loaded = agent._load_latest_report()
        assert loaded is not None
        # Should return the cached version (same object)
        assert loaded is agent._last_report

    @pytest.mark.asyncio
    async def test_load_latest_report_from_disk(self, populated_db, tmp_path):
        report_dir = tmp_path / "reports"
        agent = TraceAnalysisNightAgent(
            trace_db_path=populated_db,
            report_dir=str(report_dir),
        )

        await agent._run_analysis()
        # Clear cache to force disk read
        agent._last_report = None

        loaded = agent._load_latest_report()
        assert loaded is not None
        assert loaded.total_traces == 5

    @pytest.mark.asyncio
    async def test_load_latest_report_no_reports(self, tmp_path):
        agent = TraceAnalysisNightAgent(
            report_dir=str(tmp_path / "empty_reports"),
        )
        assert agent._load_latest_report() is None

    @pytest.mark.asyncio
    async def test_empty_db_produces_zero_report(self, db_path, tmp_path):
        agent = TraceAnalysisNightAgent(
            trace_db_path=db_path,
            report_dir=str(tmp_path / "reports"),
        )

        report = await agent._run_analysis()
        assert report.total_traces == 0
        assert report.total_spans == 0
        assert report.avg_trace_duration_ms == 0.0
