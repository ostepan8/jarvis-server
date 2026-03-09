"""Raw terminal input for single-keypress capture.

Uses tty.setcbreak (not setraw) so Ctrl+C still works for emergency exit.
Handles multi-byte escape sequences (arrow keys).
"""

from __future__ import annotations

import asyncio
import select
import sys
import termios
import tty


def _read_key_blocking() -> str:
    """Read a single keypress from stdin in cbreak mode.

    Returns a string representing the key:
    - Regular chars: "a", "j", "?", etc.
    - Arrow keys: "UP", "DOWN", "LEFT", "RIGHT"
    - Enter: "ENTER"
    - Escape (bare): "ESC"
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = sys.stdin.read(1)

        # Handle escape sequences
        if ch == "\x1b":
            # Check if more bytes are available (arrow key sequence)
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if ready:
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    arrow_map = {
                        "A": "UP",
                        "B": "DOWN",
                        "C": "RIGHT",
                        "D": "LEFT",
                    }
                    return arrow_map.get(ch3, "ESC")
                return "ESC"
            # Bare escape — no follow-up bytes
            return "ESC"

        if ch == "\r" or ch == "\n":
            return "ENTER"

        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


async def read_key_async() -> str:
    """Async wrapper around blocking key read."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_key_blocking)


def save_terminal_state() -> list:
    """Save current terminal settings."""
    fd = sys.stdin.fileno()
    return termios.tcgetattr(fd)


def restore_terminal_state(settings: list) -> None:
    """Restore saved terminal settings."""
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, settings)
