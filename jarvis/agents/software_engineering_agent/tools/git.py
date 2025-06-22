"""Git operation tool implementations."""
from typing import Any, Dict, List

from ....services.aider_service.aider_service import AiderService
from .helpers import run_service


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


async def git_diff(service: AiderService, repo_path: str) -> Dict[str, Any]:
    """Return ``git diff`` output."""
    return await run_service(service.git.diff, repo_path=repo_path)


async def git_commit(
    service: AiderService, repo_path: str, message: str | None = None
) -> Dict[str, Any]:
    """Create a git commit."""
    commit_msg = message or "Auto commit"
    return await run_service(
        service.git.commit, repo_path=repo_path, message=commit_msg
    )


async def git_push(service: AiderService, repo_path: str) -> Dict[str, Any]:
    """Push commits to the remote repository."""
    return await run_service(service.git.push, repo_path=repo_path)
