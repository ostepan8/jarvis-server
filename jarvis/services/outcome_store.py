"""SQLite-backed outcome history for night agent fix attempts.

Records every fix attempt with its result, enabling the intelligence
layer to learn from past successes and failures. WAL mode for
concurrent reads, thread-safe via RLock.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..logging import JarvisLogger

DB_DIR = Path.home() / ".jarvis"
DB_PATH = DB_DIR / "outcome_store.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS fix_attempts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL,
    discovery_type   TEXT NOT NULL,
    title            TEXT NOT NULL,
    file_pattern     TEXT DEFAULT '',
    diff_summary     TEXT DEFAULT '',
    success          INTEGER NOT NULL,
    error_message    TEXT DEFAULT '',
    triage_notes     TEXT DEFAULT '',
    confidence_score INTEGER DEFAULT 5,
    duration_seconds REAL DEFAULT 0.0
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_fix_type_time ON fix_attempts(discovery_type, timestamp);
"""


@dataclass
class FixAttempt:
    timestamp: str
    discovery_type: str
    title: str
    file_pattern: str          # comma-joined relevant files
    diff_summary: str          # first 2000 chars of diff
    success: bool
    error_message: str = ""
    triage_notes: str = ""     # JSON: triage reasoning + approach
    confidence_score: int = 5  # 1-10
    duration_seconds: float = 0.0
    id: int | None = None


class OutcomeStore:
    """Thread-safe SQLite store for fix attempt outcomes."""

    def __init__(self, db_path: str | None = None, logger: JarvisLogger | None = None) -> None:
        self.logger = logger or JarvisLogger()
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()

    def record(self, attempt: FixAttempt) -> int:
        """Record a fix attempt. Returns the row ID."""
        with self._lock:
            cursor = self._conn.execute(
                """INSERT INTO fix_attempts
                   (timestamp, discovery_type, title, file_pattern, diff_summary,
                    success, error_message, triage_notes, confidence_score, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.timestamp,
                    attempt.discovery_type,
                    attempt.title,
                    attempt.file_pattern,
                    attempt.diff_summary[:2000],  # cap diff summary
                    int(attempt.success),
                    attempt.error_message,
                    attempt.triage_notes,
                    attempt.confidence_score,
                    attempt.duration_seconds,
                ),
            )
            self._conn.commit()
            row_id = cursor.lastrowid
        self.logger.log("DEBUG", "OutcomeStore", f"Recorded attempt #{row_id}: {attempt.title}")
        return row_id

    def query_similar(self, discovery_type: str, file_patterns: list[str], limit: int = 5) -> list[FixAttempt]:
        """Find past attempts with matching type and overlapping file patterns."""
        with self._lock:
            if not file_patterns:
                rows = self._conn.execute(
                    "SELECT * FROM fix_attempts WHERE discovery_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (discovery_type, limit),
                ).fetchall()
            else:
                like_clauses = " OR ".join("file_pattern LIKE ?" for _ in file_patterns)
                sql = f"SELECT * FROM fix_attempts WHERE discovery_type = ? AND ({like_clauses}) ORDER BY timestamp DESC LIMIT ?"
                params = [discovery_type] + [f"%{fp}%" for fp in file_patterns] + [limit]
                rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    def success_rate(self, discovery_type: str, lookback_days: int = 30) -> float:
        """Return success rate (0.0 - 1.0) for a discovery type over lookback window. Returns 0.0 if no data."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        with self._lock:
            row = self._conn.execute(
                """SELECT COUNT(*) as total, SUM(success) as wins
                   FROM fix_attempts
                   WHERE discovery_type = ? AND timestamp >= ?""",
                (discovery_type, cutoff),
            ).fetchone()
        total = row["total"] if row else 0
        if total == 0:
            return 0.0
        wins = row["wins"] or 0
        return wins / total

    def recent_failures(self, n: int = 10) -> list[FixAttempt]:
        """Return the N most recent failed attempts."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fix_attempts WHERE success = 0 ORDER BY timestamp DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    def close(self) -> None:
        """Close the database connection. Safe to call multiple times."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    @staticmethod
    def _row_to_attempt(row: sqlite3.Row) -> FixAttempt:
        return FixAttempt(
            id=row["id"],
            timestamp=row["timestamp"],
            discovery_type=row["discovery_type"],
            title=row["title"],
            file_pattern=row["file_pattern"],
            diff_summary=row["diff_summary"],
            success=bool(row["success"]),
            error_message=row["error_message"],
            triage_notes=row["triage_notes"],
            confidence_score=row["confidence_score"],
            duration_seconds=row["duration_seconds"],
        )
