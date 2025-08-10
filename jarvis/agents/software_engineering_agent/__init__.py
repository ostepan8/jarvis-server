from __future__ import annotations

import asyncio
import functools
import json
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient

from .tools import code, testing, git, github, filesystem, memory
from .tools.helpers import run_service


class SoftwareEngineeringAgent(NetworkAgent):
    """Agent for automating software development workflows."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        repo_path: str,
        logger: Optional[JarvisLogger] = None,
        # aider_service: Optional[AiderService] = None,
    ) -> None:
        super().__init__("SoftwareEngineeringAgent", logger)
        self.ai_client = ai_client
        self.repo_path = repo_path
        # self.service = aider_service or create_aider_service()
        self.todos: List[str] = []
        self.private_capabilities: Set[str] = {
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
        return "Handles software development tasks using Aider AI."

    @property
    def capabilities(self) -> set[str]:
        """High-level capabilities that match natural user requests."""
        return {"aider_software_agent_command"}

    # async def _send_to_aider(self, command: str) -> str:
    #     """Send command to Aider and return clean response."""
    #     try:
    #         self.logger.log("INFO", f"Sending to Aider: {command}")
    #         enhanced_command = (
    #             f"{command}. Please proceed without asking for confirmation."
    #         )

    #         result = await run_service(
    #             self.service.aider.send_message,
    #             repo_path=self.repo_path,
    #             message=command,
    #             files=[],
    #         )

    #         if (
    #             isinstance(result, dict)
    #             and result.get("success")
    #             and result.get("stdout")
    #         ):
    #             # Clean up the Aider output - remove the startup junk
    #             stdout = result["stdout"]

    #             # Split by lines and find where the actual response starts
    #             lines = stdout.split("\n")

    #             # Skip Aider startup lines (the ones with dashes, version info, etc.)
    #             start_idx = 0
    #             for i, line in enumerate(lines):
    #                 if line.strip() and not any(
    #                     skip in line
    #                     for skip in [
    #                         "────",
    #                         "Using gpt-",
    #                         "Aider v",
    #                         "Main model:",
    #                         "Weak model:",
    #                         "Repo-map:",
    #                         "Tokens:",
    #                         "Cost:",
    #                     ]
    #                 ):
    #                     start_idx = i
    #                     break

    #             # Join the actual response lines
    #             clean_response = "\n".join(lines[start_idx:]).strip()

    #             # Remove any trailing token/cost info
    #             clean_lines = []
    #             for line in clean_response.split("\n"):
    #                 if not any(skip in line for skip in ["Tokens:", "Cost:"]):
    #                     clean_lines.append(line)

    #             return "\n".join(clean_lines).strip()

    #         else:
    #             return result.get("error_message", "No response from Aider")

    #     except Exception as exc:
    #         self.logger.log("ERROR", f"Aider failed: {str(exc)}")
    #         return f"Error: {str(exc)}"

    # async def _handle_capability_request(self, message: Message) -> None:
    #     """Handle all capability requests by sending to Aider."""
    #     command = message.content.get("data", {}).get("prompt", "")

    #     if not command:
    #         await self.send_error(
    #             message.from_agent, "No command provided", message.request_id
    #         )
    #         return

    #     # Send directly to Aider - no modifications, no logic
    #     response = await self._send_to_aider(command)

    #     await self.send_capability_response(
    #         message.from_agent, {"response": response}, message.request_id, message.id
    #     )

    # async def _handle_capability_response(self, message: Message) -> None:
    #     pass


# from __future__ import annotations

# import asyncio
# import functools
# import json
# from typing import Any, Dict, List, Optional

# from ..base import NetworkAgent
# from ..message import Message
# from ...logger import JarvisLogger
# from ...ai_clients.base import BaseAIClient
# from ...services.aider_service.aider_service import (
#     AiderService,
#     create_aider_service,
# )
# from .tools import code, testing, git, github, filesystem, memory


# class SoftwareEngineeringAgent(NetworkAgent):
#     """Agent for automating software development workflows."""

#     def __init__(
#         self,
#         ai_client: BaseAIClient,
#         repo_path: str,
#         logger: Optional[JarvisLogger] = None,
#         aider_service: Optional[AiderService] = None,
#     ) -> None:
#         super().__init__("SoftwareEngineeringAgent", logger)
#         self.ai_client = ai_client
#         self.repo_path = repo_path
#         self.service = aider_service or create_aider_service()
#         self.todos: List[str] = []

#         # Aggregate all tool schemas
#         self.tools: List[Dict[str, Any]] = (
#             code.tools
#             + testing.tools
#             + git.tools
#             + github.tools
#             + filesystem.tools
#             + memory.tools
#         )

#         self.system_prompt = (
#             "You are SoftwareEngineeringAgent, an AI that manages codebases. "
#             "Respond to developer requests by selecting and executing the proper tools. "
#             "Use only the tools provided. Keep responses concise."
#         )

#         # Map tool names to bound functions for execution
#         self.intent_map = {
#             "generate_function": functools.partial(
#                 code.generate_function, self.service, self.repo_path
#             ),
#             "refactor_code": functools.partial(
#                 code.refactor_code, self.service, self.repo_path
#             ),
#             "add_documentation": functools.partial(
#                 code.add_documentation, self.service, self.repo_path
#             ),
#             "explain_code": functools.partial(
#                 code.explain_code, self.service, self.repo_path
#             ),
#             "write_tests": functools.partial(
#                 testing.write_tests, self.service, self.repo_path
#             ),
#             "run_tests": functools.partial(
#                 testing.run_tests, self.service, self.repo_path
#             ),
#             "check_coverage": functools.partial(
#                 testing.check_coverage, self.service, self.repo_path
#             ),
#             "git_diff": functools.partial(git.git_diff, self.service, self.repo_path),
#             "git_commit": functools.partial(
#                 git.git_commit, self.service, self.repo_path
#             ),
#             "git_push": functools.partial(git.git_push, self.service, self.repo_path),
#             "create_pull_request": functools.partial(
#                 github.create_pull_request, self.service, self.repo_path
#             ),
#             "merge_pull_request": functools.partial(
#                 github.merge_pull_request, self.service, self.repo_path
#             ),
#             "read_file": functools.partial(
#                 filesystem.read_file, self.service, self.repo_path
#             ),
#             "write_file": functools.partial(
#                 filesystem.write_file, self.service, self.repo_path
#             ),
#             "list_directory": functools.partial(
#                 filesystem.list_directory, self.service, self.repo_path
#             ),
#             "create_todo": functools.partial(memory.create_todo, self.todos),
#             "snapshot_memory": functools.partial(memory.snapshot_memory, self.todos),
#         }

#     @property
#     def description(self) -> str:
#         return "Automates code generation, testing, and Git/GitHub tasks."

#     @property
#     def capabilities(self) -> set[str]:
#         return {
#             "software_command",
#             "generate_function",
#             "refactor_code",
#             "add_documentation",
#             "explain_code",
#             "write_tests",
#             "run_tests",
#             "check_coverage",
#             "git_diff",
#             "git_commit",
#             "git_push",
#             "create_pull_request",
#             "merge_pull_request",
#             "read_file",
#             "write_file",
#             "list_directory",
#             "create_todo",
#             "snapshot_memory",
#         }

#     async def _execute_function(self, name: str, args: Dict[str, Any]) -> Any:
#         """Execute a tool function via the intent map."""
#         func = self.intent_map.get(name)
#         if not func:
#             return {"error": f"Unknown tool {name}"}

#         print(f"Function name: {name}, Arguments: {args}")
#         self.logger.log("INFO", f"Executing function {name}", f"arguments: {args}")

#         try:
#             result = await func(**args)
#         except Exception as exc:
#             self.logger.log("ERROR", f"Function {name} failed", str(exc))
#             result = {"error": str(exc)}
#         return result

#     async def _process_dev_command(self, command: str) -> Dict[str, Any]:
#         """Run a developer instruction through the AI model and execute tools."""
#         messages = [
#             {"role": "system", "content": self.system_prompt},
#             {"role": "user", "content": command},
#         ]
#         actions: List[Dict[str, Any]] = []
#         iterations = 0
#         MAX_ITERS = 10

#         while iterations < MAX_ITERS:
#             message, tool_calls = await self.ai_client.chat(messages, self.tools)
#             print(
#                 f"Iteration {iterations}: Received message: {message} and tool_calls: {tool_calls}"
#             )
#             if not tool_calls:
#                 break

#             messages.append(message.model_dump())
#             for call in tool_calls:
#                 name = call.function.name
#                 args = json.loads(call.function.arguments)
#                 print(f"Calling tool: {name} with arguments: {args}")
#                 result = await self._execute_function(name, args)
#                 print(f"Result from tool {name}: {result}")
#                 actions.append({"function": name, "arguments": args, "result": result})
#                 messages.append(
#                     {
#                         "role": "tool",
#                         "tool_call_id": call.id,
#                         "content": json.dumps(result),
#                     }
#                 )
#             iterations += 1

#         response_text = getattr(message, "content", "")
#         print(
#             f"Finished processing command. Final response: {response_text}, actions: {actions}"
#         )
#         return {"response": response_text, "actions": actions}

#     async def _handle_capability_request(self, message: Message) -> None:
#         command = message.content.get("data", {}).get("command", "")

#         # Just send it directly to Aider
#         result = await self.service.aider.send_message(
#             repo_path=self.repo_path, message=command
#         )

#         await self.send_capability_response(
#             message.from_agent, result, message.request_id, message.id
#         )

#     # async def _handle_capability_request(self, message: Message) -> None:
#     #     """Handle incoming capability requests."""
#     #     self.logger.log(
#     #         "INFO",
#     #         f"SWE Agent received capability request",
#     #         f"content: {message.content}",
#     #     )

#     #     capability = message.content.get("capability")
#     #     data = message.content.get("data", {})

#     #     try:
#     #         if capability == "software_command":
#     #             command = data.get("command")
#     #             if not isinstance(command, str):
#     #                 await self.send_error(
#     #                     message.from_agent, "Invalid command", message.request_id
#     #                 )
#     #                 return
#     #             result = await self._process_dev_command(command)

#     #         elif capability in self.intent_map:
#     #             # For direct capability calls, pass the command as parameter
#     #             command = data.get("command", "")
#     #             if capability == "explain_code":
#     #                 # For explain_code, if no specific file is mentioned, explain the whole codebase
#     #                 result = await self._execute_function(
#     #                     capability, {"command": command}
#     #                 )
#     #             else:
#     #                 result = await self._execute_function(capability, data)

#     #         else:
#     #             self.logger.log("WARNING", f"Unknown capability: {capability}")
#     #             await self.send_error(
#     #                 message.from_agent,
#     #                 f"Unknown capability: {capability}",
#     #                 message.request_id,
#     #             )
#     #             return

#     #         self.logger.log(
#     #             "DEBUG",
#     #             f"SWE Agent sending response",
#     #             f"result keys: {result.keys() if isinstance(result, dict) else type(result)}",
#     #         )

#     #         await self.send_capability_response(
#     #             message.from_agent, result, message.request_id, message.id
#     #         )

#     #     except Exception as exc:
#     #         self.logger.log("ERROR", f"SWE Agent error handling {capability}", str(exc))
#     #         await self.send_error(message.from_agent, str(exc), message.request_id)

#     async def _handle_capability_response(self, message: Message) -> None:
#         pass
