from __future__ import annotations

from dataclasses import dataclass, field
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ProtocolStep:
    """Single step inside a protocol."""

    intent: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolStep":
        """Create a step from a mapping."""
        return cls(intent=data.get("intent"), parameters=data.get("parameters", {}))


@dataclass
class Protocol:
    """A named protocol consisting of ordered steps."""

    id: str
    name: str
    description: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    steps: List[ProtocolStep] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], protocol_id: str | None = None) -> "Protocol":
        """Create a Protocol from a mapping."""
        steps_data = data.get("steps", [])
        steps = [ProtocolStep.from_dict(s) for s in steps_data]
        pid = protocol_id or data.get("id") or str(uuid.uuid4())
        return cls(
            id=pid,
            name=data["name"],
            description=data.get("description", ""),
            arguments=data.get("arguments", {}),
            steps=steps,
        )

    @classmethod
    def from_file(cls, file_path: str | Path) -> "Protocol":
        """Load a Protocol definition from a JSON file."""
        data = json.loads(Path(file_path).read_text())
        return cls.from_dict(data)
