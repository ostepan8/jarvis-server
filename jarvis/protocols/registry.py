from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, List

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
                    arguments TEXT,
                    steps TEXT
                )
                """
            )
            # Backwards compatible upgrade
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(protocols)").fetchall()]
            if "arguments" not in cols:
                self.conn.execute("ALTER TABLE protocols ADD COLUMN arguments TEXT")

    def load(self, directory: Path | None = None) -> None:
        """Load protocols from the database or a directory of JSON files."""
        self.protocols.clear()

        if directory is not None:
            directory = Path(directory)
            for file_path in directory.glob("*.json"):
                try:
                    proto = Protocol.from_file(file_path)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    print(f"Failed to load {file_path}: {e}")
                    continue
                self.register(proto)
            return

        rows = self.conn.execute(
            "SELECT id, name, description, arguments, steps FROM protocols"
        ).fetchall()
        for row in rows:
            try:
                steps_data = json.loads(row["steps"] or "[]")
            except Exception:
                steps_data = []
            steps = [ProtocolStep(**step) for step in steps_data]
            try:
                args_data = json.loads(row["arguments"] or "{}")
            except Exception:
                args_data = {}
            proto = Protocol(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                arguments=args_data,
                steps=steps,
            )
            self.protocols[proto.id] = proto

    def save(self) -> None:
        with self.conn:
            for proto in self.protocols.values():
                steps_json = json.dumps([s.__dict__ for s in proto.steps])
                args_json = json.dumps(proto.arguments)
                self.conn.execute(
                    "INSERT OR REPLACE INTO protocols (id, name, description, arguments, steps) VALUES (?, ?, ?, ?, ?)",
                    (proto.id, proto.name, proto.description, args_json, steps_json),
                )

    @staticmethod
    def normalize_trigger_phrases(phrases: List[str]) -> List[str]:
        """Normalize trigger phrases by trimming, lowercasing and sorting."""
        unique = {p.strip().lower() for p in phrases}
        return sorted(unique)

    def is_duplicate(self, protocol: Protocol) -> bool:
        """Check if protocol duplicates an existing one by name or triggers."""
        name_key = protocol.name.strip().lower()
        triggers_key = self.normalize_trigger_phrases(protocol.trigger_phrases)
        for proto in self.protocols.values():
            if proto.name.strip().lower() == name_key:
                return True
            if self.normalize_trigger_phrases(proto.trigger_phrases) == triggers_key:
                return True
        return False

    def register(self, protocol: Protocol) -> dict:
        """Register a protocol if not a duplicate."""
        name_key = protocol.name.strip().lower()
        triggers_key = self.normalize_trigger_phrases(protocol.trigger_phrases)

        for proto in self.protocols.values():
            if proto.name.strip().lower() == name_key:
                print(f"⚠️ Protocol '{protocol.name}' already exists. Skipping.")
                return {"success": False, "reason": "Duplicate name"}

        for proto in self.protocols.values():
            if self.normalize_trigger_phrases(proto.trigger_phrases) == triggers_key:
                print(f"⚠️ Protocol '{protocol.name}' already exists. Skipping.")
                return {"success": False, "reason": "Duplicate trigger phrases"}

        self.protocols[protocol.id] = protocol
        self.save()
        return {"success": True, "id": protocol.id}

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
