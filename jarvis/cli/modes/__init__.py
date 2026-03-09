"""Jarvis interactive device modes — SSH-style direct control.

Auto-registers all modes on import.
"""

from .base import BaseMode, ModeKeybind, ModeRegistry, mode_registry  # noqa: F401
from .runner import run_mode  # noqa: F401
from .dashboard import show_modes_dashboard, enter_mode_by_slug  # noqa: F401

# Import modes to trigger auto-registration
from . import roku_mode  # noqa: F401
