"""Interactive kanban-style todo dashboard for the Jarvis REPL.

Launch with `/todo` or `open todo dashboard` from the main loop.
Provides a three-column board (Todo | In Progress | Done) with
keyboard-driven actions for creating, moving, and managing tasks.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from rich.console import Console
from rich.columns import Columns
from rich.panel import Panel
from jarvis.services.todo_service import TodoService, TodoItem

console = Console()

# ── Styling ──────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "todo": "bright_white",
    "in_progress": "bright_yellow",
    "done": "bright_green",
}

_PRIORITY_LABELS = {
    "urgent": ("[bold red]URGENT[/bold red]", "!!!!"),
    "high": ("[bold yellow]HIGH[/bold yellow]", "!!! "),
    "medium": ("[dim]MED[/dim]", "!!  "),
    "low": ("[dim cyan]LOW[/dim cyan]", "!   "),
}

_STATUS_HEADERS = {
    "todo": "  TODO",
    "in_progress": "  IN PROGRESS",
    "done": "  DONE",
}


def _get_input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


# ── Card rendering ───────────────────────────────────────────────────

def _render_card(item: TodoItem) -> str:
    """Render a single task card as a string block."""
    pri_label, _ = _PRIORITY_LABELS.get(item.priority.value, ("[dim]MED[/dim]", "!!  "))
    tags_str = f" [dim]#{', #'.join(item.tags)}[/dim]" if item.tags else ""
    due_str = f" [dim italic]due {item.due_date}[/dim italic]" if item.due_date else ""
    return (
        f"  [cyan]\\[{item.id}][/cyan] {pri_label}  {item.title}\n"
        f"         {tags_str}{due_str}"
    )


def _render_column(title: str, items: List[TodoItem], color: str) -> Panel:
    """Render a single status column as a Rich Panel."""
    if not items:
        body = "  [dim]No tasks[/dim]"
    else:
        cards = [_render_card(item) for item in items]
        body = "\n\n".join(cards)

    return Panel(
        body,
        title=f"[bold {color}]{title}[/bold {color}]",
        border_style=color,
        width=40,
        padding=(1, 1),
    )


def _render_board(service: TodoService) -> None:
    """Render the full kanban board."""
    todo = service.list(status="todo")
    in_progress = service.list(status="in_progress")
    done = service.list(status="done")

    cols = Columns(
        [
            _render_column(_STATUS_HEADERS["todo"], todo, _STATUS_COLORS["todo"]),
            _render_column(_STATUS_HEADERS["in_progress"], in_progress, _STATUS_COLORS["in_progress"]),
            _render_column(_STATUS_HEADERS["done"], done, _STATUS_COLORS["done"]),
        ],
        padding=(0, 1),
        expand=True,
    )

    counts = service.counts_by_status()
    total = sum(counts.values())
    header = (
        f"[bold bright_blue]Task Board[/bold bright_blue]  "
        f"[dim]({total} total — "
        f"todo:{counts['todo']}  progress:{counts['in_progress']}  done:{counts['done']})[/dim]"
    )

    console.print()
    console.print(f"  {header}")
    console.print()
    console.print(cols)


def _render_menu() -> None:
    """Render the action bar."""
    console.print(
        "\n  [cyan]\\[a][/cyan] Add task   "
        "[cyan]\\[s][/cyan] Start task   "
        "[cyan]\\[d][/cyan] Done/complete   "
        "[cyan]\\[e][/cyan] Edit task   "
        "[cyan]\\[x][/cyan] Delete task   "
        "[cyan]\\[v][/cyan] View details   "
        "[cyan]\\[f][/cyan] Filter   "
        "[cyan]\\[q][/cyan] Back\n"
    )


# ── Action handlers ──────────────────────────────────────────────────

def _handle_add(service: TodoService) -> None:
    title = _get_input("  Task title: ")
    if not title or title.lower() == "q":
        return
    desc = _get_input("  Description (optional): ")
    priority = _get_input("  Priority (urgent/high/medium/low) [medium]: ") or "medium"
    tags_raw = _get_input("  Tags (comma-separated, optional): ")
    due = _get_input("  Due date (YYYY-MM-DD, optional): ")

    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    try:
        item = service.create(
            title=title,
            description=desc,
            priority=priority,
            tags=tags,
            due_date=due or None,
        )
        console.print(f"  [green]Created:[/green] [{item.id}] {item.title}")
    except ValueError as exc:
        console.print(f"  [red]Error: {exc}[/red]")


def _handle_start(service: TodoService) -> None:
    task_id = _get_input("  Task ID to start: ")
    if not task_id or task_id.lower() == "q":
        return
    item = service.start(task_id)
    if item:
        console.print(f"  [yellow]Started:[/yellow] [{item.id}] {item.title}")
    else:
        console.print(f"  [red]Task '{task_id}' not found.[/red]")


def _handle_complete(service: TodoService) -> None:
    task_id = _get_input("  Task ID to complete: ")
    if not task_id or task_id.lower() == "q":
        return
    item = service.complete(task_id)
    if item:
        console.print(f"  [green]Completed:[/green] [{item.id}] {item.title}")
    else:
        console.print(f"  [red]Task '{task_id}' not found.[/red]")


def _handle_edit(service: TodoService) -> None:
    task_id = _get_input("  Task ID to edit: ")
    if not task_id or task_id.lower() == "q":
        return
    item = service.get(task_id)
    if not item:
        console.print(f"  [red]Task '{task_id}' not found.[/red]")
        return

    console.print(f"  Editing [{item.id}] {item.title}")
    console.print("  (press Enter to keep current value)\n")

    new_title = _get_input(f"  Title [{item.title}]: ")
    new_desc = _get_input(f"  Description [{item.description or '(none)'}]: ")
    new_priority = _get_input(f"  Priority [{item.priority.value}]: ")
    new_tags = _get_input(f"  Tags [{', '.join(item.tags)}]: ")
    new_due = _get_input(f"  Due date [{item.due_date or '(none)'}]: ")

    fields = {}
    if new_title:
        fields["title"] = new_title
    if new_desc:
        fields["description"] = new_desc
    if new_priority:
        fields["priority"] = new_priority
    if new_tags:
        fields["tags"] = [t.strip() for t in new_tags.split(",") if t.strip()]
    if new_due:
        fields["due_date"] = new_due

    if fields:
        updated = service.update(task_id, **fields)
        if updated:
            console.print(f"  [green]Updated:[/green] [{updated.id}] {updated.title}")
    else:
        console.print("  [dim]No changes.[/dim]")


def _handle_delete(service: TodoService) -> None:
    task_id = _get_input("  Task ID to delete: ")
    if not task_id or task_id.lower() == "q":
        return
    confirm = _get_input(f"  Delete task '{task_id}'? (y/n): ")
    if confirm.lower() == "y":
        if service.delete(task_id):
            console.print(f"  [red]Deleted.[/red]")
        else:
            console.print(f"  [red]Task '{task_id}' not found.[/red]")


def _handle_view(service: TodoService) -> None:
    task_id = _get_input("  Task ID: ")
    if not task_id or task_id.lower() == "q":
        return
    item = service.get(task_id)
    if not item:
        console.print(f"  [red]Task '{task_id}' not found.[/red]")
        return

    pri_label, _ = _PRIORITY_LABELS.get(item.priority.value, ("[dim]MED[/dim]", "!!  "))
    tags_str = ", ".join(item.tags) if item.tags else "(none)"
    body = (
        f"  Title:       {item.title}\n"
        f"  Status:      {item.status.value}\n"
        f"  Priority:    {item.priority.value}\n"
        f"  Tags:        {tags_str}\n"
        f"  Due:         {item.due_date or '(none)'}\n"
        f"  Description: {item.description or '(none)'}\n"
        f"  Created:     {item.created_at}\n"
        f"  Updated:     {item.updated_at}"
    )
    console.print(Panel(body, title=f"[cyan]Task {item.id}[/cyan]", border_style="cyan"))


def _handle_filter(service: TodoService) -> None:
    console.print("\n  [underline]Filter tasks[/underline]")
    console.print("  [cyan]\\[1][/cyan] By priority")
    console.print("  [cyan]\\[2][/cyan] By tag")
    console.print("  [cyan]\\[3][/cyan] Show all")

    choice = _get_input("\n  > ")
    if choice == "1":
        priority = _get_input("  Priority (urgent/high/medium/low): ")
        items = service.list(priority=priority)
    elif choice == "2":
        tag = _get_input("  Tag: ")
        items = service.list(tag=tag)
    elif choice == "3":
        items = service.list()
    else:
        return

    if not items:
        console.print("  [dim]No matching tasks.[/dim]")
        return

    for item in items:
        pri_label, _ = _PRIORITY_LABELS.get(item.priority.value, ("[dim]MED[/dim]", "!!  "))
        status_icon = {"todo": "○", "in_progress": "◐", "done": "●"}[item.status.value]
        console.print(f"  {status_icon} [{item.id}] {pri_label} {item.title}")


# ── Main loop ────────────────────────────────────────────────────────

async def run_todo_dashboard(service: Optional[TodoService] = None) -> None:
    """Main entry point for the interactive todo dashboard."""
    if service is None:
        service = TodoService()

    while True:
        _render_board(service)
        _render_menu()

        choice = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _get_input("  > ")
        )

        if choice.lower() == "q":
            break
        elif choice.lower() == "a":
            _handle_add(service)
        elif choice.lower() == "s":
            _handle_start(service)
        elif choice.lower() == "d":
            _handle_complete(service)
        elif choice.lower() == "e":
            _handle_edit(service)
        elif choice.lower() == "x":
            _handle_delete(service)
        elif choice.lower() == "v":
            _handle_view(service)
        elif choice.lower() == "f":
            _handle_filter(service)
        else:
            console.print("  [red]Unknown command.[/red]")
