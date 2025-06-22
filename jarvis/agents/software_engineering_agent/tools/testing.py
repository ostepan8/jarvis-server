"""Testing tool stubs."""
from typing import Any, Dict, List


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


async def write_tests(*args, **kwargs) -> str:
    raise NotImplementedError


async def run_tests(*args, **kwargs) -> str:
    raise NotImplementedError


async def check_coverage(*args, **kwargs) -> str:
    raise NotImplementedError
