"""SQLite-backed scheduled task service.

Manages recurring and one-shot scheduled tasks that fire prompts into the
orchestrator. Supports cron expressions, fixed intervals, and single-fire
schedules. All timestamps stored in UTC; timezone field used only for
cron local-time computation.

Persistence lives at ~/.jarvis/schedules.db.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from croniter import croniter

from ..logging import JarvisLogger

# Module-level UTC reference so methods whose ``timezone`` parameter shadows
# the stdlib import can still reach UTC without gymnastics.
_UTC = timezone.utc


class ScheduleType(str, Enum):
    ONCE = "once"          # Fire once, then disable
    CRON = "cron"          # 5-field cron expression (minute hour dom month dow)
    INTERVAL = "interval"  # Every N seconds


@dataclass
class ScheduleItem:
    """Single scheduled task record."""

    id: str                            # 8-char uuid prefix
    name: str
    schedule_type: ScheduleType
    cron_expression: Optional[str]
    interval_seconds: Optional[int]
    next_run: str                      # ISO-8601 UTC
    last_run: Optional[str]
    request_text: str                  # Prompt sent to orchestrator when fired
    timezone: str                      # For cron computation (e.g., "America/New_York")
    user_id: int
    source_agent: Optional[str]        # Which agent created it (None = user)
    enabled: bool
    created_at: str
    updated_at: str
    created_by: str                    # "user" or agent name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule_type": self.schedule_type.value,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "request_text": self.request_text,
            "timezone": self.timezone,
            "user_id": self.user_id,
            "source_agent": self.source_agent,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ScheduleItem:
        return cls(
            id=row["id"],
            name=row["name"],
            schedule_type=ScheduleType(row["schedule_type"]),
            cron_expression=row["cron_expression"],
            interval_seconds=row["interval_seconds"],
            next_run=row["next_run"],
            last_run=row["last_run"],
            request_text=row["request_text"],
            timezone=row["timezone"],
            user_id=row["user_id"],
            source_agent=row["source_agent"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"],
        )


DB_DIR = Path.home() / ".jarvis"
DB_PATH = DB_DIR / "schedules.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schedules (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    schedule_type     TEXT NOT NULL,
    cron_expression   TEXT,
    interval_seconds  INTEGER,
    next_run          TEXT NOT NULL,
    last_run          TEXT,
    request_text      TEXT NOT NULL,
    timezone          TEXT NOT NULL DEFAULT 'UTC',
    user_id           INTEGER NOT NULL,
    source_agent      TEXT,
    enabled           INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL DEFAULT 'user'
);
"""

_CREATE_WAKE_ROUTINE_TABLE = """
CREATE TABLE IF NOT EXISTS wake_routine (
    id           INTEGER PRIMARY KEY DEFAULT 1,
    routine_text TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""

_DEFAULT_WAKE_ROUTINE = (
    "Turn on the lights and tell me about my first calendar event today."
)


def _compute_next_cron_run(cron_expression: str, tz_name: str) -> str:
    """Compute the next cron run time and return as ISO-8601 UTC string."""
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    cron = croniter(cron_expression, now_local)
    next_local = cron.get_next(datetime)
    next_utc = next_local.astimezone(_UTC)
    return next_utc.isoformat()


class SchedulerService:
    """CRUD service for scheduled tasks backed by SQLite."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_WAKE_ROUTINE_TABLE)
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        schedule_type: str,
        request_text: str,
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[int] = None,
        run_at: Optional[str] = None,
        timezone: str = "UTC",
        user_id: int = 0,
        source_agent: Optional[str] = None,
        created_by: str = "user",
    ) -> ScheduleItem:
        """Create a new scheduled task and return it."""
        now = datetime.now(tz=_UTC).isoformat()
        stype = ScheduleType(schedule_type)

        if stype == ScheduleType.ONCE:
            if not run_at:
                raise ValueError("run_at is required for ONCE schedule type")
            next_run = run_at
        elif stype == ScheduleType.CRON:
            if not cron_expression:
                raise ValueError("cron_expression is required for CRON schedule type")
            next_run = _compute_next_cron_run(cron_expression, timezone)
        elif stype == ScheduleType.INTERVAL:
            if not interval_seconds:
                raise ValueError("interval_seconds is required for INTERVAL schedule type")
            next_run = (
                datetime.now(tz=_UTC) + timedelta(seconds=interval_seconds)
            ).isoformat()
        else:
            raise ValueError(f"Unknown schedule type: {schedule_type}")

        item = ScheduleItem(
            id=str(uuid.uuid4())[:8],
            name=name,
            schedule_type=stype,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            next_run=next_run,
            last_run=None,
            request_text=request_text,
            timezone=timezone,
            user_id=user_id,
            source_agent=source_agent,
            enabled=True,
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )
        self._conn.execute(
            """INSERT INTO schedules
               (id, name, schedule_type, cron_expression, interval_seconds,
                next_run, last_run, request_text, timezone, user_id,
                source_agent, enabled, created_at, updated_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.name,
                item.schedule_type.value,
                item.cron_expression,
                item.interval_seconds,
                item.next_run,
                item.last_run,
                item.request_text,
                item.timezone,
                item.user_id,
                item.source_agent,
                int(item.enabled),
                item.created_at,
                item.updated_at,
                item.created_by,
            ),
        )
        self._conn.commit()
        self.logger.log("INFO", "Schedule created", f"{item.id}: {item.name}")
        return item

    def get(self, schedule_id: str) -> Optional[ScheduleItem]:
        """Fetch a single schedule by ID (or partial ID prefix)."""
        row = self._conn.execute(
            "SELECT * FROM schedules WHERE id = ? OR id LIKE ?",
            (schedule_id, f"{schedule_id}%"),
        ).fetchone()
        return ScheduleItem.from_row(row) if row else None

    def list(
        self,
        enabled: Optional[bool] = None,
        schedule_type: Optional[str] = None,
        source_agent: Optional[str] = None,
    ) -> List[ScheduleItem]:
        """List schedules with optional filters."""
        query = "SELECT * FROM schedules WHERE 1=1"
        params: List[Any] = []
        if enabled is not None:
            query += " AND enabled = ?"
            params.append(int(enabled))
        if schedule_type:
            query += " AND schedule_type = ?"
            params.append(schedule_type)
        if source_agent:
            query += " AND source_agent = ?"
            params.append(source_agent)
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [ScheduleItem.from_row(r) for r in rows]

    def update(self, schedule_id: str, **fields: Any) -> Optional[ScheduleItem]:
        """Update fields on an existing schedule. Returns the updated item."""
        item = self.get(schedule_id)
        if not item:
            return None

        allowed = {
            "name", "schedule_type", "cron_expression", "interval_seconds",
            "next_run", "request_text", "timezone", "source_agent", "enabled",
        }
        updates: Dict[str, Any] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "schedule_type":
                updates["schedule_type"] = ScheduleType(value).value
            elif key == "enabled":
                updates["enabled"] = int(bool(value))
            else:
                updates[key] = value

        if not updates:
            return item

        updates["updated_at"] = datetime.now(tz=_UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item.id]
        self._conn.execute(
            f"UPDATE schedules SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        self.logger.log("INFO", "Schedule updated", f"{item.id}")
        return self.get(item.id)

    def delete(self, schedule_id: str) -> bool:
        """Delete a schedule. Returns True if a row was removed."""
        item = self.get(schedule_id)
        if not item:
            return False
        self._conn.execute("DELETE FROM schedules WHERE id = ?", (item.id,))
        self._conn.commit()
        self.logger.log("INFO", "Schedule deleted", f"{item.id}: {item.name}")
        return True

    def enable(self, schedule_id: str) -> Optional[ScheduleItem]:
        """Enable a schedule."""
        return self.update(schedule_id, enabled=True)

    def disable(self, schedule_id: str) -> Optional[ScheduleItem]:
        """Disable a schedule."""
        return self.update(schedule_id, enabled=False)

    # ------------------------------------------------------------------
    # Scheduling logic
    # ------------------------------------------------------------------

    def get_due_schedules(self) -> List[ScheduleItem]:
        """Return all enabled schedules whose next_run is at or before now UTC."""
        now = datetime.now(tz=_UTC).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM schedules WHERE enabled = 1 AND next_run <= ?",
            (now,),
        ).fetchall()
        return [ScheduleItem.from_row(r) for r in rows]

    def mark_fired(self, schedule_id: str) -> Optional[ScheduleItem]:
        """Record that a schedule has fired and compute the next run time.

        - ONCE: disables the schedule.
        - CRON: computes next run from cron_expression + timezone.
        - INTERVAL: next_run = now + interval_seconds.
        Always sets last_run to now.
        """
        item = self.get(schedule_id)
        if not item:
            return None

        now = datetime.now(tz=_UTC)
        now_iso = now.isoformat()

        if item.schedule_type == ScheduleType.ONCE:
            self._conn.execute(
                "UPDATE schedules SET enabled = 0, last_run = ?, updated_at = ? WHERE id = ?",
                (now_iso, now_iso, item.id),
            )
        elif item.schedule_type == ScheduleType.CRON and item.cron_expression:
            next_run = _compute_next_cron_run(item.cron_expression, item.timezone)
            self._conn.execute(
                "UPDATE schedules SET next_run = ?, last_run = ?, updated_at = ? WHERE id = ?",
                (next_run, now_iso, now_iso, item.id),
            )
        elif item.schedule_type == ScheduleType.INTERVAL and item.interval_seconds:
            next_run = (now + timedelta(seconds=item.interval_seconds)).isoformat()
            self._conn.execute(
                "UPDATE schedules SET next_run = ?, last_run = ?, updated_at = ? WHERE id = ?",
                (next_run, now_iso, now_iso, item.id),
            )

        self._conn.commit()
        self.logger.log("INFO", "Schedule fired", f"{item.id}: {item.name}")
        return self.get(item.id)

    # ------------------------------------------------------------------
    # Wake routine
    # ------------------------------------------------------------------

    def get_wake_routine(self) -> str:
        """Return the current wake routine text, or the default if none set."""
        row = self._conn.execute(
            "SELECT routine_text FROM wake_routine WHERE id = 1"
        ).fetchone()
        return row["routine_text"] if row else _DEFAULT_WAKE_ROUTINE

    def set_wake_routine(self, routine_text: str) -> str:
        """Store a new wake routine text. Returns the saved text."""
        now = datetime.now(tz=_UTC).isoformat()
        self._conn.execute(
            """INSERT INTO wake_routine (id, routine_text, updated_at)
               VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET routine_text = ?, updated_at = ?""",
            (routine_text, now, routine_text, now),
        )
        self._conn.commit()
        self.logger.log("INFO", "Wake routine updated", routine_text[:80])
        return routine_text

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
