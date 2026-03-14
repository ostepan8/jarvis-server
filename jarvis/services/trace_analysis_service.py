"""Trace analysis service for night-mode performance reporting.

Queries the TraceStore database to produce analytics on request
performance, error trends, agent bottlenecks, and capability hotspots.
All SQLite work runs synchronously and is dispatched via
``asyncio.to_thread`` to keep the event loop unblocked.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional

from ..logging import JarvisLogger
from ..logging.trace_store import DEFAULT_TRACE_DB_PATH


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class AgentPerformance:
    """Per-agent span statistics."""

    agent_name: str
    span_count: int
    avg_duration_ms: float
    max_duration_ms: float
    error_count: int
    error_rate: float  # 0.0-1.0

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "span_count": self.span_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
        }


@dataclass
class CapabilityStats:
    """Per-capability call statistics."""

    capability: str
    call_count: int
    avg_duration_ms: float
    max_duration_ms: float
    error_count: int

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "call_count": self.call_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "error_count": self.error_count,
        }


@dataclass
class TraceAnalysisReport:
    """Complete analysis report for a lookback window."""

    lookback_hours: int
    analyzed_at: str  # ISO timestamp
    total_traces: int
    total_spans: int
    total_errors: int
    avg_trace_duration_ms: float
    p95_trace_duration_ms: float
    p99_trace_duration_ms: float
    slowest_traces: list[dict] = field(default_factory=list)
    error_traces: list[dict] = field(default_factory=list)
    agent_performance: list[AgentPerformance] = field(default_factory=list)
    capability_stats: list[CapabilityStats] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lookback_hours": self.lookback_hours,
            "analyzed_at": self.analyzed_at,
            "total_traces": self.total_traces,
            "total_spans": self.total_spans,
            "total_errors": self.total_errors,
            "avg_trace_duration_ms": round(self.avg_trace_duration_ms, 2),
            "p95_trace_duration_ms": round(self.p95_trace_duration_ms, 2),
            "p99_trace_duration_ms": round(self.p99_trace_duration_ms, 2),
            "slowest_traces": self.slowest_traces,
            "error_traces": self.error_traces,
            "agent_performance": [a.to_dict() for a in self.agent_performance],
            "capability_stats": [c.to_dict() for c in self.capability_stats],
        }

    def to_summary_text(self) -> str:
        """Human-readable summary suitable for logging or morning reports."""
        lines = [
            f"Trace analysis ({self.lookback_hours}h lookback):",
            f"  Traces: {self.total_traces}, Spans: {self.total_spans}, Errors: {self.total_errors}",
        ]
        if self.total_traces > 0:
            lines.append(
                f"  Duration avg={self.avg_trace_duration_ms:.1f}ms "
                f"p95={self.p95_trace_duration_ms:.1f}ms "
                f"p99={self.p99_trace_duration_ms:.1f}ms"
            )
        if self.slowest_traces:
            lines.append("  Slowest traces:")
            for t in self.slowest_traces[:3]:
                lines.append(
                    f"    {t['trace_id'][:12]}... {t['duration_ms']:.0f}ms "
                    f"({t.get('user_input', 'N/A')[:40]})"
                )
        if self.agent_performance:
            lines.append("  Agent bottlenecks:")
            for a in sorted(
                self.agent_performance, key=lambda x: x.avg_duration_ms, reverse=True
            )[:3]:
                lines.append(
                    f"    {a.agent_name}: avg={a.avg_duration_ms:.1f}ms "
                    f"errors={a.error_count} ({a.error_rate:.1%})"
                )
        return "\n".join(lines)


# ------------------------------------------------------------------
# Service
# ------------------------------------------------------------------


class TraceAnalysisService:
    """Analyzes trace data for performance patterns, error trends, and bottlenecks."""

    def __init__(
        self,
        trace_db_path: str = DEFAULT_TRACE_DB_PATH,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self._db_path = trace_db_path
        self._logger = logger

    async def analyze(self, lookback_hours: int = 24) -> TraceAnalysisReport:
        """Run full analysis on recent traces.

        Delegates to a thread so the event loop stays responsive.
        """
        return await asyncio.to_thread(self._analyze_sync, lookback_hours)

    # ------------------------------------------------------------------
    # Synchronous analysis — runs in a worker thread
    # ------------------------------------------------------------------

    def _analyze_sync(self, lookback_hours: int) -> TraceAnalysisReport:
        """Synchronous analysis against the trace database."""
        cutoff = (datetime.now(UTC) - timedelta(hours=lookback_hours)).isoformat()

        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        try:
            summary = self._gather_summary(conn, cutoff)
            slowest = self._gather_slowest_traces(conn, cutoff)
            errors = self._gather_error_traces(conn, cutoff)
            agents = self._gather_agent_performance(conn, cutoff)
            capabilities = self._gather_capability_stats(conn, cutoff)
        finally:
            conn.close()

        return TraceAnalysisReport(
            lookback_hours=lookback_hours,
            analyzed_at=datetime.now(UTC).isoformat(),
            total_traces=summary["total_traces"],
            total_spans=summary["total_spans"],
            total_errors=summary["error_count"],
            avg_trace_duration_ms=summary["avg_duration"],
            p95_trace_duration_ms=summary["p95_duration"],
            p99_trace_duration_ms=summary["p99_duration"],
            slowest_traces=slowest,
            error_traces=errors,
            agent_performance=agents,
            capability_stats=capabilities,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _gather_summary(conn: sqlite3.Connection, cutoff: str) -> dict:
        """Total traces, total spans, error count, avg/p95/p99 duration."""
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END), 0) AS errors
            FROM traces
            WHERE start_time >= ?
            """,
            (cutoff,),
        ).fetchone()

        total_traces = row["total"]
        error_count = row["errors"]

        span_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM spans
            WHERE start_time >= ?
            """,
            (cutoff,),
        ).fetchone()
        total_spans = span_row["total"]

        # Fetch durations for percentile calculations
        durations_rows = conn.execute(
            """
            SELECT duration_ms
            FROM traces
            WHERE start_time >= ? AND duration_ms IS NOT NULL
            ORDER BY duration_ms
            """,
            (cutoff,),
        ).fetchall()

        durations = [r["duration_ms"] for r in durations_rows]

        if durations:
            avg_duration = sum(durations) / len(durations)
            p95_duration = _percentile(durations, 0.95)
            p99_duration = _percentile(durations, 0.99)
        else:
            avg_duration = 0.0
            p95_duration = 0.0
            p99_duration = 0.0

        return {
            "total_traces": total_traces,
            "total_spans": total_spans,
            "error_count": error_count,
            "avg_duration": avg_duration,
            "p95_duration": p95_duration,
            "p99_duration": p99_duration,
        }

    @staticmethod
    def _gather_slowest_traces(conn: sqlite3.Connection, cutoff: str) -> list[dict]:
        """Top 5 slowest traces by duration_ms."""
        rows = conn.execute(
            """
            SELECT trace_id, user_input, duration_ms, status
            FROM traces
            WHERE start_time >= ? AND duration_ms IS NOT NULL
            ORDER BY duration_ms DESC
            LIMIT 5
            """,
            (cutoff,),
        ).fetchall()

        return [
            {
                "trace_id": r["trace_id"],
                "user_input": r["user_input"],
                "duration_ms": r["duration_ms"],
                "status": r["status"],
            }
            for r in rows
        ]

    @staticmethod
    def _gather_error_traces(conn: sqlite3.Connection, cutoff: str) -> list[dict]:
        """Traces with ERROR status and their error spans."""
        trace_rows = conn.execute(
            """
            SELECT trace_id, user_input, duration_ms
            FROM traces
            WHERE start_time >= ? AND status = 'ERROR'
            ORDER BY start_time DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()

        results = []
        for tr in trace_rows:
            error_spans = conn.execute(
                """
                SELECT name, agent_name, error
                FROM spans
                WHERE trace_id = ? AND status = 'ERROR'
                """,
                (tr["trace_id"],),
            ).fetchall()

            results.append(
                {
                    "trace_id": tr["trace_id"],
                    "user_input": tr["user_input"],
                    "duration_ms": tr["duration_ms"],
                    "error_spans": [
                        {
                            "name": s["name"],
                            "agent_name": s["agent_name"],
                            "error": s["error"],
                        }
                        for s in error_spans
                    ],
                }
            )

        return results

    @staticmethod
    def _gather_agent_performance(
        conn: sqlite3.Connection, cutoff: str
    ) -> list[AgentPerformance]:
        """Per-agent span count, avg duration, error rate."""
        rows = conn.execute(
            """
            SELECT
                agent_name,
                COUNT(*) AS span_count,
                AVG(duration_ms) AS avg_dur,
                MAX(duration_ms) AS max_dur,
                SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS err_count
            FROM spans
            WHERE start_time >= ? AND agent_name IS NOT NULL
            GROUP BY agent_name
            ORDER BY avg_dur DESC
            """,
            (cutoff,),
        ).fetchall()

        return [
            AgentPerformance(
                agent_name=r["agent_name"],
                span_count=r["span_count"],
                avg_duration_ms=r["avg_dur"] or 0.0,
                max_duration_ms=r["max_dur"] or 0.0,
                error_count=r["err_count"],
                error_rate=(r["err_count"] / r["span_count"]) if r["span_count"] else 0.0,
            )
            for r in rows
        ]

    @staticmethod
    def _gather_capability_stats(
        conn: sqlite3.Connection, cutoff: str
    ) -> list[CapabilityStats]:
        """Per-capability avg duration, call count."""
        rows = conn.execute(
            """
            SELECT
                capability,
                COUNT(*) AS call_count,
                AVG(duration_ms) AS avg_dur,
                MAX(duration_ms) AS max_dur,
                SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS err_count
            FROM spans
            WHERE start_time >= ? AND capability IS NOT NULL
            GROUP BY capability
            ORDER BY avg_dur DESC
            """,
            (cutoff,),
        ).fetchall()

        return [
            CapabilityStats(
                capability=r["capability"],
                call_count=r["call_count"],
                avg_duration_ms=r["avg_dur"] or 0.0,
                max_duration_ms=r["max_dur"] or 0.0,
                error_count=r["err_count"],
            )
            for r in rows
        ]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile from a pre-sorted list.

    Uses nearest-rank method — no numpy required.
    """
    if not sorted_values:
        return 0.0
    k = max(0, int(len(sorted_values) * p) - 1)
    return sorted_values[k]
