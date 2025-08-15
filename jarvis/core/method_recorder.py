from __future__ import annotations

"""Helpers for recording method invocations into protocols."""

from dataclasses import dataclass
import uuid
from typing import Any, Dict

from ..protocols.instruction_protocol import InstructionProtocol
from ..protocols.models import ProtocolStep

from .method_recorder_base import MethodRecorderBase


@dataclass
class MethodRecorder(MethodRecorderBase):
    """Record agent capability calls into an :class:`InstructionProtocol`."""

    recording: bool = False
    protocol: InstructionProtocol | None = None

    def start(self, name: str, description: str = "") -> InstructionProtocol:
        """Begin a new recording session."""
        self.protocol = InstructionProtocol(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
        )
        self.recording = True
        return self.protocol

    def record_step(
        self,
        agent: str,
        function: str,
        params: Dict[str, Any],
        mappings: Dict[str, str] | None = None,
    ) -> None:
        """Append a step to the current protocol."""
        if not self.recording or not self.protocol:
            return
        self.protocol.add_step(agent, function, params, mappings)

    def get_protocol(self) -> InstructionProtocol | None:
        """Return the current protocol under construction."""
        return self.protocol

    def replace_step(
        self,
        idx: int,
        agent: str,
        function: str,
        params: Dict[str, Any],
        mappings: Dict[str, str] | None = None,
    ) -> None:
        """Replace an existing step at ``idx`` with new parameters."""
        if not self.protocol:
            return
        if idx < 0 or idx >= len(self.protocol.steps):
            raise IndexError("Step index out of range")
        self.protocol.steps[idx] = ProtocolStep(
            agent=agent,
            function=function,
            parameters=params,
            parameter_mappings=mappings or {},
        )

    def stop(self) -> InstructionProtocol | None:
        """Finalize recording and return the completed protocol."""
        proto = self.protocol
        if proto:
            self.save(proto)
        self.protocol = None
        self.recording = False
        return proto

    def clear(self) -> None:
        """Reset recorder state without returning a protocol."""
        self.protocol = None
        self.recording = False

    def save(self, protocol: InstructionProtocol) -> None:  # pragma: no cover - override
        """Persist the completed protocol.

        Default implementation does nothing. Override in subclasses to
        provide custom persistence.
        """
        return None
