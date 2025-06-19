from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ProtocolStep:
    """Single step inside a protocol."""

    intent: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Protocol:
    """A named protocol consisting of ordered steps."""

    id: str
    name: str
    description: str
    steps: List[ProtocolStep] = field(default_factory=list)
