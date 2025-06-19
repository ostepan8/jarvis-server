from __future__ import annotations

import json
import uuid
from pathlib import Path

from .. import Protocol, ProtocolStep
from ..registry import ProtocolRegistry


def load_default_protocols(registry: ProtocolRegistry, directory: str | Path | None = None) -> None:
    """Load all JSON protocol definitions in *directory* into the registry."""
    if directory is None:
        directory = Path(__file__).parent
    else:
        directory = Path(directory)

    for file_path in directory.glob("*.json"):
        data = json.loads(file_path.read_text())
        steps = [ProtocolStep(intent=s.get("intent"), parameters=s.get("parameters", {})) for s in data.get("steps", [])]
        proto = Protocol(
            id=str(uuid.uuid4()),
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
        )
        registry.register(proto)


def main() -> None:
    registry = ProtocolRegistry()
    load_default_protocols(registry)


if __name__ == "__main__":  # pragma: no cover - utility script
    main()
