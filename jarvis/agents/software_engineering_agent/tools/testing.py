"""Testing tool implementations."""
from typing import Any, Dict, List

from ....services.aider_service.aider_service import AiderService
from .helpers import run_service


tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_tests",
            "description": "Generate unit tests for a source file",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_file": {"type": "string"},
                    "test_file": {"type": "string"},
                },
                "required": ["source_file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_command": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_coverage",
            "description": "Check code coverage metrics",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


async def write_tests(
    service: AiderService,
    repo_path: str,
    source_file: str,
    test_file: str | None = None,
) -> Dict[str, Any]:
    """Generate unit tests for a file."""
    return await run_service(
        service.aider.write_tests,
        repo_path=repo_path,
        source_file=source_file,
        test_file=test_file,
    )


async def run_tests(
    service: AiderService, repo_path: str, test_command: str | None = None
) -> Dict[str, Any]:
    """Run the repository test suite."""
    return await run_service(
        service.testing.run_tests,
        repo_path=repo_path,
        test_command=test_command,
    )


async def check_coverage(service: AiderService, repo_path: str) -> Dict[str, Any]:
    """Check code coverage metrics."""
    return await run_service(service.testing.run_coverage, repo_path=repo_path)
