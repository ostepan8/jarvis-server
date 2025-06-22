"""Filesystem tool implementations."""
from typing import Any, Dict, List

from ....services.aider_service.aider_service import AiderService
from .helpers import run_service


tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write contents to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "contents": {"type": "string"},
                },
                "required": ["path", "contents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List directory entries",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


async def read_file(
    service: AiderService, repo_path: str, path: str
) -> Dict[str, Any]:
    """Read file contents."""
    return await run_service(
        service.files.read_file,
        repo_path=repo_path,
        file_path=path,
    )


async def write_file(
    service: AiderService, repo_path: str, path: str, contents: str
) -> Dict[str, Any]:
    """Write data to ``path``."""
    return await run_service(
        service.files.write_file,
        repo_path=repo_path,
        file_path=path,
        content=contents,
    )


async def list_directory(
    service: AiderService, repo_path: str, path: str
) -> Dict[str, Any]:
    """List directory entries."""
    return await run_service(
        service.files.list_directory,
        repo_path=repo_path,
        dir_path=path,
    )
