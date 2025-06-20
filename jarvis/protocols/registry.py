from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, List
import re

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
                    -- no trigger_phrases yet
                )
                """
            )
            # Backwards-compatible upgrade:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(protocols)")]
            if "arguments" not in cols:
                self.conn.execute("ALTER TABLE protocols ADD COLUMN arguments TEXT")
            if "trigger_phrases" not in cols:
                # <<< add this
                self.conn.execute(
                    "ALTER TABLE protocols ADD COLUMN trigger_phrases TEXT"
                )

    def load(self, directory: Path | None = None) -> None:
        self.protocols.clear()
        if directory is not None:
            directory = Path(directory)
            if not directory.exists():
                print(f"Directory {directory} does not exist")
                return

            for json_file in directory.glob("*.json"):
                try:
                    protocol = Protocol.from_file(json_file)
                    self.register(protocol)
                except Exception as e:
                    print(f"Failed to load protocol from {json_file}: {e}")
            return

        rows = self.conn.execute(
            # <<< include trigger_phrases in the SELECT
            "SELECT id, name, description, arguments, steps, trigger_phrases FROM protocols"
        ).fetchall()

        for row in rows:
            # parse steps & args exactly as before…
            steps = [ProtocolStep(**step) for step in json.loads(row["steps"] or "[]")]
            args_data = json.loads(row["arguments"] or "{}")

            # now parse triggers:
            triggers = json.loads(row["trigger_phrases"] or "[]")

            proto = Protocol(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                arguments=args_data,
                steps=steps,
                trigger_phrases=triggers,  # <<< new
            )
            self.protocols[proto.id] = proto
            print(f"Loaded protocol: {proto.id} – {proto.name}")

    def save(self) -> None:
        with self.conn:
            for proto in self.protocols.values():
                steps_json = json.dumps([s.__dict__ for s in proto.steps])
                args_json = json.dumps(proto.arguments)
                triggers_json = json.dumps(proto.trigger_phrases)  # <<< new
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO protocols
                      (id, name, description, arguments, steps, trigger_phrases)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proto.id,
                        proto.name,
                        proto.description,
                        args_json,
                        steps_json,
                        triggers_json,  # <<< new
                    ),
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
                return {"success": False, "reason": "Duplicate name"}

        for proto in self.protocols.values():
            if self.normalize_trigger_phrases(proto.trigger_phrases) == triggers_key:
                return {"success": False, "reason": "Duplicate trigger phrases"}

        self.protocols[protocol.id] = protocol
        self.save()
        return {"success": True, "id": protocol.id}

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Lowercase and remove punctuation for comparison."""
        text = text.lower().strip()
        text = re.sub(r"[\W_]+", " ", text)
        return " ".join(text.split())

    def find_matching_protocol(self, user_input: str) -> Optional[Protocol]:
        """Find a protocol whose trigger phrase exactly matches the given input."""
        normalized_input = self._normalize_text(user_input)
        print(f"Looking for protocol matching: '{normalized_input}'")

        for proto in self.protocols.values():
            print(f"Checking protocol {proto.id}: {proto.name}")
            for phrase in proto.trigger_phrases:
                norm_phrase = self._normalize_text(phrase)
                print(f"  Comparing with trigger: '{norm_phrase}'")
                if norm_phrase == normalized_input:
                    print(f"Found matching protocol: {proto.id}")
                    return proto

        print("No matching protocol found")
        return None

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
