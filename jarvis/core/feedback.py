"""Feedback collection and correction storage for self-healing responses.

When a user says "bad!" (or similar), the system captures the previous
interaction and stores it as a correction record.  These corrections are
injected into future agent prompts so the system avoids repeating the
same mistakes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


FEEDBACK_TRIGGERS: set[str] = {
    "bad!",
    "bad",
    "wrong",
    "terrible",
    "awful",
    "no!",
    "that's wrong",
    "incorrect",
}

# Normalised for matching — built once at import time
_NORMALISED_TRIGGERS: set[str] = {t.lower().strip() for t in FEEDBACK_TRIGGERS}


class FeedbackCollector:
    """Detects negative feedback, logs corrections, and serves them back."""

    def __init__(self, feedback_dir: Optional[str] = None) -> None:
        self.feedback_dir = Path(feedback_dir) if feedback_dir else Path.home() / ".jarvis" / "feedback"
        self.corrections_file = self.feedback_dir / "corrections.jsonl"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    @staticmethod
    def is_negative_feedback(text: str) -> bool:
        """Return True if *text* matches a known negative-feedback trigger."""
        return text.lower().strip() in _NORMALISED_TRIGGERS

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    def log_correction(
        self,
        user_id: int,
        original_input: str,
        bad_response: str,
        feedback_text: str,
        intent: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> str:
        """Append a correction record and return its ID."""
        correction_id = str(uuid.uuid4())
        record = {
            "id": correction_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "original_input": original_input,
            "bad_response": bad_response,
            "feedback_text": feedback_text,
            "intent": intent,
            "capability": capability,
            "resolved": False,
        }
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        with open(self.corrections_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return correction_id

    def get_corrections(
        self,
        limit: int = 20,
        user_id: Optional[int] = None,
    ) -> List[dict]:
        """Return the most recent corrections, optionally filtered by user."""
        if not self.corrections_file.exists():
            return []

        records: list[dict] = []
        with open(self.corrections_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("resolved"):
                    continue
                if user_id is not None and record.get("user_id") != user_id:
                    continue
                records.append(record)

        # Return the most recent *limit* entries
        return records[-limit:]

    def mark_resolved(self, correction_id: str) -> bool:
        """Mark a correction as resolved by rewriting the file."""
        if not self.corrections_file.exists():
            return False

        lines: list[str] = []
        found = False
        with open(self.corrections_file, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    lines.append(stripped)
                    continue
                if record.get("id") == correction_id:
                    record["resolved"] = True
                    found = True
                lines.append(json.dumps(record))

        if found:
            with open(self.corrections_file, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        return found
