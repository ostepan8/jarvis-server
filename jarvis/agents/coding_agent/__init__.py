"""CodingAgent — the hands that type when you'd rather not.

Capabilities:
    implement_feature — build new features, agents, services, endpoints
    fix_bug          — diagnose and fix bugs in the codebase
    write_tests      — generate or expand test coverage
    explain_code     — explain how code works, trace call paths
    refactor_code    — restructure code without changing behavior
    run_code         — execute arbitrary shell commands or scripts
    edit_file        — modify an existing file
    read_file        — read file contents
    create_file      — create a new file or directory
    list_files       — list files and directories

Delegates to Claude Code CLI with --dangerously-skip-permissions for full
autonomous execution. This is the primary fallback agent for anything
involving files, code, or system operations.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...logging import JarvisLogger


# Every capability this agent owns.
CAPABILITIES: Set[str] = {
    "implement_feature",
    "fix_bug",
    "write_tests",
    "explain_code",
    "refactor_code",
    "run_code",
    "edit_file",
    "read_file",
    "create_file",
    "list_files",
}

# Maximum time (seconds) for a single Claude Code invocation.
_DEFAULT_TIMEOUT = 600


class CodingAgent(NetworkAgent):
    """Full-stack coding agent backed by Claude Code CLI.

    Routes every coding, file, and system request through the Claude Code
    CLI running with ``--dangerously-skip-permissions``, giving it the same
    power as an interactive session — reads, writes, shell commands, the lot.
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        claude_binary: str = "claude",
        logger: Optional[JarvisLogger] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__("CodingAgent", logger)
        self.project_root = project_root or str(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        self.claude_binary = claude_binary
        self.timeout = timeout
        self.intent_map: Dict[str, Any] = {cap: self._execute for cap in CAPABILITIES}

    @property
    def description(self) -> str:
        return (
            "Full-stack coding agent — implements features, fixes bugs, writes tests, "
            "explains code, refactors, and handles all file and system operations. "
            "The primary fallback for anything involving code or files."
        )

    @property
    def capabilities(self) -> Set[str]:
        return CAPABILITIES

    @property
    def supports_dialogue(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Network message handler
    # ------------------------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in CAPABILITIES:
            await self.send_error(
                message.from_agent,
                f"Unknown capability: {capability}",
                message.request_id,
            )
            return

        self.logger.log(
            "INFO",
            f"CodingAgent handling: {capability}",
            str(data)[:200],
        )

        try:
            prompt = data.get("prompt", "")
            result = await self._execute(prompt=prompt, capability=capability)
            await self.send_capability_response(
                message.from_agent,
                result.to_dict(),
                message.request_id,
                message.id,
            )
        except Exception as exc:
            self.logger.log("ERROR", "CodingAgent error", str(exc))
            err = AgentResponse.from_exception(
                exc, "The coding agent encountered an issue mid-operation."
            )
            await self.send_capability_response(
                message.from_agent,
                err.to_dict(),
                message.request_id,
                message.id,
            )

    async def _handle_capability_response(self, message: Message) -> None:  # noqa: ARG002
        pass  # CodingAgent does not issue sub-requests

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        prompt: str = "",
        capability: str = "",
    ) -> AgentResponse:
        """Run a task through the Claude Code CLI.

        Builds a capability-aware system preamble, then hands the full
        prompt to ``claude -p --dangerously-skip-permissions``.
        """
        if not prompt:
            return AgentResponse.error_response(
                "No prompt provided. Even I need instructions.",
                ErrorInfo(message="Empty prompt"),
            )

        system_preamble = self._build_preamble(capability)
        full_prompt = f"{system_preamble}\n\nUSER REQUEST:\n{prompt}"

        self.logger.log(
            "INFO",
            f"CodingAgent invoking Claude Code ({capability})",
            f"project_root={self.project_root}",
        )

        start = time.monotonic()
        result = await self._run_claude(full_prompt)
        duration = round(time.monotonic() - start, 2)

        if result["success"]:
            return AgentResponse.success_response(
                response=result["stdout"],
                actions=[
                    {
                        "type": capability or "coding_task",
                        "details": {
                            "duration_seconds": duration,
                            "exit_code": result["exit_code"],
                        },
                    }
                ],
                data={"raw_output": result["stdout"]},
                metadata={"agent": "CodingAgent", "capability": capability},
            )
        else:
            return AgentResponse.error_response(
                response=result["stderr"] or result["stdout"] or "Claude Code returned an error.",
                error=ErrorInfo(
                    message=f"Exit code {result['exit_code']}",
                    error_type="ClaudeCodeError",
                    details={
                        "exit_code": result["exit_code"],
                        "stderr": result["stderr"][:500],
                        "duration_seconds": duration,
                    },
                ),
            )

    async def _run_claude(self, prompt: str) -> Dict[str, Any]:
        """Invoke the Claude Code CLI as a subprocess.

        Strips the ``CLAUDECODE`` environment variable so nested
        invocations work correctly from within an existing session.
        """
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        cmd = [
            self.claude_binary,
            "-p",
            "--dangerously-skip-permissions",
            prompt,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_root,
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Timed out after {self.timeout}s",
                    "exit_code": -1,
                }
            except asyncio.CancelledError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                raise

            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")

            return {
                "success": process.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": process.returncode or 0,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    f"Claude CLI binary '{self.claude_binary}' not found. "
                    "Ensure Claude Code is installed and on the PATH."
                ),
                "exit_code": -127,
            }

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_preamble(capability: str) -> str:
        """Build a capability-specific system preamble for the CLI prompt."""
        base = (
            "You are an autonomous coding agent operating inside the Jarvis project. "
            "You have full access to the filesystem and shell. "
            "Be precise, minimal, and correct. "
            "Always explain what you changed and why."
        )

        guidance = {
            "implement_feature": (
                "Implement the requested feature. Create any necessary files, "
                "write tests alongside the implementation, and commit with a "
                "conventional commit message."
            ),
            "fix_bug": (
                "Diagnose and fix the reported bug. Read the relevant code, "
                "identify the root cause, apply the minimal fix, add a "
                "regression test, and commit."
            ),
            "write_tests": (
                "Write comprehensive tests for the specified code. Use pytest "
                "and pytest-asyncio. Cover happy paths, edge cases, and error "
                "conditions. Follow existing test patterns in the project."
            ),
            "explain_code": (
                "Read the relevant code and provide a clear, detailed explanation "
                "of how it works. Include call flow, data structures, and any "
                "non-obvious design decisions. Do not modify any files."
            ),
            "refactor_code": (
                "Refactor the specified code for clarity and maintainability. "
                "Preserve all existing behavior — tests must still pass. "
                "Commit with a descriptive message."
            ),
            "run_code": (
                "Execute the requested command or script. Return the full output. "
                "If the command modifies state, confirm what changed."
            ),
            "edit_file": (
                "Edit the specified file as requested. Make only the changes "
                "described — no additional cleanup or refactoring."
            ),
            "read_file": (
                "Read and return the contents of the specified file. "
                "Do not modify anything."
            ),
            "create_file": (
                "Create the specified file or directory. If creating a file, "
                "populate it with the requested content."
            ),
            "list_files": (
                "List the files and directories at the specified path. "
                "Show structure clearly."
            ),
        }

        specific = guidance.get(capability, "")
        if specific:
            return f"{base}\n\nTASK TYPE: {capability}\n{specific}"
        return base
