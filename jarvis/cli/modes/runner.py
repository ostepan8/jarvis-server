"""Async mode runtime loop — takes over the REPL during a mode session."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .base import BaseMode
from .raw_input import read_key_async, save_terminal_state, restore_terminal_state

if TYPE_CHECKING:
    pass

console = Console()


def _render_help(mode: BaseMode) -> None:
    """Render the keybind help panel for a mode."""
    # Group keybinds by category
    categories: dict[str, list] = {}
    seen_actions: set[str] = set()

    for kb in mode.keybinds:
        # Deduplicate (e.g., arrow keys and hjkl map to same action)
        dedup_key = f"{kb.category}:{kb.action}"
        if dedup_key in seen_actions:
            continue
        seen_actions.add(dedup_key)

        if kb.category not in categories:
            categories[kb.category] = []
        categories[kb.category].append(kb)

    table = Table(
        title=f"{mode.icon}  {mode.name} — Keybinds",
        border_style="bright_blue",
        title_style="bold bright_blue",
        show_lines=False,
    )
    table.add_column("Key", style="bold cyan", min_width=10)
    table.add_column("Action", min_width=16)
    table.add_column("Category", style="dim", min_width=12)

    category_order = ["navigation", "playback", "volume", "power", "info", "system"]
    for cat in category_order:
        binds = categories.get(cat, [])
        for kb in binds:
            # Show all keys that map to this action
            all_keys = [b.key for b in mode.keybinds if b.action == kb.action]
            key_display = " / ".join(_format_key(k) for k in all_keys)
            table.add_row(key_display, kb.label, cat)

    console.print()
    console.print(table)
    console.print()


def _format_key(key: str) -> str:
    """Format a key for display."""
    special = {
        "ENTER": "Enter",
        "ESC": "Esc",
        "UP": "Up",
        "DOWN": "Down",
        "LEFT": "Left",
        "RIGHT": "Right",
        " ": "Space",
    }
    return special.get(key, key)


def _print_status(message: str) -> None:
    """Print inline status using carriage return."""
    sys.stdout.write(f"\r\033[K  {message}")
    sys.stdout.flush()


async def run_mode(mode: BaseMode) -> None:
    """Run a mode session — takes over the REPL until the user exits."""
    saved_state = save_terminal_state()

    try:
        # Connect to device
        print("  Connecting...")
        try:
            connected = await mode.on_enter()
        except Exception as e:
            console.print(f"  [red]Connection error: {e}[/red]")
            return

        if not connected:
            console.print(f"  [red]Could not connect to {mode.name}.[/red]")
            console.print("  [dim]Check that the device is on and the IP is configured.[/dim]\n")
            return

        # Show header
        console.print()
        console.print(
            Panel(
                f"  Connected to [bold]{mode.name}[/bold]  |  "
                f"Press [cyan]?[/cyan] for help  |  "
                f"Press [cyan]q[/cyan] to exit",
                title=f"{mode.icon}  {mode.name} Mode",
                border_style="green",
            )
        )
        _print_status("Ready")

        # Main keystroke loop
        while True:
            key = await read_key_async()

            # Exit check
            if mode.is_exit_key(key):
                break

            # Help — temporarily restore terminal for Rich rendering
            if key == "?":
                restore_terminal_state(saved_state)
                _render_help(mode)
                _print_status("Ready")
                continue

            # Dispatch keypress
            try:
                status = await mode.handle_key(key)
                if status:
                    _print_status(status)
            except Exception as e:
                _print_status(f"Error: {e}")

    except KeyboardInterrupt:
        pass  # Ctrl+C — clean exit
    except Exception as e:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        console.print(f"  [red]Mode error: {e}[/red]")
    finally:
        # Always restore terminal state
        restore_terminal_state(saved_state)
        await mode.on_exit()
        # Clear the status line and show exit message
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        console.print(f"  [dim]Exited {mode.name} mode.[/dim]\n")
