from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class Capability:
    """Defines a capability that an agent provides."""

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
