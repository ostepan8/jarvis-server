"""GitHub operation tool stubs."""
from typing import Any, Dict, List


tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_pull_request",
            "description": "Create a pull request",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_pull_request",
            "description": "Merge an existing pull request",
            "parameters": {
                "type": "object",
                "properties": {"pr_number": {"type": "integer"}},
                "required": ["pr_number"],
            },
        },
    },
]


async def create_pull_request(*args, **kwargs) -> str:
    raise NotImplementedError


async def merge_pull_request(*args, **kwargs) -> str:
    raise NotImplementedError
