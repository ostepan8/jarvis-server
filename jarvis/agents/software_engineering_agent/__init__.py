from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Dict, List, Optional

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient
from ...services.aider_service import AiderService, create_aider_service
from .tools import (
    code_tools,
    testing_tools,
    git_tools,
    github_tools,
    filesystem_tools,
    memory_tools,
)


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
            code_tools
            + testing_tools
            + git_tools
            + github_tools
            + filesystem_tools
            + memory_tools
        )

        self.system_prompt = (
            "You are SoftwareEngineeringAgent, an AI that manages codebases. "
            "Respond to developer requests by selecting and executing the proper tools. "
            "Use only the tools provided. Keep responses concise."
        )

        # Map tool names to bound methods for execution
        self.intent_map = {
            "generate_function": self.generate_function,
            "refactor_code": self.refactor_code,
            "add_documentation": self.add_documentation,
            "explain_code": self.explain_code,
            "write_tests": self.write_tests,
            "run_tests": self.run_tests,
            "check_coverage": self.check_coverage,
            "git_diff": self.git_diff,
            "git_commit": self.git_commit,
            "git_push": self.git_push,
            "create_pull_request": self.create_pull_request,
            "merge_pull_request": self.merge_pull_request,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_directory": self.list_directory,
            "create_todo": self.create_todo,
            "snapshot_memory": self.snapshot_memory,
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

    async def _run_service(self, func: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Run a blocking service method in an executor and return dict output."""
        loop = asyncio.get_running_loop()

        def call() -> Dict[str, Any]:
            result = func(*args, **kwargs)
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result

        return await loop.run_in_executor(None, call)

    # === Tool method implementations ===
    async def generate_function(self, spec: str, file_path: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.aider.send_message,
            repo_path=self.repo_path,
            message=spec,
            files=[file_path],
        )

    async def refactor_code(self, file_path: str, instructions: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.aider.refactor_code,
            repo_path=self.repo_path,
            file_path=file_path,
            refactor_description=instructions,
        )

    async def add_documentation(self, file_path: str, target: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.aider.document_code,
            repo_path=self.repo_path,
            file_path=file_path,
        )

    async def explain_code(self, file_path: str, target: Optional[str] = None) -> Dict[str, Any]:
        return await self._run_service(
            self.service.aider.explain_code,
            repo_path=self.repo_path,
            file_path=file_path,
            function_or_class_name=target,
        )

    async def write_tests(self, source_file: str, test_file: Optional[str] = None) -> Dict[str, Any]:
        return await self._run_service(
            self.service.aider.write_tests,
            repo_path=self.repo_path,
            source_file=source_file,
            test_file=test_file,
        )

    async def run_tests(self, test_command: Optional[str] = None) -> Dict[str, Any]:
        return await self._run_service(
            self.service.testing.run_tests,
            repo_path=self.repo_path,
            test_command=test_command,
        )

    async def check_coverage(self) -> Dict[str, Any]:
        return await self._run_service(
            self.service.testing.run_coverage,
            repo_path=self.repo_path,
        )

    async def git_diff(self) -> Dict[str, Any]:
        return await self._run_service(
            self.service.git.diff,
            repo_path=self.repo_path,
        )

    async def git_commit(self, message: Optional[str] = None) -> Dict[str, Any]:
        commit_msg = message or "Auto commit"
        return await self._run_service(
            self.service.git.commit,
            repo_path=self.repo_path,
            message=commit_msg,
        )

    async def git_push(self) -> Dict[str, Any]:
        return await self._run_service(self.service.git.push, repo_path=self.repo_path)

    async def create_pull_request(self, title: str, body: str) -> Dict[str, Any]:
        if not self.service.is_github_available:
            return {"error": "GitHub operations not available"}
        return await self._run_service(
            self.service.github.create_pr,
            repo_path=self.repo_path,
            title=title,
            body=body,
        )

    async def merge_pull_request(self, pr_number: int) -> Dict[str, Any]:
        if not self.service.is_github_available:
            return {"error": "GitHub operations not available"}
        return await self._run_service(
            self.service.github.merge_pr,
            repo_path=self.repo_path,
            pr_number=pr_number,
        )

    async def read_file(self, path: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.files.read_file,
            repo_path=self.repo_path,
            file_path=path,
        )

    async def write_file(self, path: str, contents: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.files.write_file,
            repo_path=self.repo_path,
            file_path=path,
            content=contents,
        )

    async def list_directory(self, path: str) -> Dict[str, Any]:
        return await self._run_service(
            self.service.files.list_directory,
            repo_path=self.repo_path,
            dir_path=path,
        )

    async def create_todo(self, text: str) -> Dict[str, Any]:
        self.todos.append(text)
        return {"todo": text}

    async def snapshot_memory(self) -> Dict[str, Any]:
        return {"todos": list(self.todos)}

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
