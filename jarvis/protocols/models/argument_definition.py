from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from enum import Enum


class ArgumentType(Enum):
    """Types of arguments a protocol can accept."""

    CHOICE = "choice"  # Pick from a list: {red, blue, green}
    RANGE = "range"  # Number in range: {1-255}
    TEXT = "text"  # Free text
    BOOLEAN = "boolean"  # True/False


@dataclass
class ArgumentDefinition:
    """Defines what kind of argument a protocol expects."""

    name: str
    type: ArgumentType
    choices: List[str] = field(default_factory=list)  # For CHOICE type
    min_val: Optional[int] = None  # For RANGE type
    max_val: Optional[int] = None  # For RANGE type
    required: bool = True
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArgumentDefinition":
        """Create ArgumentDefinition from dict (for JSON loading)."""
        arg_type = ArgumentType(data["type"])
        return cls(
            name=data["name"],
            type=arg_type,
            choices=data.get("choices", []),
            min_val=data.get("min_val"),
            max_val=data.get("max_val"),
            required=data.get("required", True),
            description=data.get("description", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "name": self.name,
            "type": self.type.value,
            "required": self.required,
            "description": self.description,
        }
        if self.choices:
            result["choices"] = self.choices
        if self.min_val is not None:
            result["min_val"] = self.min_val
        if self.max_val is not None:
            result["max_val"] = self.max_val
        return result
