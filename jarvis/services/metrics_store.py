"""SQLite-backed time-series metrics store for device monitoring.

Stores raw metrics at full resolution (24h retention) and hourly rollups
(30-day retention). WAL mode for concurrent reads, thread-safe via RLock.
All data persisted locally in ~/.jarvis/device_metrics.db.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging import JarvisLogger

DB_DIR = Path.home() / ".jarvis"
DB_PATH = DB_DIR / "device_metrics.db"

_CREATE_METRICS = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    component   TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       REAL NOT NULL,
    unit        TEXT DEFAULT '',
    severity    TEXT DEFAULT 'ok',
    metadata    TEXT DEFAULT '{}'
);
"""

_CREATE_METRICS_IDX_COMPONENT = """
CREATE INDEX IF NOT EXISTS idx_metrics_component_time
ON metrics(component, timestamp);
"""

_CREATE_METRICS_IDX_NAME = """
CREATE INDEX IF NOT EXISTS idx_metrics_name_time
ON metrics(metric_name, timestamp);
"""

_CREATE_HOURLY = """
CREATE TABLE IF NOT EXISTS metrics_hourly (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hour         TEXT NOT NULL,
    component    TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    min_value    REAL,
    max_value    REAL,
    avg_value    REAL,
    sample_count INTEGER,
    UNIQUE(hour, component, metric_name)
);
"""


class MetricsStore:
    """Thread-safe SQLite store for device metrics with automatic rollup."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_METRICS)
        self._conn.execute(_CREATE_METRICS_IDX_COMPONENT)
        self._conn.execute(_CREATE_METRICS_IDX_NAME)
        self._conn.execute(_CREATE_HOURLY)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_batch(self, rows: List[Dict[str, Any]]) -> int:
        """Bulk-insert metric rows. Returns count inserted."""
        if not rows:
            return 0

        with self._lock:
            values = [
                (
                    row["timestamp"],
                    row["component"],
                    row["metric_name"],
                    row["value"],
                    row.get("unit", ""),
                    row.get("severity", "ok"),
                    json.dumps(row.get("metadata", {})),
                )
                for row in rows
            ]
            self._conn.executemany(
                """INSERT INTO metrics
                   (timestamp, component, metric_name, value, unit, severity, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            self._conn.commit()
            count = len(values)

        self.logger.log("DEBUG", "MetricsStore", f"Recorded {count} metric(s)")
        return count

    # ------------------------------------------------------------------
    # Read — raw
    # ------------------------------------------------------------------

    def query(
        self,
        component: str,
        metric_name: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query raw metrics with optional filters. Returns list of dicts."""
        sql = "SELECT * FROM metrics WHERE component = ?"
        params: List[Any] = [component]

        if metric_name is not None:
            sql += " AND metric_name = ?"
            params.append(metric_name)
        if start is not None:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end is not None:
            sql += " AND timestamp <= ?"
            params.append(end)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        return [self._row_to_dict(r) for r in rows]

    def query_latest(
        self,
        component: str,
        metric_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Most recent value for a component (optionally filtered by metric name)."""
        sql = "SELECT * FROM metrics WHERE component = ?"
        params: List[Any] = [component]

        if metric_name is not None:
            sql += " AND metric_name = ?"
            params.append(metric_name)

        sql += " ORDER BY timestamp DESC LIMIT 1"

        with self._lock:
            row = self._conn.execute(sql, params).fetchone()

        return self._row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Read — aggregated
    # ------------------------------------------------------------------

    def query_aggregated(
        self,
        component: str,
        metric_name: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return hourly rollup rows for the given component."""
        sql = "SELECT * FROM metrics_hourly WHERE component = ?"
        params: List[Any] = [component]

        if metric_name is not None:
            sql += " AND metric_name = ?"
            params.append(metric_name)
        if start is not None:
            sql += " AND hour >= ?"
            params.append(start)
        if end is not None:
            sql += " AND hour <= ?"
            params.append(end)

        sql += " ORDER BY hour DESC"

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        return [
            {
                "hour": r["hour"],
                "component": r["component"],
                "metric_name": r["metric_name"],
                "min_value": r["min_value"],
                "max_value": r["max_value"],
                "avg_value": r["avg_value"],
                "sample_count": r["sample_count"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def compact(self, retention_hours: int = 24) -> Dict[str, int]:
        """Aggregate raw metrics older than *retention_hours* into hourly
        rollups, then delete those raw rows.

        Returns ``{"aggregated": N, "deleted": M}``.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=retention_hours)
        ).isoformat()

        with self._lock:
            # Build hourly aggregates from raw rows older than the cutoff
            agg_rows = self._conn.execute(
                """SELECT
                       strftime('%%Y-%%m-%%dT%%H:00:00', timestamp) AS hour,
                       component,
                       metric_name,
                       MIN(value)   AS min_value,
                       MAX(value)   AS max_value,
                       AVG(value)   AS avg_value,
                       COUNT(*)     AS sample_count
                   FROM metrics
                   WHERE timestamp < ?
                   GROUP BY hour, component, metric_name""",
                (cutoff,),
            ).fetchall()

            aggregated = 0
            for row in agg_rows:
                self._conn.execute(
                    """INSERT INTO metrics_hourly
                       (hour, component, metric_name, min_value, max_value, avg_value, sample_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(hour, component, metric_name) DO UPDATE SET
                           min_value    = MIN(excluded.min_value, metrics_hourly.min_value),
                           max_value    = MAX(excluded.max_value, metrics_hourly.max_value),
                           avg_value    = (excluded.avg_value * excluded.sample_count
                                          + metrics_hourly.avg_value * metrics_hourly.sample_count)
                                         / (excluded.sample_count + metrics_hourly.sample_count),
                           sample_count = excluded.sample_count + metrics_hourly.sample_count
                    """,
                    (
                        row["hour"],
                        row["component"],
                        row["metric_name"],
                        row["min_value"],
                        row["max_value"],
                        row["avg_value"],
                        row["sample_count"],
                    ),
                )
                aggregated += 1

            # Delete the raw rows we just aggregated
            cursor = self._conn.execute(
                "DELETE FROM metrics WHERE timestamp < ?", (cutoff,)
            )
            deleted = cursor.rowcount
            self._conn.commit()

        self.logger.log(
            "INFO",
            "MetricsStore",
            f"Compact: {aggregated} rollup(s), {deleted} raw row(s) purged",
        )
        return {"aggregated": aggregated, "deleted": deleted}

    def cleanup(self, retention_days: int = 30) -> int:
        """Delete hourly rollup rows older than *retention_days*. Returns count deleted."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()

        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM metrics_hourly WHERE hour < ?", (cutoff,)
            )
            deleted = cursor.rowcount
            self._conn.commit()

        self.logger.log(
            "INFO",
            "MetricsStore",
            f"Cleanup: {deleted} hourly rollup(s) purged",
        )
        return deleted

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection. Safe to call multiple times."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a raw metrics Row to a plain dict, parsing metadata JSON."""
        metadata_raw = row["metadata"]
        try:
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "component": row["component"],
            "metric_name": row["metric_name"],
            "value": row["value"],
            "unit": row["unit"],
            "severity": row["severity"],
            "metadata": metadata,
        }
