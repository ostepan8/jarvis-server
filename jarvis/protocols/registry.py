from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

from . import Protocol, ProtocolStep


class ProtocolRegistry:
    """Stores and retrieves Protocol definitions using SQLite."""

    def __init__(self, db_path: str = "protocols.db") -> None:
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_table()
        self.protocols: Dict[str, Protocol] = {}
        self.load()

    def _ensure_table(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS protocols (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    steps TEXT
                )
                """
            )

    def load(self) -> None:
        self.protocols.clear()
        rows = self.conn.execute(
            "SELECT id, name, description, steps FROM protocols"
        ).fetchall()
        for row in rows:
            try:
                steps_data = json.loads(row["steps"] or "[]")
            except Exception:
                steps_data = []
            steps = [ProtocolStep(**step) for step in steps_data]
            proto = Protocol(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                steps=steps,
            )
            self.protocols[proto.id] = proto

    def save(self) -> None:
        with self.conn:
            for proto in self.protocols.values():
                steps_json = json.dumps([s.__dict__ for s in proto.steps])
                self.conn.execute(
                    "INSERT OR REPLACE INTO protocols (id, name, description, steps) VALUES (?, ?, ?, ?)",
                    (proto.id, proto.name, proto.description, steps_json),
                )

    def register(self, protocol: Protocol) -> None:
        self.protocols[protocol.id] = protocol
        self.save()

    def get(self, identifier: str) -> Optional[Protocol]:
        if identifier in self.protocols:
            return self.protocols[identifier]
        for proto in self.protocols.values():
            if proto.name == identifier:
                return proto
        return None

    def list_ids(self) -> Iterable[str]:
        return list(self.protocols.keys())

    def close(self) -> None:
        if self.conn:
            self.conn.close()
