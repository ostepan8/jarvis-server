"""Commands dashboard for the Jarvis REPL.

Provides `/commands` slash command to browse all available voice
trigger phrases, sorted shortest-first for quick reference.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from jarvis.core.system import JarvisSystem

console = Console()


def _get_protocols(jarvis: JarvisSystem) -> list:
    """Return available protocols, or empty list if none loaded."""
    if not jarvis.protocol_runtime:
        return []
    return jarvis.protocol_runtime.list_protocols()


def _shortest_trigger(phrases: list[str]) -> str:
    """Return the shortest trigger phrase from a list."""
    return min(phrases, key=len) if phrases else ""


async def show_commands_overview(jarvis: JarvisSystem) -> None:
    """Show a compact table of all commands sorted by shortest trigger phrase."""
    protocols = _get_protocols(jarvis)
    if not protocols:
        console.print("[dim]  No commands available.[/dim]")
        return

    # Sort by length of shortest trigger phrase
    protocols.sort(key=lambda p: len(_shortest_trigger(p.trigger_phrases)))

    table = Table(
        title="Commands",
        border_style="bright_blue",
        title_style="bold bright_blue",
    )
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Trigger", style="bold green", min_width=16)
    table.add_column("Command", style="cyan", min_width=14)
    table.add_column("Description", min_width=20)
    table.add_column("Phrases", justify="center", style="dim", width=7)

    for i, proto in enumerate(protocols, 1):
        shortest = _shortest_trigger(proto.trigger_phrases)
        table.add_row(
            str(i),
            f'"{shortest}"',
            proto.name,
            proto.description,
            str(len(proto.trigger_phrases)),
        )

    console.print()
    console.print(table)
    console.print(
        "\n  [dim]Tip: [cyan]/commands <name>[/cyan] for details  |  "
        "[cyan]/commands all[/cyan] for every trigger phrase[/dim]\n"
    )


async def show_command_detail(jarvis: JarvisSystem, name: str) -> None:
    """Show full detail for a single command (all trigger phrases, args, agent)."""
    protocols = _get_protocols(jarvis)
    name_lower = name.lower().replace(" ", "_")

    # Match by protocol name (case-insensitive, underscore-insensitive)
    match = None
    for proto in protocols:
        if proto.name.lower().replace(" ", "_") == name_lower:
            match = proto
            break

    # Fallback: partial match
    if not match:
        for proto in protocols:
            if name_lower in proto.name.lower().replace(" ", "_"):
                match = proto
                break

    if not match:
        console.print(f"[red]  Command '{name}' not found.[/red]")
        console.print("[dim]  Use /commands to see all available commands.[/dim]")
        return

    # Build trigger phrase list sorted by length
    phrases = sorted(match.trigger_phrases, key=len)
    phrase_lines = "\n".join(
        f"  [green]{'*' if i == 0 else ' '}[/green] {p}"
        for i, p in enumerate(phrases)
    )

    # Required agents
    agents = ", ".join(sorted({step.agent for step in match.steps}))

    # Arguments
    arg_lines = ""
    if match.argument_definitions:
        arg_parts = []
        for ad in match.argument_definitions:
            choices = f" ({', '.join(ad.choices)})" if hasattr(ad, "choices") and ad.choices else ""
            arg_parts.append(f"  {ad.name}{choices}")
        arg_lines = "\n\n  [underline]Arguments[/underline]\n" + "\n".join(arg_parts)

    body = (
        f"  [underline]Description[/underline]\n"
        f"  {match.description}\n\n"
        f"  [underline]Agent[/underline]\n"
        f"  {agents}\n\n"
        f"  [underline]Trigger Phrases[/underline] ({len(phrases)})\n"
        f"{phrase_lines}"
        f"{arg_lines}"
    )

    console.print()
    console.print(Panel(body, title=f"[bold]{match.name}[/bold]", border_style="bright_blue"))
    console.print()


async def show_commands_all(jarvis: JarvisSystem) -> None:
    """Show every protocol with all trigger phrases, grouped and sorted."""
    protocols = _get_protocols(jarvis)
    if not protocols:
        console.print("[dim]  No commands available.[/dim]")
        return

    # Sort protocols by shortest trigger
    protocols.sort(key=lambda p: len(_shortest_trigger(p.trigger_phrases)))

    table = Table(
        title="All Commands & Trigger Phrases",
        border_style="bright_blue",
        title_style="bold bright_blue",
        show_lines=True,
    )
    table.add_column("Command", style="cyan", min_width=14)
    table.add_column("Description", min_width=18)
    table.add_column("Trigger Phrases (shortest first)", style="green", min_width=30)

    for proto in protocols:
        phrases = sorted(proto.trigger_phrases, key=len)
        phrase_text = "\n".join(phrases)
        table.add_row(proto.name, proto.description, phrase_text)

    console.print()
    console.print(table)
    console.print()
