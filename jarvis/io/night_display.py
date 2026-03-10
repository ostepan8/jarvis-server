"""Real-time terminal output for night mode operations.

Writes directly to sys.stdout — bypasses OutputHandler intentionally,
since night mode output is a side-channel that should appear even while
the input prompt is blocked.
"""

from __future__ import annotations

import sys
from datetime import datetime

from colorama import Fore, Style


class NightModePrinter:
    """Renders night mode progress events to the terminal.

    One line per event, prefixed with [night] in magenta and an HH:MM:SS
    timestamp.  Messages are terse — this is a status feed, not a novel.
    """

    PREFIX = f"{Fore.MAGENTA}[night]{Style.RESET_ALL}"

    def on_event(self, event_type: str, message: str, data: dict) -> None:
        """Handle a progress event from the night improvement cycle."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"{self.PREFIX} {Fore.CYAN}{timestamp}{Style.RESET_ALL}  {message}"

        # Append PR URL on success if available
        if event_type == "task_success" and data.get("pr_url"):
            line += f" PR: {data['pr_url']}"

        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def print_entering(self) -> None:
        """Announce night mode activation."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(
            f"\n{self.PREFIX} {Fore.CYAN}{timestamp}{Style.RESET_ALL}  "
            f"Entering night mode. Stand by.\n"
        )
        sys.stdout.flush()

    def print_waiting(self) -> None:
        """Indicate night mode is idle, waiting for user."""
        sys.stdout.write(
            f"{self.PREFIX}           "
            f"{Fore.WHITE}Press Enter or type a command to wake Jarvis.{Style.RESET_ALL}\n"
        )
        sys.stdout.flush()

    def print_waking(self) -> None:
        """Announce return from night mode."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(
            f"{self.PREFIX} {Fore.CYAN}{timestamp}{Style.RESET_ALL}  "
            f"Back online.\n\n"
        )
        sys.stdout.flush()
