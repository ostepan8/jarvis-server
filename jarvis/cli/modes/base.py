"""Base mode ABC, ModeKeybind dataclass, and ModeRegistry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModeKeybind:
    """A single keybind definition for a mode."""

    key: str
    label: str
    action: str
    category: str  # navigation, playback, volume, power, info, system


class BaseMode(ABC):
    """Abstract base class for all interactive device modes."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable mode name."""

    @property
    @abstractmethod
    def slug(self) -> str:
        """URL-safe identifier."""

    @property
    @abstractmethod
    def icon(self) -> str:
        """Emoji icon for display."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the mode."""

    @property
    @abstractmethod
    def keybinds(self) -> list[ModeKeybind]:
        """All keybinds supported by this mode."""

    @abstractmethod
    async def on_enter(self) -> bool:
        """Called when entering the mode. Return True if device is reachable."""

    @abstractmethod
    async def on_exit(self) -> None:
        """Called when exiting the mode. Cleanup resources."""

    @abstractmethod
    async def handle_key(self, key: str) -> Optional[str]:
        """Handle a keypress. Return a status message or None."""

    def is_exit_key(self, key: str) -> bool:
        """Return True if this key should exit the mode."""
        return key in ("q", "\x1b")  # q or bare Esc


class ModeRegistry:
    """Global registry of available modes."""

    def __init__(self) -> None:
        self._modes: dict[str, type[BaseMode]] = {}

    def register(self, mode_cls: type[BaseMode]) -> type[BaseMode]:
        """Register a mode class. Can be used as a decorator."""
        # Instantiate temporarily to get slug
        # We store the class, not the instance
        slug = mode_cls.__dict__.get("_slug") or mode_cls.__name__.lower().replace("mode", "")
        self._modes[slug] = mode_cls
        return mode_cls

    def register_with_slug(self, slug: str, mode_cls: type[BaseMode]) -> None:
        """Register a mode class with an explicit slug."""
        self._modes[slug] = mode_cls

    @property
    def all_modes(self) -> dict[str, type[BaseMode]]:
        return dict(self._modes)

    def get(self, slug: str) -> Optional[type[BaseMode]]:
        return self._modes.get(slug)


# Global singleton
mode_registry = ModeRegistry()
