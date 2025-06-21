from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


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
