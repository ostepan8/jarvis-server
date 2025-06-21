from __future__ import annotations

from dataclasses import dataclass, field
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ProtocolStep:
    """Single step inside a protocol - directly maps to a function call."""

    agent: str  # Which agent provides this capability
    function: str  # Exact function name in the agent's intent_map
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Optional: for dynamic parameters that depend on previous step results
    parameter_mappings: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolStep":
        """Create a step from a mapping."""
        return cls(
            agent=data["agent"],
            function=data["function"],
            parameters=data.get("parameters", {}),
            parameter_mappings=data.get("parameter_mappings", {}),
        )


@dataclass
class Protocol:
    """A named protocol consisting of ordered steps."""

    id: str
    name: str
    description: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    trigger_phrases: List[str] = field(default_factory=list)
    steps: List[ProtocolStep] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], protocol_id: str | None = None
    ) -> "Protocol":
        """Create a Protocol from a mapping."""
        steps_data = data.get("steps", [])
        steps = [ProtocolStep.from_dict(s) for s in steps_data]
        pid = protocol_id or data.get("id") or str(uuid.uuid4())
        return cls(
            id=pid,
            name=data["name"],
            description=data.get("description", ""),
            arguments=data.get("arguments", {}),
            trigger_phrases=data.get("trigger_phrases", [data["name"]]),
            steps=steps,
        )

    @classmethod
    def from_file(cls, file_path: str | Path) -> "Protocol":
        """Load a Protocol definition from a JSON file."""
        data = json.loads(Path(file_path).read_text())
        return cls.from_dict(data)
