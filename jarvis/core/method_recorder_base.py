from __future__ import annotations

"""Abstract base class for protocol recorders."""

from abc import ABC, abstractmethod

from ..protocols.instruction_protocol import InstructionProtocol


class MethodRecorderBase(ABC):
    """Abstract base for persisting recorded protocols.

    Subclasses must implement :meth:`save` to store completed protocols.
    """

    @abstractmethod
    def save(self, protocol: InstructionProtocol) -> None:
        """Persist the completed protocol."""
        raise NotImplementedError
