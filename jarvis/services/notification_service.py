"""Notification service with pluggable delivery backends.

Starts with macOS native notifications (osascript).  Designed so adding
Slack, SMS, email, push, or carrier pigeon later is a one-class affair.
"""

from __future__ import annotations

import platform
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import deque

from ..logging import JarvisLogger


class NotificationPriority(str, Enum):
    """How urgently the human needs to know."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """A single notification record."""

    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    source: str = ""  # Which agent or subsystem sent it
    timestamp: str = ""
    delivered_via: List[str] = field(default_factory=list)
    delivery_errors: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "delivered_via": self.delivered_via,
            "delivery_errors": self.delivery_errors,
        }


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------

class NotificationBackend(ABC):
    """Base class for notification delivery backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'macos', 'slack')."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Deliver a notification. Returns True on success."""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this backend can send notifications right now."""


# ---------------------------------------------------------------------------
# macOS backend
# ---------------------------------------------------------------------------

class MacOSNotificationBackend(NotificationBackend):
    """Native macOS notifications via osascript."""

    @property
    def name(self) -> str:
        return "macos"

    def is_available(self) -> bool:
        return platform.system() == "Darwin"

    def send(self, notification: Notification) -> bool:
        if not self.is_available():
            return False
        try:
            safe_title = notification.title.replace("\\", "\\\\").replace('"', '\\"')
            safe_message = notification.message.replace("\\", "\\\\").replace('"', '\\"')

            # Add sound for high/critical priority
            sound_clause = ""
            if notification.priority in (
                NotificationPriority.HIGH,
                NotificationPriority.CRITICAL,
            ):
                sound_clause = ' sound name "Ping"'

            script = (
                f'display notification "{safe_message}" '
                f'with title "{safe_title}"{sound_clause}'
            )
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_DEFAULT_HISTORY_LIMIT = 100


class NotificationService:
    """Manages notification delivery across pluggable backends.

    Maintains a rolling history of recent notifications so the user
    can ask "what did I miss" after stepping away.
    """

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self._backends: List[NotificationBackend] = []
        self._history: deque[Notification] = deque(maxlen=history_limit)

        # Register the default macOS backend
        macos = MacOSNotificationBackend()
        if macos.is_available():
            self.register_backend(macos)

    # -- Backend management -------------------------------------------------

    def register_backend(self, backend: NotificationBackend) -> None:
        """Add a delivery backend."""
        self._backends.append(backend)
        self.logger.log(
            "INFO",
            "Notification backend registered",
            backend.name,
        )

    @property
    def available_backends(self) -> List[str]:
        """Names of currently available backends."""
        return [b.name for b in self._backends if b.is_available()]

    # -- Sending ------------------------------------------------------------

    def send(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        source: str = "",
    ) -> Notification:
        """Send a notification through all available backends.

        Returns the Notification record with delivery results.
        """
        notification = Notification(
            title=title,
            message=message,
            priority=priority,
            source=source,
        )

        if not self._backends:
            notification.delivery_errors["_global"] = "No backends configured"
            self._history.append(notification)
            return notification

        for backend in self._backends:
            if not backend.is_available():
                notification.delivery_errors[backend.name] = "Backend unavailable"
                continue
            try:
                success = backend.send(notification)
                if success:
                    notification.delivered_via.append(backend.name)
                else:
                    notification.delivery_errors[backend.name] = "Send returned False"
            except Exception as exc:
                notification.delivery_errors[backend.name] = str(exc)

        self._history.append(notification)
        return notification

    # -- History ------------------------------------------------------------

    def get_history(
        self,
        limit: int = 20,
        priority: Optional[NotificationPriority] = None,
        source: Optional[str] = None,
    ) -> List[Notification]:
        """Retrieve recent notifications, optionally filtered."""
        items = list(self._history)
        if priority:
            items = [n for n in items if n.priority == priority]
        if source:
            items = [n for n in items if n.source == source]
        # Most recent first
        items.reverse()
        return items[:limit]

    def clear_history(self) -> int:
        """Clear notification history. Returns count cleared."""
        count = len(self._history)
        self._history.clear()
        return count
