from __future__ import annotations

from pathlib import Path

from ..logger import JarvisLogger
from .models import Protocol
from .registry import ProtocolRegistry


class ProtocolLoader:
    """Load protocol definition files into a registry."""

    def __init__(self, registry: ProtocolRegistry, logger: JarvisLogger | None = None) -> None:
        self.registry = registry
        self.logger = logger or JarvisLogger()

    def load_directory(self, directory: Path) -> None:
        """Load all ``*.json`` protocols from a directory."""
        directory = Path(directory)
        if not directory.exists():
            self.logger.log("ERROR", "Protocol directory not found", str(directory))
            return

        for json_file in sorted(directory.glob("*.json")):
            try:
                protocol = Protocol.from_file(json_file)
                result = self.registry.register(protocol)
                if result.get("success"):
                    self.logger.log(
                        "INFO",
                        "Loaded protocol",
                        f"{protocol.name}",
                        f"Triggers: {protocol.trigger_phrases}",
                    )
                else:
                    self.logger.log(
                        "WARNING",
                        "Failed to register protocol",
                        f"{protocol.name}",
                        str(result),
                    )
            except Exception as exc:  # pragma: no cover - logging only
                self.logger.log(
                    "ERROR",
                    f"Failed to load protocol from {json_file}",
                    str(exc),
                )
