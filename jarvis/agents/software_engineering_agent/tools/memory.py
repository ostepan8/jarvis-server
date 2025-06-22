"""Memory and logging tool stubs."""
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


async def create_todo(*args, **kwargs) -> str:
    raise NotImplementedError


async def snapshot_memory(*args, **kwargs) -> str:
    raise NotImplementedError
