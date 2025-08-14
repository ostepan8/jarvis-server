from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .models import Protocol, ProtocolStep


@dataclass
class InstructionProtocol(Protocol):
    """Protocol with convenience method for adding steps."""

    def add_step(
        self,
        agent: str,
        function: str,
        params: Dict[str, Any],
        mappings: Dict[str, str] | None = None,
    ) -> None:
        """Append a ``ProtocolStep`` to the protocol."""
        self.steps.append(
            ProtocolStep(
                agent=agent,
                function=function,
                parameters=params,
                parameter_mappings=mappings or {},
            )
        )
