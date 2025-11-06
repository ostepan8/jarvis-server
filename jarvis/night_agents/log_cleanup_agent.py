from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Set

from .base import NightAgent
from ..logging import JarvisLogger
from ..core.constants import LOG_DB_PATH
from ..agents.message import Message


class LogCleanupAgent(NightAgent):
    """Cleans old logs from the database periodically."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        db_path: str = LOG_DB_PATH,
        retention_days: int = 30,
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
        """
        super().__init__("LogCleanupAgent", logger)
        self.db_path = db_path
        self.retention_days = retention_days

    @property
    def description(self) -> str:
        return "Cleans old logs from the database"

    @property
    def capabilities(self) -> Set[str]:
        return {"clean_logs"}

    async def _handle_capability_request(self, message: Message) -> None:
        if message.content.get("capability") != "clean_logs":
            return
        result = await self._clean_logs()
        await self.send_capability_response(
            to_agent=message.from_agent,
            result=result,
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        return None

    async def start_background_tasks(self) -> None:
        """Start the periodic log cleanup task."""
        self._create_background_task(self._periodic_cleanup())

    async def _periodic_cleanup(self) -> None:
        """Periodically clean logs every 24 hours."""
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
