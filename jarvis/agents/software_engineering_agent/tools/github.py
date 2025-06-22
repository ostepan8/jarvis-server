"""GitHub operation tool implementations."""
from typing import Any, Dict, List

from ....services.aider_service.aider_service import AiderService
from .helpers import run_service


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


async def create_pull_request(
    service: AiderService, repo_path: str, title: str, body: str
) -> Dict[str, Any]:
    """Create a pull request on GitHub."""
    if not service.is_github_available:
        return {"error": "GitHub operations not available"}
    return await run_service(
        service.github.create_pr,
        repo_path=repo_path,
        title=title,
        body=body,
    )


async def merge_pull_request(
    service: AiderService, repo_path: str, pr_number: int
) -> Dict[str, Any]:
    """Merge an existing pull request."""
    if not service.is_github_available:
        return {"error": "GitHub operations not available"}
    return await run_service(
        service.github.merge_pr,
        repo_path=repo_path,
        pr_number=pr_number,
    )
