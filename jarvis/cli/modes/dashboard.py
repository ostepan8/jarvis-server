"""Modes dashboard — /modes slash command UI."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from .base import BaseMode, mode_registry
from .runner import run_mode

if TYPE_CHECKING:
    from jarvis.core.system import JarvisSystem

console = Console()


async def show_modes_dashboard(jarvis: JarvisSystem) -> None:
    """Interactive dashboard for the /modes slash command."""
    mode_classes = mode_registry.all_modes

    if not mode_classes:
        console.print("\n  [dim]No modes available.[/dim]\n")
        return

    # Instantiate modes to check availability
    modes_list: list[tuple[str, BaseMode | None, bool]] = []
    for slug, mode_cls in mode_classes.items():
        try:
            mode = mode_cls(jarvis)
            # Check if the backing service is available
            available = _check_availability(jarvis, slug)
            modes_list.append((slug, mode, available))
        except Exception:
            modes_list.append((slug, None, False))

    # Render table
    table = Table(
        title="Device Modes",
        border_style="bright_blue",
        title_style="bold bright_blue",
    )
    table.add_column("#", style="cyan", justify="center", min_width=3)
    table.add_column("Mode", min_width=14)
    table.add_column("Description", min_width=30)
    table.add_column("Status", justify="center", min_width=10)

    for i, (slug, mode, available) in enumerate(modes_list, 1):
        if mode is None:
            table.add_row(str(i), slug, "—", "[red]Error[/red]")
            continue
        status = "[green]Available[/green]" if available else "[red]Unavailable[/red]"
        table.add_row(str(i), f"{mode.icon}  {mode.name}", mode.description, status)

    console.print()
    console.print(table)
    console.print(
        "\n  [dim]Select a number to enter a mode, or [cyan]q[/cyan] to go back.[/dim]\n"
    )

    # Get user selection
    choice = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _get_input("  > ")
    )

    if choice.lower() == "q" or not choice:
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(modes_list):
            slug, mode, available = modes_list[idx]
            if mode is None:
                console.print("[red]  Mode failed to initialize.[/red]")
                return
            if not available:
                console.print(
                    f"\n  [red]{mode.name} is not available.[/red]"
                    "\n  [dim]Check that the device is enabled in /config and the IP is set.[/dim]\n"
                )
                return
            if mode is not None:
                await run_mode(mode)
                return
        console.print("[red]  Invalid selection.[/red]")
    except ValueError:
        console.print("[red]  Invalid selection.[/red]")


def _check_availability(jarvis: JarvisSystem, slug: str) -> bool:
    """Check if a mode's backing service is available."""
    if slug == "roku":
        agents = jarvis.network.agents
        roku_agent = agents.get("RokuAgent")
        return (
            roku_agent is not None
            and hasattr(roku_agent, "roku_service")
            and hasattr(jarvis.config, "roku_ip_address")
            and bool(jarvis.config.roku_ip_address)
        )
    return False


async def enter_mode_by_slug(
    jarvis: JarvisSystem, slug: str, target_device: str | None = None
) -> bool:
    """Enter a mode directly by slug. Returns True if mode was found and entered.

    ``target_device`` is an optional friendly-name hint forwarded to the mode
    so it can resolve a specific device on entry (e.g. "bedroom", "living room").
    """
    mode_cls = mode_registry.get(slug)
    if mode_cls is None:
        return False

    import inspect

    sig = inspect.signature(mode_cls.__init__)
    if "target_device" in sig.parameters:
        mode = mode_cls(jarvis, target_device=target_device)
    else:
        mode = mode_cls(jarvis)

    if not _check_availability(jarvis, slug):
        console.print(
            f"\n  [red]{mode.name} is not available.[/red]"
            "\n  [dim]Check that the device is enabled in /config and the IP is set.[/dim]\n"
        )
        return True  # Found but unavailable — still handled

    await run_mode(mode)
    return True


def _get_input(prompt: str) -> str:
    """Synchronous input wrapper."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"
