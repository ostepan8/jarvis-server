from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Event:
    """Simple container for event details."""

    summary: str
    start: str  # RFC3339 timestamp
    end: str  # RFC3339 timestamp
    description: str = ""
    timezone: str = "UTC"
    id: str | None = None
    recurrence: str | None = None

class CalendarService(ABC):
    """Abstract calendar service interface."""

    @abstractmethod
    def add_event(self, event: Event) -> str:
        """Add an event and return its ID."""

    @abstractmethod
    def delete_event(self, event_id: str) -> None:
        """Remove an event by ID."""
