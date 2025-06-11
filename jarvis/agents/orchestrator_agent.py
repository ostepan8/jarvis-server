from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from .base import NetworkAgent
from .message import Message
from .task import Task
from ..ai_clients import BaseAIClient
from ..logger import JarvisLogger
from ..utils import extract_json_from_text


class OrchestratorAgent(NetworkAgent):
    """Agent that breaks down complex requests into task sequences."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 10.0,
    ) -> None:
        super().__init__("OrchestratorAgent", logger)
        self.ai_client = ai_client
        self.response_timeout = response_timeout
        self.sequences: Dict[str, Dict[str, Any]] = {}
        self.pending_requests: Dict[str, Dict[str, Any]] = {}

    @property
    def description(self) -> str:
        return "Plans and orchestrates multi-step tasks"

    @property
    def capabilities(self) -> set[str]:
        """Orchestrator exposes no public capabilities."""
        return set()

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability != "orchestrate_tasks":
            return

        analysis = message.content.get("data", {}).get("analysis", {})
        self.logger.log("DEBUG", "Orchestration request analysis", json.dumps(analysis))
        history = message.content.get("context", {}).get("history", [])
        tasks = self._create_tasks(analysis)
        self.logger.log(
            "DEBUG", "Initial tasks", [t.capability for t in tasks]
        )
        self.sequences[message.request_id] = {
            "tasks": tasks,
            "current": 0,
            "origin": message.from_agent,
            "origin_msg": message.id,
            "results": {},
            "context_history": history,
        }
        await self._execute_next(message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        seq = self.sequences.get(message.request_id)
        if not seq:
            return
        task = seq["tasks"][seq["current"]]
        self.logger.log(
            "DEBUG",
            f"Received result for {task.capability}",
            json.dumps(message.content),
        )
        task.result = message.content
        seq["results"][task.capability] = message.content
        seq.setdefault("context_history", []).append(
            {"capability": task.capability, "result": message.content}
        )

        seq["current"] += 1
        await self._execute_next(message.request_id)

    async def _handle_error(self, message: Message) -> None:
        """Handle error messages from other agents gracefully."""
        seq = self.sequences.get(message.request_id)
        if seq:
            task = seq["tasks"][seq["current"]]
            seq["results"][task.capability] = {"error": message.content.get("error")}

            seq["current"] += 1
            await self._execute_next(message.request_id)
        else:
            await super()._handle_error(message)

    async def _execute_next(self, request_id: str) -> None:
        seq = self.sequences[request_id]
        if seq["current"] >= len(seq["tasks"]):
            # Finished - send results back
            result_payload = {
                "results": seq["results"],
                "context_history": seq.get("context_history", []),
            }
            if seq["origin"] != self.name:
                await self.send_capability_response(
                    seq["origin"], result_payload, request_id, seq["origin_msg"]
                )
            else:
                pending = self.pending_requests.get(request_id)
                if pending and not pending["future"].done():
                    pending["future"].set_result(result_payload)
                    del self.pending_requests[request_id]
            del self.sequences[request_id]
            return

        task = seq["tasks"][seq["current"]]
        context = self._gather_dependency_results(task, seq["results"])
        self.logger.log(
            "DEBUG",
            "Execute task",
            {
                "task_id": task.id,
                "capability": task.capability,
                "agent": task.assigned_agent,
                "context": context,
            },
        )

        command = self._build_task_command(
            task,
            self.pending_requests.get(request_id, {}).get("user_input", ""),
            context,
        )

        content = {
            "capability": task.capability,
            "data": {"command": command},
        }
        if context:
            content["context"] = context
        self.logger.log(
            "DEBUG",
            "Send capability request",
            {
                "to": task.assigned_agent,
                "capability": task.capability,
                "data": content.get("data"),
                "context": bool(context),
            },
        )
        await self.send_message(
            task.assigned_agent, "capability_request", content, request_id
        )

    def _gather_dependency_results(
        self, task: Task, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return full results for tasks this task depends on."""
        context = {dep: results.get(dep) for dep in task.depends_on if dep in results}
        if context:
            self.logger.log(
                "DEBUG",
                f"Context for {task.capability}",
                json.dumps(context),
            )
        return context

    def _build_task_command(
        self, task: Task, user_input: str, context: Dict[str, Any]
    ) -> str:
        """Create a command instructing the agent to perform only the given task."""
        base = (
            f"User request: {user_input}. "
            f"Your subtask is to execute capability '{task.capability}'."
        )
        if context:
            base += f" Use these previous results as context: {json.dumps(context)}."
        return base + " Only handle this capability and nothing else."

    def _create_tasks(self, analysis: Dict[str, Any]) -> List[Task]:
        """Create a task list from analysis output."""

        tasks: List[Task] = []
        intent = analysis.get("intent", "No intent found")
        caps = analysis.get("capabilities_needed", [])
        dependency_map = analysis.get("dependencies", {})

        for cap in caps:
            # Skip orchestrator capability to avoid recursion
            if cap == "orchestrate_tasks":
                continue

            providers = self.network.capability_registry.get(cap)
            if not providers:
                self.logger.log("WARNING", "No provider for capability", cap)
                continue

            tasks.append(
                Task(
                    capability=cap,
                    assigned_agent=providers[0],
                    depends_on=dependency_map.get(cap, []),
                    intent=intent,
                )
            )
        self.logger.log(
            "DEBUG",
            "Tasks created",
            [
                {
                    "id": t.id,
                    "capability": t.capability,
                    "agent": t.assigned_agent,
                    "depends_on": t.depends_on,
                }
                for t in tasks
            ],
        )
        return tasks

    async def process_user_request(
        self, user_input: str, tz_name: str
    ) -> Dict[str, Any]:
        """Analyze and execute a user request sequentially."""
        request_id = f"req_{uuid.uuid4()}"
        analysis = await self._analyze_request(user_input, tz_name)
        if analysis.get("analysis_failed"):
            return {
                "success": False,
                "response": "Sorry, I couldn't understand that request.",
                "request_id": request_id,
            }
        self.logger.log("INFO", "Analysis", json.dumps(analysis))
        tasks = self._create_tasks(analysis)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = {
            "future": future,
            "user_input": user_input,
            "tz": tz_name,
        }
        self.sequences[request_id] = {
            "tasks": tasks,
            "current": 0,
            "origin": self.name,
            "origin_msg": "",
            "results": {},
            "context_history": [
                {
                    "capability": "user_request",
                    "result": user_input,
                }
            ],
        }
        await self._execute_next(request_id)
        try:
            result_data = await asyncio.wait_for(future, timeout=self.response_timeout)
        except asyncio.TimeoutError:
            return {
                "success": False,
                "response": "Request timed out",
                "request_id": request_id,
            }

        final_text = await self._format_response(
            request_id,
            result_data["results"],
            tz_name,
            history=result_data.get("context_history", []),
        )
        self.logger.log("INFO", "Final response", final_text)
        return {"success": True, "response": final_text, "request_id": request_id}

    async def _analyze_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Use AI to analyze the user request and determine needed tasks."""
        self.logger.log("DEBUG", "Analyzing request", user_input)
        available_capabilities = []
        for cap, agents in self.network.capability_registry.items():
            if cap == "orchestrate_tasks":
                continue
            available_capabilities.append(f"- {cap}: provided by {', '.join(agents)}")

        current_date = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        system_prompt = f"""You are JARVIS, analyzing user requests to determine which capabilities are needed.

Current date: {current_date}

Available capabilities:
{chr(10).join(available_capabilities)}

List any dependencies explicitly using a "dependencies" mapping. For example: "dependencies": {{"remove_event": ["view_schedule"]}}.

Analyze the user's request and return a JSON object with:
- "intent": brief description of what the user wants
- "capabilities_needed": list of capability names needed
- "dependencies": mapping of capability names to the capabilities they depend on
- "coordination_notes": any special coordination needed between capabilities

Be thorough - include all capabilities that might be needed."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        self.logger.log("DEBUG", "Analysis prompt", json.dumps(messages))

        response = await self.ai_client.chat(messages, [])
        self.logger.log(
            "DEBUG", "Analysis raw response", getattr(response[0], "content", str(response))
        )

        analysis = extract_json_from_text(response[0].content)
        if analysis is None:
            self.logger.log("ERROR", "Failed to analyze request", response[0].content)
            return {"analysis_failed": True}

        self.logger.log("DEBUG", "Analysis result", json.dumps(analysis))
        return analysis

    async def _format_response(
        self,
        request_id: str,
        responses: Dict[str, Any],
        tz_name: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Format a natural language response from agent results."""
        request_data = self.pending_requests.get(request_id, {})
        context = {
            "user_request": request_data.get("user_input", ""),
            "agent_responses": responses,
            "timestamp": datetime.now(ZoneInfo(tz_name)).isoformat(),
        }
        if history:
            context["history"] = history
        system_prompt = """You are JARVIS, Tony Stark's AI assistant.
Format the agent responses into a natural, conversational response.
Be concise but complete. Don't mention the internal agent names."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User asked: {context['user_request']}"},
            {
                "role": "assistant",
                "content": f"Here's what I found: {json.dumps(context)}",
            },
        ]
        self.logger.log("DEBUG", "Format prompt", json.dumps(messages))

        result = await self.ai_client.chat(messages, [])
        self.logger.log(
            "DEBUG", "Format raw response", getattr(result[0], "content", str(result))
        )
        return result[0].content
