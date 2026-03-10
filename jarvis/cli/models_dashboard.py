"""Interactive AI model management dashboard for the Jarvis REPL.

Provides the `/models` slash command with rich terminal UI for switching
AI providers, models, and managing model presets.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from jarvis.core.config import (
    BUILTIN_PRESETS,
    ModelPreset,
    load_config,
    save_config,
    ConfigProfile,
)

if TYPE_CHECKING:
    from jarvis.core.system import JarvisSystem

console = Console()

# Known models per provider (informational catalog, not a validation gate)
KNOWN_MODELS: dict[str, list[tuple[str, str]]] = {
    "openai": [
        ("gpt-4o", "Flagship multimodal model, strong reasoning"),
        ("gpt-4o-mini", "Fast and affordable, good for most tasks"),
        ("gpt-4-turbo", "GPT-4 Turbo with vision"),
        ("gpt-4", "Original GPT-4"),
        ("gpt-3.5-turbo", "Legacy, fast and cheap"),
        ("o1", "Reasoning model, slow but powerful"),
        ("o1-mini", "Smaller reasoning model"),
        ("o3-mini", "Latest small reasoning model"),
    ],
    "anthropic": [
        ("claude-opus-4-6", "Most capable Claude model"),
        ("claude-sonnet-4-6", "Strong balance of speed and capability"),
        ("claude-haiku-4-5-20251001", "Fastest Claude model"),
        ("claude-3-opus-20240229", "Previous generation flagship"),
        ("claude-3-sonnet-20240229", "Previous generation balanced"),
        ("claude-3-haiku-20240307", "Previous generation fast"),
    ],
}

_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai": ("gpt-4o", "gpt-4o-mini"),
    "anthropic": ("claude-sonnet-4-6", "claude-haiku-4-5-20251001"),
}


def _get_input(prompt: str) -> str:
    """Synchronous input wrapper."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def _slugify(name: str) -> str:
    """Convert a preset name to a dict key."""
    return name.strip().lower().replace(" ", "_")


def _load_state(jarvis: JarvisSystem) -> tuple[str, dict[str, ConfigProfile]]:
    """Load profiles from disk, creating a default if none exist."""
    active_key, profiles = load_config()
    if not profiles:
        profile = ConfigProfile.from_config("Default", jarvis.config)
        profiles = {"default": profile}
        active_key = "default"
        save_config(active_key, profiles)
    if active_key not in profiles:
        active_key = next(iter(profiles))
    return active_key, profiles


def _get_all_presets(
    profile: ConfigProfile,
) -> list[tuple[str, ModelPreset, bool]]:
    """Return merged list of (key, preset, is_custom) for display."""
    result: list[tuple[str, ModelPreset, bool]] = []
    for key, preset in BUILTIN_PRESETS.items():
        result.append((key, preset, False))
    for key, data in profile.model_presets.items():
        preset = ModelPreset.from_dict(data) if isinstance(data, dict) else data
        result.append((key, preset, True))
    return result


def _render_dashboard(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Render the main AI model settings panel."""
    profile = profiles[active_key]
    config = jarvis.config

    preset_name = "Manual"
    if profile.active_preset:
        # Check built-in first, then custom
        if profile.active_preset in BUILTIN_PRESETS:
            preset_name = BUILTIN_PRESETS[profile.active_preset].label
        elif profile.active_preset in profile.model_presets:
            data = profile.model_presets[profile.active_preset]
            preset_name = data.get("label", profile.active_preset) if isinstance(data, dict) else profile.active_preset

    body = (
        f"  Active Preset: [bold yellow]{preset_name}[/bold yellow]\n"
        f"  Provider:      [cyan]{config.ai_provider}[/cyan]\n"
        f"  Strong Model:  [green]{config.strong_model}[/green]\n"
        f"  Weak Model:    [green]{config.weak_model}[/green]"
    )

    console.print(Panel(body, title="AI Model Settings", border_style="bright_blue"))


def _render_presets_table(profile: ConfigProfile) -> None:
    """Render the presets table with built-in and custom presets."""
    all_presets = _get_all_presets(profile)

    table = Table(
        title=f"Model Presets ({len(BUILTIN_PRESETS)} built-in"
        + (f" + {len(profile.model_presets)} custom)" if profile.model_presets else ")"),
        border_style="bright_blue",
    )
    table.add_column("#", style="cyan", justify="right", width=4)
    table.add_column("Name", min_width=14)
    table.add_column("Provider", min_width=10)
    table.add_column("Strong Model", min_width=18)
    table.add_column("Weak Model", min_width=18)
    table.add_column("", width=4)

    for i, (key, preset, is_custom) in enumerate(all_presets, 1):
        num = f"{i}*" if is_custom else str(i)
        active = "[bold green]\u25c0[/bold green]" if key == profile.active_preset else ""
        table.add_row(
            num,
            preset.label,
            preset.provider,
            preset.strong_model,
            preset.weak_model,
            active,
        )

    console.print(table)
    if profile.model_presets:
        console.print("  [dim]* = custom preset[/dim]")


def _render_menu() -> None:
    """Render the action bar."""
    console.print(
        "\n  [cyan]\\[s][/cyan] Switch preset   "
        "[cyan]\\[n][/cyan] New preset   "
        "[cyan]\\[e][/cyan] Edit preset   "
        "[cyan]\\[d][/cyan] Delete preset\n"
        "  [cyan]\\[p][/cyan] Change provider  "
        "[cyan]\\[m][/cyan] Edit models  "
        "[cyan]\\[c][/cyan] Model catalog  "
        "[cyan]\\[q][/cyan] Back\n"
    )


def _handle_switch_preset(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Select and apply a model preset."""
    profile = profiles[active_key]
    all_presets = _get_all_presets(profile)

    console.print("\n  [underline]Switch Model Preset[/underline]")
    for i, (key, preset, is_custom) in enumerate(all_presets, 1):
        marker = " [bold green]\u25c0[/bold green]" if key == profile.active_preset else ""
        custom_tag = " [dim](custom)[/dim]" if is_custom else ""
        console.print(
            f"  [cyan]\\[{i}][/cyan] {preset.label}{custom_tag}"
            f"  [dim]{preset.provider} | {preset.strong_model} / {preset.weak_model}[/dim]{marker}"
        )

    choice = _get_input("\n  Select preset number: ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(all_presets):
            key, preset, _ = all_presets[idx]
            jarvis.config.ai_provider = preset.provider
            jarvis.config.strong_model = preset.strong_model
            jarvis.config.weak_model = preset.weak_model
            profile.ai_settings = {
                "ai_provider": preset.provider,
                "strong_model": preset.strong_model,
                "weak_model": preset.weak_model,
            }
            profile.active_preset = key
            save_config(active_key, profiles)
            console.print(f"  Switched to [bold yellow]{preset.label}[/bold yellow]")
            console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
            return
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")


def _handle_create_preset(
    active_key: str,
    profiles: dict[str, ConfigProfile],
    current_provider: str,
) -> None:
    """Create a new custom model preset."""
    console.print("\n  [underline]Create New Preset[/underline]")

    name = _get_input("  Preset name: ")
    if not name or name.lower() == "q":
        return
    key = _slugify(name)
    if key in BUILTIN_PRESETS or key in profiles[active_key].model_presets:
        console.print(f"[red]  Preset '{name}' already exists.[/red]")
        return

    # Provider selection
    console.print(f"\n  [cyan]\\[1][/cyan] OpenAI")
    console.print(f"  [cyan]\\[2][/cyan] Anthropic")
    console.print(f"  [dim]  (Enter = {current_provider})[/dim]")
    p_choice = _get_input("  Provider: ")
    if p_choice == "1":
        provider = "openai"
    elif p_choice == "2":
        provider = "anthropic"
    elif not p_choice:
        provider = current_provider
    else:
        console.print("[red]  Invalid provider.[/red]")
        return

    defaults = _PROVIDER_DEFAULTS.get(provider, ("gpt-4o", "gpt-4o-mini"))

    strong = _get_input(f"  Strong model [{defaults[0]}]: ")
    strong = strong if strong else defaults[0]

    weak = _get_input(f"  Weak model [{defaults[1]}]: ")
    weak = weak if weak else defaults[1]

    preset = ModelPreset(label=name, provider=provider, strong_model=strong, weak_model=weak)
    profiles[active_key].model_presets[key] = preset.to_dict()
    save_config(active_key, profiles)
    console.print(f"  Created preset [bold yellow]{name}[/bold yellow]")


def _handle_edit_preset(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Edit an existing custom preset."""
    profile = profiles[active_key]
    custom_keys = list(profile.model_presets.keys())

    if not custom_keys:
        console.print("[red]  No custom presets to edit. Built-in presets are immutable.[/red]")
        return

    console.print("\n  [underline]Edit Custom Preset[/underline]")
    for i, key in enumerate(custom_keys, 1):
        data = profile.model_presets[key]
        label = data.get("label", key) if isinstance(data, dict) else key
        console.print(f"  [cyan]\\[{i}][/cyan] {label}")

    choice = _get_input("\n  Select preset to edit (or q): ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(custom_keys):
            key = custom_keys[idx]
            data = profile.model_presets[key]
            preset = ModelPreset.from_dict(data) if isinstance(data, dict) else ModelPreset(label=key, provider="openai", strong_model="gpt-4o", weak_model="gpt-4o-mini")

            console.print(f"\n  Editing [bold yellow]{preset.label}[/bold yellow] (Enter to keep current)")

            new_label = _get_input(f"  Name [{preset.label}]: ")
            if new_label:
                preset.label = new_label

            console.print(f"  [cyan]\\[1][/cyan] OpenAI  [cyan]\\[2][/cyan] Anthropic  [dim](current: {preset.provider})[/dim]")
            p_choice = _get_input("  Provider: ")
            if p_choice == "1":
                preset.provider = "openai"
            elif p_choice == "2":
                preset.provider = "anthropic"

            new_strong = _get_input(f"  Strong model [{preset.strong_model}]: ")
            if new_strong:
                preset.strong_model = new_strong

            new_weak = _get_input(f"  Weak model [{preset.weak_model}]: ")
            if new_weak:
                preset.weak_model = new_weak

            profile.model_presets[key] = preset.to_dict()

            # If this is the active preset, update ai_settings too
            if profile.active_preset == key:
                jarvis.config.ai_provider = preset.provider
                jarvis.config.strong_model = preset.strong_model
                jarvis.config.weak_model = preset.weak_model
                profile.ai_settings = {
                    "ai_provider": preset.provider,
                    "strong_model": preset.strong_model,
                    "weak_model": preset.weak_model,
                }
                console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")

            save_config(active_key, profiles)
            console.print(f"  Updated preset [bold yellow]{preset.label}[/bold yellow]")
            return
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")


def _handle_delete_preset(
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Delete a custom preset."""
    profile = profiles[active_key]
    custom_keys = list(profile.model_presets.keys())

    if not custom_keys:
        console.print("[red]  No custom presets to delete.[/red]")
        return

    console.print("\n  [underline]Delete Custom Preset[/underline]")
    for i, key in enumerate(custom_keys, 1):
        data = profile.model_presets[key]
        label = data.get("label", key) if isinstance(data, dict) else key
        console.print(f"  [cyan]\\[{i}][/cyan] {label}")

    choice = _get_input("\n  Select preset to delete (or q): ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(custom_keys):
            key = custom_keys[idx]
            data = profile.model_presets[key]
            label = data.get("label", key) if isinstance(data, dict) else key
            confirm = _get_input(f"  Delete '{label}'? (y/n): ")
            if confirm.lower() == "y":
                del profile.model_presets[key]
                if profile.active_preset == key:
                    profile.active_preset = None
                save_config(active_key, profiles)
                console.print(f"  Deleted preset [bold red]{label}[/bold red]")
            return
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")


def _handle_change_provider(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Switch AI provider with sensible defaults."""
    profile = profiles[active_key]
    current = jarvis.config.ai_provider

    console.print("\n  [underline]Change AI Provider[/underline]")
    providers = ["openai", "anthropic"]
    for i, p in enumerate(providers, 1):
        marker = " [bold green]\u25c0[/bold green]" if p == current else ""
        console.print(f"  [cyan]\\[{i}][/cyan] {p}{marker}")

    choice = _get_input("\n  Select provider: ")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(providers):
            provider = providers[idx]
            defaults = _PROVIDER_DEFAULTS[provider]
            jarvis.config.ai_provider = provider
            jarvis.config.strong_model = defaults[0]
            jarvis.config.weak_model = defaults[1]
            profile.ai_settings = {
                "ai_provider": provider,
                "strong_model": defaults[0],
                "weak_model": defaults[1],
            }
            profile.active_preset = None  # Manual mode
            save_config(active_key, profiles)
            console.print(
                f"  Provider set to [bold yellow]{provider}[/bold yellow]"
                f"  ({defaults[0]} / {defaults[1]})"
            )
            if provider == "anthropic":
                console.print("  [dim]Ensure ANTHROPIC_API_KEY is set in your environment.[/dim]")
            console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
            return
    except ValueError:
        pass
    console.print("[red]  Invalid selection.[/red]")


def _handle_edit_models(
    jarvis: JarvisSystem,
    active_key: str,
    profiles: dict[str, ConfigProfile],
) -> None:
    """Directly edit the strong or weak model name."""
    profile = profiles[active_key]

    console.print("\n  [underline]Edit Models[/underline]")
    console.print(f"  [cyan]\\[1][/cyan] Strong model: {jarvis.config.strong_model}")
    console.print(f"  [cyan]\\[2][/cyan] Weak model:   {jarvis.config.weak_model}")

    choice = _get_input("\n  Select (or q): ")
    if choice == "1":
        new_model = _get_input(f"  New strong model [{jarvis.config.strong_model}]: ")
        if new_model:
            jarvis.config.strong_model = new_model
            profile.ai_settings["strong_model"] = new_model
            profile.active_preset = None
            save_config(active_key, profiles)
            console.print(f"  Strong model set to [bold yellow]{new_model}[/bold yellow]")
            console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
    elif choice == "2":
        new_model = _get_input(f"  New weak model [{jarvis.config.weak_model}]: ")
        if new_model:
            jarvis.config.weak_model = new_model
            profile.ai_settings["weak_model"] = new_model
            profile.active_preset = None
            save_config(active_key, profiles)
            console.print(f"  Weak model set to [bold yellow]{new_model}[/bold yellow]")
            console.print("  [dim]Restart Jarvis for changes to take full effect.[/dim]")
    elif choice and choice.lower() != "q":
        console.print("[red]  Invalid selection.[/red]")


def _render_model_catalog(provider: str) -> None:
    """Display known models for the current provider."""
    models = KNOWN_MODELS.get(provider, [])
    if not models:
        console.print(f"[red]  No known models for provider '{provider}'.[/red]")
        return

    table = Table(
        title=f"Known {provider.title()} Models",
        border_style="bright_blue",
    )
    table.add_column("#", style="cyan", justify="right", width=4)
    table.add_column("Model ID", min_width=28)
    table.add_column("Description", min_width=36)

    for i, (model_id, desc) in enumerate(models, 1):
        table.add_row(str(i), model_id, desc)

    console.print()
    console.print(table)
    console.print("  [dim]You can use any model string — this catalog is just a reference.[/dim]")


async def run_models_dashboard(jarvis: JarvisSystem) -> None:
    """Main entry point for the /models interactive dashboard."""
    active_key, profiles = _load_state(jarvis)

    while True:
        console.print()
        _render_dashboard(jarvis, active_key, profiles)
        _render_presets_table(profiles[active_key])
        _render_menu()

        choice = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _get_input("  > ")
        )

        if choice.lower() == "q":
            break
        elif choice.lower() == "s":
            _handle_switch_preset(jarvis, active_key, profiles)
        elif choice.lower() == "n":
            _handle_create_preset(active_key, profiles, jarvis.config.ai_provider)
        elif choice.lower() == "e":
            _handle_edit_preset(jarvis, active_key, profiles)
        elif choice.lower() == "d":
            _handle_delete_preset(active_key, profiles)
        elif choice.lower() == "p":
            _handle_change_provider(jarvis, active_key, profiles)
        elif choice.lower() == "m":
            _handle_edit_models(jarvis, active_key, profiles)
        elif choice.lower() == "c":
            _render_model_catalog(jarvis.config.ai_provider)
        else:
            console.print("[red]  Unknown command.[/red]")
