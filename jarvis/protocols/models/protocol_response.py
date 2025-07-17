from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ResponseMode(Enum):
    """How a protocol should generate its response."""

    STATIC = "static"
    AI = "ai"


@dataclass
class ProtocolResponse:
    """Defines how to produce a reply after protocol execution."""

    mode: ResponseMode
    phrases: List[str] = field(default_factory=list)
    prompt: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolResponse":
        return cls(
            mode=ResponseMode(data["mode"]),
            phrases=data.get("phrases", []),
            prompt=data.get("prompt", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {"mode": self.mode.value}
        if self.phrases:
            result["phrases"] = self.phrases
        if self.prompt:
            result["prompt"] = self.prompt
        return result
