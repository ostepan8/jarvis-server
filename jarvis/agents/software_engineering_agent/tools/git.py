"""Git operation tool stubs."""
from typing import Any, Dict, List


tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Commit staged changes",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push commits to remote",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


async def git_diff(*args, **kwargs) -> str:
    raise NotImplementedError


async def git_commit(*args, **kwargs) -> str:
    raise NotImplementedError


async def git_push(*args, **kwargs) -> str:
    raise NotImplementedError
