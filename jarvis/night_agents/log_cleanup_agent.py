from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Set

from .base import NightAgent
from ..logging import JarvisLogger
from ..logging.trace_store import DEFAULT_TRACE_DB_PATH
from ..core.constants import LOG_DB_PATH
from ..agents.message import Message


class LogCleanupAgent(NightAgent):
    """Cleans old logs from the database periodically."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        db_path: str = LOG_DB_PATH,
        retention_days: int = 30,
        trace_db_path: str = DEFAULT_TRACE_DB_PATH,
    ) -> None:
        """Initialize the log cleanup agent.

        Parameters
        ----------
        logger:
            Logger instance for logging cleanup operations
        db_path:
            Path to the SQLite log database
        retention_days:
            Number of days to retain logs (default: 30). Logs older than this will be deleted.
        trace_db_path:
            Path to the SQLite trace database
        """
        super().__init__("LogCleanupAgent", logger)
        self.db_path = db_path
        self.retention_days = retention_days
        self.trace_db_path = trace_db_path

    @property
    def description(self) -> str:
        return "Cleans old logs from the database"

    @property
    def capabilities(self) -> Set[str]:
        return {"clean_logs", "clean_traces"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability == "clean_logs":
            result = await self._clean_logs()
        elif capability == "clean_traces":
            result = await self._clean_traces()
        else:
            return
        await self.send_capability_response(
            to_agent=message.from_agent,
            result=result,
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        return None

    async def start_background_tasks(self, progress_callback=None) -> None:
        """Start the periodic log cleanup task."""
        self._create_background_task(self._periodic_cleanup())

    async def _periodic_cleanup(self) -> None:
        """Periodically clean logs and traces every 24 hours."""
        while True:
            try:
                await self._clean_logs()
            except Exception as exc:
                if self.logger:
                    self.logger.log(
                        "ERROR",
                        "Log cleanup failed",
                        str(exc),
                    )
            try:
                await self._clean_traces()
            except Exception as exc:
                if self.logger:
                    self.logger.log(
                        "ERROR",
                        "Trace cleanup failed",
                        str(exc),
                    )
            # Wait 24 hours (86400 seconds) before next cleanup
            await asyncio.sleep(86400)

    async def _clean_logs(self) -> dict:
        """Clean logs older than retention_days from the database.

        Returns
        -------
        dict
            Summary of cleanup operation with deleted_count and total_before
        """
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            cutoff_str = cutoff_date.isoformat()

            # Count logs before cleanup
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            total_before = cursor.fetchone()[0]

            # Delete logs older than retention_days
            cursor = conn.execute(
                "DELETE FROM logs WHERE timestamp < ?",
                (cutoff_str,),
            )
            deleted_count = cursor.rowcount

            # Commit changes
            conn.commit()

            # Count logs after cleanup
            cursor = conn.execute("SELECT COUNT(*) FROM logs")
            total_after = cursor.fetchone()[0]

            # Vacuum to reclaim space (must be done before closing)
            conn.execute("VACUUM")
            conn.close()

            result = {
                "deleted_count": deleted_count,
                "total_before": total_before,
                "total_after": total_after,
                "retention_days": self.retention_days,
                "cutoff_date": cutoff_str,
            }

            if self.logger:
                self.logger.log(
                    "INFO",
                    f"Log cleanup completed: deleted {deleted_count} old entries",
                    f"Kept {total_after} logs (retention: {self.retention_days} days)",
                )

            return result

        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "ERROR",
                    "Log cleanup failed",
                    str(exc),
                )
            raise

    async def _clean_traces(self) -> dict:
        """Clean traces older than retention_days and orphaned spans.

        Returns
        -------
        dict
            Summary of cleanup operation with traces_deleted, spans_deleted,
            and total counts.
        """
        try:
            conn = sqlite3.connect(self.trace_db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            cutoff_str = cutoff_date.isoformat()

            # Count traces before cleanup
            cursor = conn.execute("SELECT COUNT(*) FROM traces")
            traces_before = cursor.fetchone()[0]

            # Delete old traces
            cursor = conn.execute(
                "DELETE FROM traces WHERE start_time < ?",
                (cutoff_str,),
            )
            traces_deleted = cursor.rowcount

            # Delete orphaned spans (trace_id no longer in traces)
            cursor = conn.execute(
                "DELETE FROM spans WHERE trace_id NOT IN (SELECT trace_id FROM traces)",
            )
            spans_deleted = cursor.rowcount

            conn.commit()

            # Count after cleanup
            cursor = conn.execute("SELECT COUNT(*) FROM traces")
            traces_after = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM spans")
            spans_after = cursor.fetchone()[0]

            conn.execute("VACUUM")
            conn.close()

            result = {
                "traces_deleted": traces_deleted,
                "spans_deleted": spans_deleted,
                "traces_before": traces_before,
                "traces_after": traces_after,
                "spans_after": spans_after,
                "retention_days": self.retention_days,
                "cutoff_date": cutoff_str,
            }

            if self.logger:
                self.logger.log(
                    "INFO",
                    f"Trace cleanup completed: deleted {traces_deleted} traces, {spans_deleted} orphaned spans",
                    f"Kept {traces_after} traces (retention: {self.retention_days} days)",
                )

            return result

        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "ERROR",
                    "Trace cleanup failed",
                    str(exc),
                )
            raise
