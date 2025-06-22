from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Dict, List, Optional

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient
from ...services.aider_service.aider_service import (
    AiderService,
    create_aider_service,
)
from .tools import code, testing, git, github, filesystem, memory


class SoftwareEngineeringAgent(NetworkAgent):
    """Agent for automating software development workflows."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        repo_path: str,
        logger: Optional[JarvisLogger] = None,
        aider_service: Optional[AiderService] = None,
    ) -> None:
        super().__init__("SoftwareEngineeringAgent", logger)
        self.ai_client = ai_client
        self.repo_path = repo_path
        self.service = aider_service or create_aider_service()
        self.todos: List[str] = []

        # Aggregate all tool schemas
        self.tools: List[Dict[str, Any]] = (
            code.tools
            + testing.tools
            + git.tools
            + github.tools
            + filesystem.tools
            + memory.tools
        )

        self.system_prompt = (
            "You are SoftwareEngineeringAgent, an AI that manages codebases. "
            "Respond to developer requests by selecting and executing the proper tools. "
            "Use only the tools provided. Keep responses concise."
        )

        # Map tool names to bound functions for execution
        self.intent_map = {
            "generate_function": functools.partial(
                code.generate_function, self.service, self.repo_path
            ),
            "refactor_code": functools.partial(
                code.refactor_code, self.service, self.repo_path
            ),
            "add_documentation": functools.partial(
                code.add_documentation, self.service, self.repo_path
            ),
            "explain_code": functools.partial(
                code.explain_code, self.service, self.repo_path
            ),
            "write_tests": functools.partial(
                testing.write_tests, self.service, self.repo_path
            ),
            "run_tests": functools.partial(
                testing.run_tests, self.service, self.repo_path
            ),
            "check_coverage": functools.partial(
                testing.check_coverage, self.service, self.repo_path
            ),
            "git_diff": functools.partial(git.git_diff, self.service, self.repo_path),
            "git_commit": functools.partial(
                git.git_commit, self.service, self.repo_path
            ),
            "git_push": functools.partial(git.git_push, self.service, self.repo_path),
            "create_pull_request": functools.partial(
                github.create_pull_request, self.service, self.repo_path
            ),
            "merge_pull_request": functools.partial(
                github.merge_pull_request, self.service, self.repo_path
            ),
            "read_file": functools.partial(
                filesystem.read_file, self.service, self.repo_path
            ),
            "write_file": functools.partial(
                filesystem.write_file, self.service, self.repo_path
            ),
            "list_directory": functools.partial(
                filesystem.list_directory, self.service, self.repo_path
            ),
            "create_todo": functools.partial(memory.create_todo, self.todos),
            "snapshot_memory": functools.partial(memory.snapshot_memory, self.todos),
        }

    @property
    def description(self) -> str:
        return "Automates code generation, testing, and Git/GitHub tasks."

    @property
    def capabilities(self) -> set[str]:
        return {
            "software_command",
            "generate_function",
            "refactor_code",
            "add_documentation",
            "explain_code",
            "write_tests",
            "run_tests",
            "check_coverage",
            "git_diff",
            "git_commit",
            "git_push",
            "create_pull_request",
            "merge_pull_request",
            "read_file",
            "write_file",
            "list_directory",
            "create_todo",
            "snapshot_memory",
        }

    async def _execute_function(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute a tool function via the intent map."""
        func = self.intent_map.get(name)
        if not func:
            return {"error": f"Unknown tool {name}"}

        loop = asyncio.get_running_loop()
        try:
            call = functools.partial(func, **args)
            result = await loop.run_in_executor(None, call)
        except Exception as exc:  # pragma: no cover - placeholder
            result = {"error": str(exc)}
        return result

    async def _process_dev_command(self, command: str) -> Dict[str, Any]:
        """Run a developer instruction through the AI model and execute tools."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": command},
        ]
        actions: List[Dict[str, Any]] = []
        iterations = 0
        MAX_ITERS = 10

        while iterations < MAX_ITERS:
            message, tool_calls = await self.ai_client.chat(messages, self.tools)
            if not tool_calls:
                break

            messages.append(message.model_dump())
            for call in tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments)
                result = await self._execute_function(name, args)
                actions.append({"function": name, "arguments": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
            iterations += 1

        response_text = getattr(message, "content", "")
        return {"response": response_text, "actions": actions}


    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability == "software_command":
            command = data.get("command")
            if not isinstance(command, str):
                await self.send_error(message.from_agent, "Invalid command", message.request_id)
                return
            result = await self._process_dev_command(command)
        elif capability in self.intent_map:
            result = await self._execute_function(capability, data)
        else:
            return

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass
