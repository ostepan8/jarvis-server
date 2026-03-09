from __future__ import annotations

from pathlib import Path

from ..logging import JarvisLogger
from .models import Protocol
from .registry import ProtocolRegistry


class ProtocolLoader:
    """Load protocol definition files into a registry."""

    def __init__(
        self, registry: ProtocolRegistry, logger: JarvisLogger | None = None
    ) -> None:
        self.registry = registry
        self.logger = logger or JarvisLogger()

    def load_directory(
        self, directory: Path, skip_prefixes: list[str] | None = None
    ) -> None:
        """Load all ``*.json`` protocols from a directory.

        Args:
            directory: Directory containing JSON protocol definitions.
            skip_prefixes: Optional list of filename prefixes to skip
                (e.g. ``["lights_"]`` to skip all lights protocols).
        """
        directory = Path(directory)
        if not directory.exists():
            self.logger.log("ERROR", "Protocol directory not found", str(directory))
            return

        skip_prefixes = skip_prefixes or []

        for json_file in sorted(directory.glob("*.json")):
            if any(json_file.name.startswith(prefix) for prefix in skip_prefixes):
                self.logger.log(
                    "INFO", "Skipping disabled protocol", json_file.name
                )
                continue
            try:
                protocol = Protocol.from_file(json_file)
                result = self.registry.register(protocol, replace_duplicates=True)
                if result.get("success"):
                    if result.get("replaced"):
                        details = (
                            f"{protocol.name} - Triggers: {protocol.trigger_phrases}"
                        )
                        self.logger.log(
                            "INFO",
                            "Replaced protocol",
                            details,
                        )
                    else:
                        details = (
                            f"{protocol.name} - Triggers: {protocol.trigger_phrases}"
                        )
                        self.logger.log(
                            "INFO",
                            "Loaded protocol",
                            details,
                        )
                else:
                    details = f"{protocol.name} - {str(result)}"
                    self.logger.log(
                        "WARNING",
                        "Failed to register protocol",
                        details,
                    )
            except Exception as exc:  # pragma: no cover - logging only
                self.logger.log(
                    "ERROR",
                    f"Failed to load protocol from {json_file}",
                    str(exc),
                )
