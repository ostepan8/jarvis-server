"""SQLite-backed todo/task management service.

Provides a Linear-style taskboard with statuses, priorities, tags, and
due dates. All data is persisted locally in ~/.jarvis/todos.db.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logging import JarvisLogger


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Ordering for priority comparisons (lower = more important)
PRIORITY_ORDER = {
    TaskPriority.URGENT: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.MEDIUM: 2,
    TaskPriority.LOW: 3,
}


@dataclass
class TodoItem:
    """Single task record."""

    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: List[str] = field(default_factory=list)
    due_date: Optional[str] = None  # ISO-8601 date string
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "tags": self.tags,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TodoItem:
        tags_raw = row["tags"]
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            tags=tags,
            due_date=row["due_date"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


DB_DIR = Path.home() / ".jarvis"
DB_PATH = DB_DIR / "todos.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS todos (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT DEFAULT 'todo',
    priority    TEXT DEFAULT 'medium',
    tags        TEXT DEFAULT '',
    due_date    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class TodoService:
    """CRUD service for todo items backed by SQLite."""

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
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        tags: Optional[List[str]] = None,
        due_date: Optional[str] = None,
    ) -> TodoItem:
        """Create a new task and return it."""
        now = datetime.now(timezone.utc).isoformat()
        item = TodoItem(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            status=TaskStatus.TODO,
            priority=TaskPriority(priority),
            tags=tags or [],
            due_date=due_date,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            """INSERT INTO todos (id, title, description, status, priority, tags, due_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.title,
                item.description,
                item.status.value,
                item.priority.value,
                ",".join(item.tags),
                item.due_date,
                item.created_at,
                item.updated_at,
            ),
        )
        self._conn.commit()
        self.logger.log("INFO", "Todo created", f"{item.id}: {item.title}")
        return item

    def get(self, todo_id: str) -> Optional[TodoItem]:
        """Fetch a single task by ID (or partial ID prefix)."""
        row = self._conn.execute(
            "SELECT * FROM todos WHERE id = ? OR id LIKE ?",
            (todo_id, f"{todo_id}%"),
        ).fetchone()
        return TodoItem.from_row(row) if row else None

    def list(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[TodoItem]:
        """List tasks with optional filters."""
        query = "SELECT * FROM todos WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if tag:
            query += " AND (',' || tags || ',') LIKE ?"
            params.append(f"%,{tag},%")
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [TodoItem.from_row(r) for r in rows]

    def update(self, todo_id: str, **fields: Any) -> Optional[TodoItem]:
        """Update fields on an existing task. Returns the updated item."""
        item = self.get(todo_id)
        if not item:
            return None

        allowed = {"title", "description", "status", "priority", "tags", "due_date"}
        updates: Dict[str, Any] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "tags" and isinstance(value, list):
                updates["tags"] = ",".join(value)
            elif key == "status":
                updates["status"] = TaskStatus(value).value
            elif key == "priority":
                updates["priority"] = TaskPriority(value).value
            else:
                updates[key] = value

        if not updates:
            return item

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item.id]
        self._conn.execute(
            f"UPDATE todos SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        self.logger.log("INFO", "Todo updated", f"{item.id}")
        return self.get(item.id)

    def delete(self, todo_id: str) -> bool:
        """Delete a task. Returns True if a row was removed."""
        item = self.get(todo_id)
        if not item:
            return False
        self._conn.execute("DELETE FROM todos WHERE id = ?", (item.id,))
        self._conn.commit()
        self.logger.log("INFO", "Todo deleted", f"{item.id}: {item.title}")
        return True

    def complete(self, todo_id: str) -> Optional[TodoItem]:
        """Shorthand: mark a task as done."""
        return self.update(todo_id, status="done")

    def start(self, todo_id: str) -> Optional[TodoItem]:
        """Shorthand: mark a task as in_progress."""
        return self.update(todo_id, status="in_progress")

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def counts_by_status(self) -> Dict[str, int]:
        """Return {status: count} for all statuses."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM todos GROUP BY status"
        ).fetchall()
        counts = {s.value: 0 for s in TaskStatus}
        for row in rows:
            counts[row["status"]] = row["cnt"]
        return counts

    def close(self) -> None:
        self._conn.close()
