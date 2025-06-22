"""Code manipulation tool implementations."""
from typing import Any, Dict, List

from ....services.aider_service.aider_service import AiderService
from .helpers import run_service

# Tool schema definitions

tools: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "generate_function",
            "description": "Generate a new Python function in the specified file",
            "parameters": {
                "type": "object",
                "properties": {
                    "spec": {"type": "string", "description": "Function specification"},
                    "file_path": {"type": "string", "description": "File path"},
                },
                "required": ["spec", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refactor_code",
            "description": "Refactor code in a file according to instructions",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "instructions": {"type": "string"},
                },
                "required": ["file_path", "instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_documentation",
            "description": "Add documentation to a file or function",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "target": {"type": "string", "description": "Function or section"},
                },
                "required": ["file_path", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_code",
            "description": "Explain selected code",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "target": {"type": "string", "description": "Optional function or class"},
                },
                "required": ["file_path"],
            },
        },
    },
]


async def generate_function(
    service: AiderService, repo_path: str, spec: str, file_path: str
) -> Dict[str, Any]:
    """Generate a new function using the aider service."""
    return await run_service(
        service.aider.send_message,
        repo_path=repo_path,
        message=spec,
        files=[file_path],
    )


async def refactor_code(
    service: AiderService, repo_path: str, file_path: str, instructions: str
) -> Dict[str, Any]:
    """Refactor code in ``file_path`` according to ``instructions``."""
    return await run_service(
        service.aider.refactor_code,
        repo_path=repo_path,
        file_path=file_path,
        refactor_description=instructions,
    )


async def add_documentation(
    service: AiderService, repo_path: str, file_path: str, target: str
) -> Dict[str, Any]:
    """Add documentation to ``file_path``."""
    return await run_service(
        service.aider.document_code,
        repo_path=repo_path,
        file_path=file_path,
    )


async def explain_code(
    service: AiderService,
    repo_path: str,
    file_path: str,
    target: str | None = None,
) -> Dict[str, Any]:
    """Explain selected code."""
    return await run_service(
        service.aider.explain_code,
        repo_path=repo_path,
        file_path=file_path,
        function_or_class_name=target,
    )
