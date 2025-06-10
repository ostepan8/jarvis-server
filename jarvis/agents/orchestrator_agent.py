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
        return {"orchestrate_tasks"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability != "orchestrate_tasks":
            return

        analysis = message.content.get("data", {}).get("analysis", {})
        tasks = self._create_tasks(analysis)
        self.sequences[message.request_id] = {
            "tasks": tasks,
            "current": 0,
            "origin": message.from_agent,
            "origin_msg": message.id,
            "results": {},
        }
        await self._execute_next(message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        seq = self.sequences.get(message.request_id)
        if not seq:
            return
        task = seq["tasks"][seq["current"]]
        task.result = message.content
        seq["results"][task.capability] = message.content
        seq["current"] += 1
        await self._execute_next(message.request_id)

    async def _execute_next(self, request_id: str) -> None:
        seq = self.sequences[request_id]
        if seq["current"] >= len(seq["tasks"]):
            # Finished - send results back
            if seq["origin"] != self.name:
                await self.send_capability_response(
                    seq["origin"], seq["results"], request_id, seq["origin_msg"]
                )
            else:
                pending = self.pending_requests.get(request_id)
                if pending and not pending["future"].done():
                    pending["future"].set_result(seq["results"])
                    del self.pending_requests[request_id]
            del self.sequences[request_id]
            return

        task = seq["tasks"][seq["current"]]
        content = {"capability": task.capability, "data": task.parameters}
        await self.send_message(task.assigned_agent, "capability_request", content, request_id)

    def _create_tasks(self, analysis: Dict[str, Any]) -> List[Task]:
        tasks: List[Task] = []
        caps = analysis.get("capabilities_needed", [])
        params = analysis.get("parameters", {})
        for cap in caps:
            provider = None
            providers = self.network.capability_registry.get(cap)
            if providers:
                provider = providers[0]
            tasks.append(Task(capability=cap, parameters=params.get(cap, {}), assigned_agent=provider))
        return tasks

    async def process_user_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Analyze and execute a user request sequentially."""
        request_id = f"req_{uuid.uuid4()}"
        analysis = await self._analyze_request(user_input, tz_name)
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
        }
        await self._execute_next(request_id)
        try:
            results = await asyncio.wait_for(future, timeout=self.response_timeout)
        except asyncio.TimeoutError:
            return {"success": False, "response": "Request timed out", "request_id": request_id}

        final_text = await self._format_response(request_id, results, tz_name)
        return {"success": True, "response": final_text, "request_id": request_id}

    async def _analyze_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Use AI to analyze the user request and determine needed tasks."""
        self.logger.log("DEBUG", "Analyzing request", user_input)
        available_capabilities = []
        for cap, agents in self.network.capability_registry.items():
            available_capabilities.append(f"- {cap}: provided by {', '.join(agents)}")

        current_date = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        system_prompt = f"""You are JARVIS, analyzing user requests to determine which capabilities are needed.

Current date: {current_date}

Available capabilities:
{chr(10).join(available_capabilities)}

Analyze the user's request and return a JSON object with:
- "intent": brief description of what the user wants
- "capabilities_needed": list of capability names needed
- "parameters": dict of parameters for each capability
- "coordination_notes": any special coordination needed between capabilities

Be thorough - include all capabilities that might be needed."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        response = await self.ai_client.chat(messages, [])

        try:
            analysis = json.loads(response[0].content)
        except Exception:
            analysis = self._simple_request_analysis(user_input)

        self.logger.log("DEBUG", "Analysis result", json.dumps(analysis))
        return analysis

    async def _format_response(self, request_id: str, responses: Dict[str, Any], tz_name: str) -> str:
        """Format a natural language response from agent results."""
        request_data = self.pending_requests.get(request_id, {})
        context = {
            "user_request": request_data.get("user_input", ""),
            "agent_responses": responses,
            "timestamp": datetime.now(ZoneInfo(tz_name)).isoformat(),
        }
        system_prompt = """You are JARVIS, Tony Stark's AI assistant.
Format the agent responses into a natural, conversational response.
Be concise but complete. Don't mention the internal agent names."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User asked: {context['user_request']}"},
            {"role": "assistant", "content": f"Here's what I found: {json.dumps(context)}"},
        ]

        result = await self.ai_client.chat(messages, [])
        return result[0].content

    def _simple_request_analysis(self, user_input: str) -> Dict[str, Any]:
        """Very basic keyword-based analysis as a fallback."""
        lower_input = user_input.lower()
        capabilities_needed: List[str] = []
        parameters: Dict[str, Any] = {}
        if any(word in lower_input for word in ["schedule", "calendar", "meeting", "appointment"]):
            capabilities_needed.append("calendar_command")
            parameters["calendar_command"] = {"command": user_input}
        if any(word in lower_input for word in ["email", "mail", "send"]):
            capabilities_needed.append("send_email")
        return {
            "intent": "Process user request",
            "capabilities_needed": capabilities_needed,
            "parameters": parameters,
        }
