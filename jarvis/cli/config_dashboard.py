"""Interactive config dashboard for the Jarvis REPL.

Provides `/config` and `/agents` slash commands with rich terminal UI.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from jarvis.core.config import (
    CONNECTION_KEYS,
    FLAG_NAMES,
    ConfigProfile,
    apply_profile,
    load_config,
    save_config,
)

if TYPE_CHECKING:
    from jarvis.core.system import JarvisSystem

console = Console()

# Human-readable labels for feature flags
_FLAG_LABELS = {
    "enable_lights": "Lights",
    "enable_canvas": "Canvas",
    "enable_night_mode": "Night Mode",
    "enable_roku": "Roku",
}

# Human-readable labels for connection keys
_CONN_LABELS = {
    "lighting_backend": "Lighting Backend",
    "hue_bridge_ip": "Hue Bridge IP",
    "hue_username": "Hue Username",
    "roku_ip_address": "Roku IP",
    "yeelight_bulb_ips": "Yeelight Bulb IPs",
}


def _slugify(name: str) -> str:
    """Convert a profile label to a dict key."""
    return name.strip().lower().replace(" ", "_")


def _get_input(prompt: str) -> str:
    """Synchronous input wrapper."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def _load_state(jarvis: JarvisSystem) -> tuple[str, dict[str, ConfigProfile]]:
    """Load profiles from disk, creating a default if none exist."""
    active_key, profiles = load_config()
    if not profiles:
        # Bootstrap from current runtime config
        profile = ConfigProfile.from_config("Default", jarvis.config)
        profiles = {"default": profile}
        active_key = "default"
        save_config(active_key, profiles)
    if active_key not in profiles:
        active_key = next(iter(profiles))
    return active_key, profiles


def _render_dashboard(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Render the main config dashboard panel."""
    profile = profiles[active_key]
    flags = jarvis.config.flags

    # --- Feature flags section ---
    flag_lines: list[str] = []
    for i, name in enumerate(FLAG_NAMES, 1):
        label = _FLAG_LABELS.get(name, name)
        val = getattr(flags, name, False)
        status = "[bold green]ON [/bold green]" if val else "[bold red]OFF[/bold red]"
        flag_lines.append(f"  [cyan]\\[{i}][/cyan] {label:<14s} {status}")

    # Pair flags into two columns
    paired: list[str] = []
    for idx in range(0, len(flag_lines), 2):
        left = flag_lines[idx]
        right = flag_lines[idx + 1] if idx + 1 < len(flag_lines) else ""
        paired.append(f"{left}    {right}")

    # --- Connection details section ---
    conn_lines: list[str] = []
    for key in CONNECTION_KEYS:
        label = _CONN_LABELS.get(key, key)
        val = getattr(jarvis.config, key, None)
        display = str(val) if val else "--"
        conn_lines.append(f"  {label + ':':<22s} {display}")

    body = (
        f"  Active Profile: [bold yellow]{profile.label}[/bold yellow]\n"
        "\n"
        "  [underline]Feature Flags[/underline]\n"
        + "\n".join(paired)
        + "\n\n"
        "  [underline]Connection Details[/underline]\n"
        + "\n".join(conn_lines)
    )

    console.print(Panel(body, title="Jarvis Configuration", border_style="bright_blue"))


def _render_agents(jarvis: JarvisSystem) -> None:
    """Render the active agents table."""
    agents = jarvis.network.agents
    table = Table(title=f"Active Agents ({len(agents)})", border_style="bright_blue")
    table.add_column("Name", style="cyan", min_width=18)
    table.add_column("Description", min_width=24)
    table.add_column("Capabilities", justify="center", min_width=6)

    for name, agent in sorted(agents.items()):
        caps = len(agent.capabilities) if hasattr(agent, "capabilities") else 0
        desc = agent.description if hasattr(agent, "description") else ""
        table.add_row(name, desc, str(caps))

    console.print(table)


def _render_menu() -> None:
    """Render the action bar."""
    console.print(
        "\n  [cyan]\\[1-5][/cyan] Toggle flag   "
        "[cyan]\\[p][/cyan] Switch profile   "
        "[cyan]\\[n][/cyan] New profile   "
        "[cyan]\\[c][/cyan] Edit connections   "
        "[cyan]\\[d][/cyan] Delete profile   "
        "[cyan]\\[q][/cyan] Back\n"
    )


def _handle_toggle(
    jarvis: JarvisSystem,
    idx: int,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Toggle a feature flag by index (1-based)."""
    if idx < 1 or idx > len(FLAG_NAMES):
        console.print("[red]Invalid flag number.[/red]")
        return
    name = FLAG_NAMES[idx - 1]
    current = getattr(jarvis.config.flags, name)
    setattr(jarvis.config.flags, name, not current)
    new_val = "ON" if not current else "OFF"
    console.print(f"  {_FLAG_LABELS.get(name, name)} → [bold]{new_val}[/bold]")
    # Persist
    profiles[active_key].feature_flags[name] = not current
    save_config(active_key, profiles)


def _handle_switch_profile(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> tuple[str, dict[str, ConfigProfile]]:
    """Show profile list and switch."""
    keys = list(profiles.keys())
    console.print("\n  [underline]Profiles[/underline]")
    for i, k in enumerate(keys, 1):
        marker = " [bold green]◀[/bold green]" if k == active_key else ""
        console.print(f"  [cyan]\\[{i}][/cyan] {profiles[k].label}{marker}")

    choice = _get_input("\n  Select profile number: ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            new_key = keys[idx]
            apply_profile(jarvis.config, profiles[new_key])
            save_config(new_key, profiles)
            console.print(f"  Switched to [bold yellow]{profiles[new_key].label}[/bold yellow]")
            console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
            return new_key, profiles
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")
    return active_key, profiles


def _handle_new_profile(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> tuple[str, dict[str, ConfigProfile]]:
    """Create a new profile from the current config."""
    name = _get_input("  Profile name: ")
    if not name or name.lower() == "q":
        return active_key, profiles
    key = _slugify(name)
    if key in profiles:
        console.print(f"[red]  Profile '{name}' already exists.[/red]")
        return active_key, profiles
    profiles[key] = ConfigProfile.from_config(name, jarvis.config)
    save_config(active_key, profiles)
    console.print(f"  Created profile [bold yellow]{name}[/bold yellow]")
    return active_key, profiles


def _handle_edit_connections(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Sub-menu to edit connection details."""
    console.print("\n  [underline]Edit Connections[/underline]")
    for i, key in enumerate(CONNECTION_KEYS, 1):
        label = _CONN_LABELS.get(key, key)
        val = getattr(jarvis.config, key, None)
        display = str(val) if val else "--"
        console.print(f"  [cyan]\\[{i}][/cyan] {label}: {display}")

    choice = _get_input("\n  Select connection to edit (or q): ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(CONNECTION_KEYS):
            conn_key = CONNECTION_KEYS[idx]
            label = _CONN_LABELS.get(conn_key, conn_key)
            new_val = _get_input(f"  New value for {label}: ")
            if new_val and new_val.lower() != "q":
                # Handle list type for yeelight_bulb_ips
                if conn_key == "yeelight_bulb_ips":
                    parsed = [ip.strip() for ip in new_val.split(",")]
                    setattr(jarvis.config, conn_key, parsed)
                    profiles[active_key].connections[conn_key] = parsed
                else:
                    setattr(jarvis.config, conn_key, new_val)
                    profiles[active_key].connections[conn_key] = new_val
                save_config(active_key, profiles)
                console.print(f"  {label} updated.")
                console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
            return
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")


def _handle_delete_profile(
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> tuple[str, dict[str, ConfigProfile]]:
    """Delete a profile (cannot delete the active one if it's the last)."""
    if len(profiles) <= 1:
        console.print("[red]  Cannot delete the only profile.[/red]")
        return active_key, profiles

    keys = [k for k in profiles if k != active_key]
    console.print("\n  [underline]Delete Profile[/underline]")
    for i, k in enumerate(keys, 1):
        console.print(f"  [cyan]\\[{i}][/cyan] {profiles[k].label}")

    choice = _get_input("\n  Select profile to delete (or q): ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            del_key = keys[idx]
            label = profiles[del_key].label
            confirm = _get_input(f"  Delete '{label}'? (y/n): ")
            if confirm.lower() == "y":
                del profiles[del_key]
                save_config(active_key, profiles)
                console.print(f"  Deleted profile [bold red]{label}[/bold red]")
            return active_key, profiles
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")
    return active_key, profiles


async def run_config_dashboard(jarvis: JarvisSystem) -> None:
    """Main entry point for the /config interactive dashboard."""
    active_key, profiles = _load_state(jarvis)

    while True:
        console.print()
        _render_dashboard(jarvis, active_key, profiles)
        _render_agents(jarvis)
        _render_menu()

        choice = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _get_input("  > ")
        )

        if choice.lower() == "q":
            break
        elif choice.lower() == "p":
            active_key, profiles = _handle_switch_profile(jarvis, active_key, profiles)
        elif choice.lower() == "n":
            active_key, profiles = _handle_new_profile(jarvis, active_key, profiles)
        elif choice.lower() == "c":
            _handle_edit_connections(jarvis, active_key, profiles)
        elif choice.lower() == "d":
            active_key, profiles = _handle_delete_profile(active_key, profiles)
        elif choice.isdigit():
            _handle_toggle(jarvis, int(choice), active_key, profiles)
        else:
            console.print("[red]  Unknown command.[/red]")


async def show_agents_detail(jarvis: JarvisSystem) -> None:
    """Show a detailed view of all active agents (/agents command)."""
    agents = jarvis.network.agents
    table = Table(title=f"Active Agents ({len(agents)})", border_style="bright_blue")
    table.add_column("Name", style="cyan", min_width=20)
    table.add_column("Description", min_width=28)
    table.add_column("Capabilities", min_width=12)
    table.add_column("Intents", justify="center", min_width=8)

    for name, agent in sorted(agents.items()):
        caps = ", ".join(sorted(agent.capabilities)) if hasattr(agent, "capabilities") else ""
        desc = agent.description if hasattr(agent, "description") else ""
        intents = str(len(agent.intent_map)) if hasattr(agent, "intent_map") else "0"
        table.add_row(name, desc, caps, intents)

    console.print()
    console.print(table)
    console.print()
