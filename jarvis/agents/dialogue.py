"""Data structures for agent-to-agent dialogue sessions.

A dialogue is a multi-turn conversation between a lead (initiator) agent
and a specialist (responder) agent.  Each turn reuses the existing
``_request_and_wait_for_agent()`` primitive — no new messaging infra needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class DialogueStatus(Enum):
    """Lifecycle status of a dialogue session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"  # budget/deadline/max-turns
    ERROR = "error"


@dataclass
class DialogueTurn:
    """A single turn in a dialogue."""

    turn_number: int
    speaker: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "speaker": self.speaker,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DialogueTurn:
        return cls(
            turn_number=data["turn_number"],
            speaker=data["speaker"],
            message=data["message"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class DialogueSession:
    """Tracks the full state of a multi-turn dialogue between two agents."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    initiator: str = ""
    responder: str = ""
    goal: str = ""
    capability: str = ""
    turns: List[DialogueTurn] = field(default_factory=list)
    max_turns: int = 5
    status: DialogueStatus = DialogueStatus.ACTIVE

    # ---- properties ----

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def is_complete(self) -> bool:
        return self.status != DialogueStatus.ACTIVE

    # ---- mutators ----

    def add_turn(self, speaker: str, message: str, **metadata: Any) -> DialogueTurn:
        turn = DialogueTurn(
            turn_number=self.turn_count + 1,
            speaker=speaker,
            message=message,
            metadata=metadata,
        )
        self.turns.append(turn)
        return turn

    # ---- formatting ----

    def format_transcript(self) -> str:
        lines: List[str] = []
        for t in self.turns:
            lines.append(f"[Turn {t.turn_number}] {t.speaker}: {t.message}")
        return "\n".join(lines)

    # ---- serialisation ----

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "initiator": self.initiator,
            "responder": self.responder,
            "goal": self.goal,
            "capability": self.capability,
            "turns": [t.to_dict() for t in self.turns],
            "max_turns": self.max_turns,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DialogueSession:
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())),
            initiator=data.get("initiator", ""),
            responder=data.get("responder", ""),
            goal=data.get("goal", ""),
            capability=data.get("capability", ""),
            turns=[DialogueTurn.from_dict(t) for t in data.get("turns", [])],
            max_turns=data.get("max_turns", 5),
            status=DialogueStatus(data.get("status", "active")),
        )
