from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, List
import re
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

from ..logger import JarvisLogger
from .models import Protocol, ProtocolStep, ProtocolResponse


class ProtocolRegistry:
    """Stores and retrieves Protocol definitions using SQLite."""

    def __init__(
        self, db_path: str = "protocols.db", logger: JarvisLogger | None = None
    ) -> None:
        self.db_path = Path(db_path)
        self.logger = logger or JarvisLogger()
        self.conn: sqlite3.Connection = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_table()
        self.protocols: Dict[str, Protocol] = {}
        self.load()

    def _ensure_table(self) -> None:
        """Ensure the SQLite table for protocols exists.

        Columns:
            id                   TEXT PRIMARY KEY
            name                 TEXT
            description          TEXT
            arguments            TEXT  -- JSON mapping of argument definitions
            steps                TEXT  -- JSON list of ProtocolStep definitions
            trigger_phrases      TEXT  -- JSON list of phrases that activate the protocol
            argument_definitions TEXT  -- JSON list of ArgumentDefinition objects
            response             TEXT  -- JSON ProtocolResponse definition
        """

        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS protocols (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    arguments TEXT,
                    steps TEXT,
                    trigger_phrases TEXT,
                    argument_definitions TEXT,
                    response TEXT
                )
                """
            )
            # Backwards-compatible upgrade:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(protocols)")]
            if "arguments" not in cols:
                self.conn.execute("ALTER TABLE protocols ADD COLUMN arguments TEXT")
            if "trigger_phrases" not in cols:
                self.conn.execute(
                    "ALTER TABLE protocols ADD COLUMN trigger_phrases TEXT"
                )
            if "argument_definitions" not in cols:  # NEW
                self.conn.execute(
                    "ALTER TABLE protocols ADD COLUMN argument_definitions TEXT"
                )
            if "response" not in cols:
                self.conn.execute("ALTER TABLE protocols ADD COLUMN response TEXT")

    def load(self, directory: Path | None = None) -> None:
        from .models import ArgumentDefinition  # Import here to avoid circular imports

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
            "SELECT id, name, description, arguments, steps, trigger_phrases, argument_definitions, response FROM protocols"
        ).fetchall()

        for row in rows:
            # parse steps & args exactly as before…
            steps = [ProtocolStep(**step) for step in json.loads(row["steps"] or "[]")]
            args_data = json.loads(row["arguments"] or "{}")
            triggers = json.loads(row["trigger_phrases"] or "[]")

            # NEW: parse argument definitions
            arg_defs_data = json.loads(row["argument_definitions"] or "[]")
            arg_defs = [ArgumentDefinition.from_dict(ad) for ad in arg_defs_data]
            resp_data = json.loads(row["response"] or "null")
            response = ProtocolResponse.from_dict(resp_data) if resp_data else None

            proto = Protocol(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                arguments=args_data,
                steps=steps,
                trigger_phrases=triggers,
                argument_definitions=arg_defs,  # NEW
                response=response,
            )
            self.protocols[proto.id] = proto
            self.logger.log(
                "DEBUG",
                "Protocol loaded",
                f"{proto.id} - {proto.name}",
            )

    def save(self) -> None:
        with self.conn:
            for proto in self.protocols.values():
                steps_json = json.dumps([s.__dict__ for s in proto.steps])
                args_json = json.dumps(proto.arguments)
                triggers_json = json.dumps(proto.trigger_phrases)
                arg_defs_json = json.dumps(
                    [ad.to_dict() for ad in proto.argument_definitions]
                )  # NEW

                response_json = (
                    json.dumps(proto.response.to_dict()) if proto.response else "null"
                )

                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO protocols
                    (id, name, description, arguments, steps, trigger_phrases, argument_definitions, response)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proto.id,
                        proto.name,
                        proto.description,
                        args_json,
                        steps_json,
                        triggers_json,
                        arg_defs_json,  # NEW
                        response_json,
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

    def find_matching_protocol(
        self,
        user_input: str,
        *,
        timeout: float | None = None,
    ) -> Optional[Protocol]:
        """Find the first protocol whose trigger phrase matches the input.

        The check for each protocol is executed concurrently using a
        :class:`~concurrent.futures.ThreadPoolExecutor`. This speeds up
        matching when many protocols are registered.

        Args:
            user_input: Raw text from the user.
            timeout: Optional maximum number of seconds to wait for all
                checks to finish. Remaining tasks will be cancelled on timeout.

        Returns:
            ``Protocol`` if a match is found, otherwise ``None``.
        """

        normalized_input = self._normalize_text(user_input)
        self.logger.log("DEBUG", "Looking for protocol matching", normalized_input)

        def check_protocol(proto: Protocol) -> Optional[Protocol]:
            """Return the protocol if any trigger matches the input."""
            self.logger.log("DEBUG", "Checking protocol", f"{proto.id}: {proto.name}")
            for phrase in proto.trigger_phrases:
                norm_phrase = self._normalize_text(phrase)
                self.logger.log("DEBUG", "Comparing with trigger", norm_phrase)
                if norm_phrase == normalized_input:
                    self.logger.log("DEBUG", "Found matching protocol", proto.id)
                    return proto
            return None

        with ThreadPoolExecutor(max_workers=len(self.protocols) or 1) as executor:
            futures = [
                executor.submit(check_protocol, p) for p in self.protocols.values()
            ]

            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                proto = future.result()
                if proto:
                    # Cancel remaining checks as soon as a match is found
                    for f in futures:
                        if f is not future:
                            f.cancel()
                    return proto

            for f in futures:
                f.cancel()

        self.logger.log("DEBUG", "No matching protocol found")
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
