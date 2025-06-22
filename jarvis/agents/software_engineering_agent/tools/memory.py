"""Memory and logging tool implementations."""

from typing import Any, Dict, List


tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "Create a TODO item",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "snapshot_memory",
            "description": "Snapshot agent state for later retrieval",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def create_todo(todos: List[str], text: str) -> Dict[str, Any]:  # Remove async
    """Add a todo item to the in-memory list."""
    todos.append(text)
    return {"todo": text}


def snapshot_memory(todos: List[str]) -> Dict[str, Any]:  # Remove async
    """Return a snapshot of stored todo items."""
    return {"todos": list(todos)}
