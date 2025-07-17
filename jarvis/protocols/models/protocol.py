from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .protocol_step import ProtocolStep
from .argument_definition import ArgumentDefinition
from .protocol_response import ProtocolResponse


@dataclass
class Protocol:
    """A named protocol consisting of ordered steps."""

    id: str
    name: str
    description: str
    arguments: Dict[str, Any] = field(default_factory=dict)  # For protocol parameters
    trigger_phrases: List[str] = field(default_factory=list)  # For voice activation
    steps: List[ProtocolStep] = field(default_factory=list)
    argument_definitions: List[ArgumentDefinition] = field(default_factory=list)  # NEW
    response: ProtocolResponse | None = None

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], protocol_id: str | None = None
    ) -> "Protocol":
        """Create a Protocol from a mapping."""
        steps_data = data.get("steps", [])
        steps = [ProtocolStep.from_dict(s) for s in steps_data]

        # Handle argument definitions if present
        arg_defs_data = data.get("argument_definitions", [])
        arg_defs = [ArgumentDefinition.from_dict(ad) for ad in arg_defs_data]

        resp_data = data.get("responses") or data.get("response")
        response = ProtocolResponse.from_dict(resp_data) if resp_data else None

        pid = protocol_id or data.get("id") or str(uuid.uuid4())
        return cls(
            id=pid,
            name=data["name"],
            description=data.get("description", ""),
            arguments=data.get("arguments", {}),
            trigger_phrases=data.get("trigger_phrases", [data["name"]]),
            steps=steps,
            argument_definitions=arg_defs,  # NEW
            response=response,
        )

    @classmethod
    def from_file(cls, file_path: str | Path) -> "Protocol":
        """Load a Protocol definition from a JSON file."""
        data = json.loads(Path(file_path).read_text())
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Protocol to dict for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
            "trigger_phrases": self.trigger_phrases,
            "steps": [step.__dict__ for step in self.steps],
            "argument_definitions": [ad.to_dict() for ad in self.argument_definitions],
            "responses": self.response.to_dict() if self.response else None,
        }
