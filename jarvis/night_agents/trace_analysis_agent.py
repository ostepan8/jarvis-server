"""Night agent that analyzes request traces for performance and reliability insights.

Runs periodically during night mode, queries the trace database for the
last 24 hours of activity, and produces a ``TraceAnalysisReport`` saved
as JSON under ``~/.jarvis/trace_reports/``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Set

from .base import NightAgent
from ..agents.message import Message
from ..agents.response import AgentResponse
from ..logging import JarvisLogger
from ..services.trace_analysis_service import TraceAnalysisService, TraceAnalysisReport


class TraceAnalysisNightAgent(NightAgent):
    """Analyzes request traces during night mode to surface performance and reliability issues."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        trace_db_path: str = "jarvis_traces.db",
        report_dir: Optional[str] = None,
        run_interval: int = 86400,
    ) -> None:
        super().__init__("TraceAnalysisAgent", logger)
        self._service = TraceAnalysisService(
            trace_db_path=trace_db_path, logger=logger
        )
        self._run_interval = run_interval
        self._report_dir = Path(
            report_dir or Path.home() / ".jarvis" / "trace_reports"
        )
        self._last_report: Optional[TraceAnalysisReport] = None

    @property
    def description(self) -> str:
        return "Analyzes request traces for performance patterns and error trends"

    @property
    def capabilities(self) -> Set[str]:
        return {"analyze_traces", "get_trace_report"}

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")

        if capability == "analyze_traces":
            report = await self._run_analysis()
            result = AgentResponse(
                success=True,
                response=report.to_summary_text(),
                data=report.to_dict(),
                metadata={"agent": self.name},
            )
        elif capability == "get_trace_report":
            report = self._load_latest_report()
            if report:
                result = AgentResponse(
                    success=True,
                    response=report.to_summary_text(),
                    data=report.to_dict(),
                    metadata={"agent": self.name},
                )
            else:
                result = AgentResponse(
                    success=True,
                    response="No trace analysis reports available yet.",
                    metadata={"agent": self.name},
                )
        else:
            result = AgentResponse(
                success=False,
                response=f"Unknown capability: {capability}",
                metadata={"agent": self.name},
            )

        await self.send_capability_response(
            to_agent=message.from_agent,
            result=result.to_dict(),
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        return None

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def start_background_tasks(self, progress_callback=None) -> None:
        """Start the periodic trace analysis cycle."""
        self._create_background_task(self._periodic_analysis())

    async def _periodic_analysis(self) -> None:
        """Run analysis, then sleep for run_interval. Repeat."""
        while True:
            try:
                await self._run_analysis()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.logger:
                    self.logger.log("ERROR", "Trace analysis failed", str(exc))
            await asyncio.sleep(self._run_interval)

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    async def _run_analysis(self) -> TraceAnalysisReport:
        """Execute one analysis pass and persist the report."""
        report = await self._service.analyze(lookback_hours=24)
        self._last_report = report
        self._save_report(report)
        if self.logger:
            self.logger.log(
                "INFO", "Trace analysis complete", report.to_summary_text()
            )
        return report

    # ------------------------------------------------------------------
    # Report persistence
    # ------------------------------------------------------------------

    def _save_report(self, report: TraceAnalysisReport) -> str:
        """Persist report as JSON. Returns the file path."""
        self._report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filepath = self._report_dir / f"{timestamp}.json"
        filepath.write_text(json.dumps(report.to_dict(), indent=2))
        return str(filepath)

    def _load_latest_report(self) -> Optional[TraceAnalysisReport]:
        """Load the most recent saved report, or return the cached one."""
        if self._last_report is not None:
            return self._last_report

        if not self._report_dir.exists():
            return None

        files = sorted(self._report_dir.glob("*.json"))
        if not files:
            return None

        try:
            data = json.loads(files[-1].read_text())
            return TraceAnalysisReport(
                lookback_hours=data.get("lookback_hours", 24),
                analyzed_at=data.get("analyzed_at", ""),
                total_traces=data.get("total_traces", 0),
                total_spans=data.get("total_spans", 0),
                total_errors=data.get("total_errors", 0),
                avg_trace_duration_ms=data.get("avg_trace_duration_ms", 0.0),
                p95_trace_duration_ms=data.get("p95_trace_duration_ms", 0.0),
                p99_trace_duration_ms=data.get("p99_trace_duration_ms", 0.0),
                slowest_traces=data.get("slowest_traces", []),
                error_traces=data.get("error_traces", []),
            )
        except (json.JSONDecodeError, KeyError):
            return None
