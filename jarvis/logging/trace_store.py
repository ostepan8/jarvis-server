"""SQLite persistence for traces and spans.

Thread-safe storage mirroring JarvisLogger patterns: WAL mode,
thread-local connections, reentrant lock.  Stored in a separate
database (``jarvis_traces.db``) so trace volume doesn't bloat the
main log file and can be rotated independently.
"""

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import fields as dc_fields
from typing import Any, Dict, List, Optional

DEFAULT_TRACE_DB_PATH = "jarvis_traces.db"


class TraceStore:
    def __init__(self, db_path: str = DEFAULT_TRACE_DB_PATH):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._local = threading.local()
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0,
            )
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    @contextmanager
    def _db_context(self):
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        with self._db_context() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    user_input TEXT,
                    user_id INTEGER,
                    source TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    duration_ms REAL,
                    status TEXT DEFAULT 'OK',
                    metadata TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    agent_name TEXT,
                    capability TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    duration_ms REAL,
                    status TEXT DEFAULT 'OK',
                    input_data TEXT,
                    output_data TEXT,
                    error TEXT,
                    attributes TEXT,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_parent ON spans(parent_span_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_agent ON spans(agent_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_capability ON spans(capability)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_start ON spans(start_time)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_status ON spans(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_traces_start ON traces(start_time)"
            )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_trace(self, trace) -> None:
        with self._db_context() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, user_input, user_id, source, start_time,
                    end_time, duration_ms, status, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace.trace_id,
                    trace.user_input,
                    trace.user_id,
                    trace.source,
                    trace.start_time,
                    trace.end_time,
                    trace.duration_ms,
                    trace.status,
                    trace.metadata,
                ),
            )

    def complete_trace(
        self,
        trace_id: str,
        end_time: str,
        duration_ms: float,
        status: str = "OK",
    ) -> None:
        with self._db_context() as conn:
            conn.execute(
                "UPDATE traces SET end_time=?, duration_ms=?, status=? WHERE trace_id=?",
                (end_time, duration_ms, status, trace_id),
            )

    def save_span(self, span) -> None:
        with self._db_context() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO spans
                   (span_id, trace_id, parent_span_id, name, kind, agent_name,
                    capability, start_time, end_time, duration_ms, status,
                    input_data, output_data, error, attributes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.name,
                    span.kind,
                    span.agent_name,
                    span.capability,
                    span.start_time,
                    span.end_time,
                    span.duration_ms,
                    span.status,
                    span.input_data,
                    span.output_data,
                    span.error,
                    span.attributes,
                ),
            )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._db_context() as conn:
            row = conn.execute(
                "SELECT * FROM traces WHERE trace_id=?", (trace_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_spans(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._db_context() as conn:
            rows = conn.execute(
                "SELECT * FROM spans WHERE trace_id=? ORDER BY start_time",
                (trace_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_traces(
        self,
        since: str = None,
        until: str = None,
        status: str = None,
        agent: str = None,
        capability: str = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = "SELECT DISTINCT t.* FROM traces t"
        params: list = []
        joins: list = []
        conditions: list = []

        if agent or capability:
            joins.append("JOIN spans s ON t.trace_id = s.trace_id")

        if since:
            conditions.append("t.start_time >= ?")
            params.append(since)
        if until:
            conditions.append("t.start_time <= ?")
            params.append(until)
        if status:
            conditions.append("t.status = ?")
            params.append(status)
        if agent:
            conditions.append("s.agent_name = ?")
            params.append(agent)
        if capability:
            conditions.append("s.capability = ?")
            params.append(capability)

        if joins:
            query += " " + " ".join(joins)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY t.start_time DESC LIMIT ?"
        params.append(limit)

        with self._db_context() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def search_spans(
        self,
        trace_id: str = None,
        agent_name: str = None,
        capability: str = None,
        kind: str = None,
        status: str = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM spans"
        conditions: list = []
        params: list = []

        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if agent_name:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if capability:
            conditions.append("capability = ?")
            params.append(capability)
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        with self._db_context() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            if hasattr(self._local, "connection") and self._local.connection:
                try:
                    self._local.connection.close()
                except Exception:
                    pass
                finally:
                    self._local.connection = None
