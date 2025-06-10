from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Task:
    """Represents a single step in a complex request."""

    capability: str
    parameters: Dict[str, Any]
    assigned_agent: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    result: Any = None
