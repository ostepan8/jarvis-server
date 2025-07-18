from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from ..base import NetworkAgent
from ..message import Message
from ..task import Task
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger
from ...utils import extract_json_from_text
from ...performance import track_async


class OrchestratorAgent(NetworkAgent):
    """Agent that breaks down complex requests into task sequences."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 30.0,  # Increased timeout
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
        self.logger.log("INFO", "Orchestration request analysis", json.dumps(analysis))
        history = message.content.get("context", {}).get("history", [])
        tasks = self._create_tasks(analysis)
        self.logger.log("INFO", "Initial tasks", [t.capability for t in tasks])
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
            self.logger.log(
                "WARNING", f"No sequence found for request_id: {message.request_id}"
            )
            return

        # Log current state for debugging
        self.logger.log(
            "INFO",
            f"Current sequence state",
            {
                "request_id": message.request_id,
                "current_index": seq["current"],
                "total_tasks": len(seq["tasks"]),
                "completed_tasks": list(seq["results"].keys()),
            },
        )

        if seq["current"] >= len(seq["tasks"]):
            self.logger.log("WARNING", "Received response but no current task")
            return

        task = seq["tasks"][seq["current"]]
        self.logger.log(
            "INFO",
            f"Received result for {task.capability}",
            {"prompt": task.prompt, "result": message.content},
        )

        # Store the result
        task.result = message.content
        seq["results"][task.capability] = message.content
        seq.setdefault("context_history", []).append(
            {"capability": task.capability, "result": message.content}
        )

        # Move to next task
        seq["current"] += 1

        # Continue execution
        await self._execute_next(message.request_id)

    async def _handle_error(self, message: Message) -> None:
        """Handle error messages from other agents gracefully."""
        seq = self.sequences.get(message.request_id)
        if seq and seq["current"] < len(seq["tasks"]):
            task = seq["tasks"][seq["current"]]
            self.logger.log(
                "ERROR", f"Error in task {task.capability}", message.content
            )
            seq["results"][task.capability] = {"error": message.content.get("error")}

            # Continue to next task even on error
            seq["current"] += 1
            await self._execute_next(message.request_id)
        else:
            await super()._handle_error(message)

    async def _execute_next(self, request_id: str) -> None:
        seq = self.sequences.get(request_id)
        if not seq:
            self.logger.log("ERROR", f"No sequence found for request_id: {request_id}")
            return

        self.logger.log(
            "INFO",
            f"Execute next task",
            {
                "request_id": request_id,
                "current": seq["current"],
                "total": len(seq["tasks"]),
                "completed": list(seq["results"].keys()),
            },
        )

        if seq["current"] >= len(seq["tasks"]):
            # All tasks completed
            self.logger.log("INFO", f"All tasks completed for request {request_id}")

            # Prepare final results
            result_payload = {
                "results": seq["results"],
                "context_history": seq.get("context_history", []),
            }

            if seq["origin"] != self.name:
                # Response to another agent
                await self.send_capability_response(
                    seq["origin"], result_payload, request_id, seq["origin_msg"]
                )
            else:
                # Response to user request
                pending = self.pending_requests.get(request_id)
                if pending and not pending["future"].done():
                    pending["future"].set_result(result_payload)
                    # Don't delete pending_requests yet - _format_response needs it

            # Clean up sequence
            del self.sequences[request_id]
            return

        # Execute current task
        task = seq["tasks"][seq["current"]]
        context = self._gather_dependency_results(task, seq["results"])

        self.logger.log(
            "INFO",
            "Dependency context",
            {"depends_on": task.depends_on, "context": context},
        )

        self.logger.log(
            "INFO",
            f"Executing task {seq['current'] + 1}/{len(seq['tasks'])}",
            {
                "capability": task.capability,
                "agent": task.assigned_agent,
                "has_context": bool(context),
            },
        )

        # Build prompt for the task via a quick LLM call
        user_input = self.pending_requests.get(request_id, {}).get("user_input", "")
        prompt = await self._draft_prompt_via_llm(user_input, task, context)
        task.prompt = prompt

        # Prepare capability request
        content = {
            "capability": task.capability,
            "data": {"prompt": prompt},
        }
        if context:
            content["context"] = context

        # Send to the agent
        # Log before sending the message
        self.logger.log(
            "INFO",
            f"Sending capability request to {task.assigned_agent}",
            {"capability": task.capability, "request_id": request_id},
        )

        await self.send_message(
            task.assigned_agent, "capability_request", content, request_id
        )

    def _gather_dependency_results(
        self, task: Task, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return full results for tasks this task depends on."""
        context = {}
        for dep in task.depends_on:
            if dep in results:
                context[dep] = results[dep]
            else:
                self.logger.log(
                    "WARNING", f"Missing dependency {dep} for {task.capability}"
                )

        if context:
            self.logger.log(
                "DEBUG",
                f"Context for {task.capability}",
                json.dumps(context),
            )
        return context

    async def _draft_prompt_via_llm(
        self, user_input: str, task: Task, context: Dict[str, Any]
    ) -> str:
        """Use a quick weak LLM call to craft a prompt for the agent."""
        system_prompt = (
            "You generate concise prompts for specialized agents. "
            "First summarize the user's overall command, then explicitly name the agent that will act "
            "and explain why the capability is needed. Finally craft a short instruction incorporating any provided context."
        )

        user_message = {
            "overall_request": user_input,
            "capability": task.capability,
            "assigned_agent": task.assigned_agent,
            "task_intent": task.intent,
            "context": context,
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_message)},
        ]

        try:
            result, _ = await self.ai_client.weak_chat(messages, [])
            prompt = getattr(result, "content", "")
        except Exception as exc:
            self.logger.log("ERROR", "Prompt drafting failed", str(exc))
            prompt = ""

        self.logger.log(
            "INFO",
            f"Prompt for {task.capability}",
            prompt,
        )

        return prompt

    def _create_tasks(self, analysis: Dict[str, Any]) -> List[Task]:
        """Create a task list from analysis output."""
        tasks: List[Task] = []
        intent = analysis.get("intent", "No intent found")
        caps = analysis.get("capabilities_needed", [])
        dependency_map = analysis.get("dependencies", {})

        self.logger.log("INFO", "Dependency map", dependency_map)

        for cap in caps:
            # Skip orchestrator capability to avoid recursion
            if cap == "orchestrate_tasks":
                continue

            providers = self.network.capability_registry.get(cap)
            if not providers:
                self.logger.log("WARNING", f"No provider for capability: {cap}")
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
            "INFO",
            f"Created {len(tasks)} tasks",
            [
                {
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

        # Analyze the request
        analysis = await self._analyze_request(user_input, tz_name)
        if analysis.get("analysis_failed"):
            return {
                "success": False,
                "response": "Sorry, I couldn't understand that request.",
                "request_id": request_id,
            }

        self.logger.log(
            "INFO", f"Analysis complete: {analysis.get('intent', 'Unknown')}"
        )

        # Create tasks
        tasks = self._create_tasks(analysis)
        if not tasks:
            return {
                "success": False,
                "response": "I couldn't find any capabilities to handle that request.",
                "request_id": request_id,
            }

        # Set up future for async response
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        # Store request data
        self.pending_requests[request_id] = {
            "future": future,
            "user_input": user_input,
            "tz": tz_name,
        }

        # Initialize sequence
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

        # Start execution
        await self._execute_next(request_id)

        # Wait for completion
        try:
            result_data = await asyncio.wait_for(future, timeout=self.response_timeout)
        except asyncio.TimeoutError:
            self.logger.log("ERROR", f"Request {request_id} timed out")
            # Clean up
            if request_id in self.sequences:
                del self.sequences[request_id]
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            return {
                "success": False,
                "response": "The request took too long to complete. Please try again.",
                "request_id": request_id,
            }

        # Format final response
        self.logger.log(
            "INFO",
            f"Formatting final response for request {request_id}",
            {
                "num_results": len(result_data["results"]),
                "history_length": len(result_data.get("context_history", [])),
            },
        )
        final_text = await self._format_response(
            request_id,
            result_data["results"],
            tz_name,
            history=result_data.get("context_history", []),
        )

        # Clean up pending request
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]

        self.logger.log("INFO", f"Request {request_id} completed successfully")

        return {"success": True, "response": final_text, "request_id": request_id}

    @track_async("orchestrator_analysis")
    async def _analyze_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Use AI to analyze the user request and determine needed tasks."""
        self.logger.log("DEBUG", "Analyzing request", user_input)

        # Get available capabilities
        available_capabilities = []
        for cap, agents in self.network.capability_registry.items():
            if cap == "orchestrate_tasks":
                continue
            available_capabilities.append(f"- {cap}: provided by {', '.join(agents)}")

        current_date = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        system_prompt = f"""
You are JARVIS, analyzing user requests to determine which capabilities are needed to fulfill them using available tools. You must prioritize dependency resolution and task decomposition over improvisation.

Current date: {current_date}

Available capabilities:
{chr(10).join(available_capabilities)}

Your job is to reason carefully through what the user is asking, and return a JSON object with:

- "intent": a concise summary of what the user wants
- "capabilities_needed": all capability names required to fulfill the task
- "dependencies": a mapping like {{capability: [dependent_capability, ...]}} showing any information that must be retrieved first
- "coordination_notes": a precise, step-by-step breakdown of what order capabilities should run in and how they work together

Instructions:
1. Do **not** guess or assume any state. If the request involves modifying, deleting, or interacting with something that must already exist (like events, files, settings), you must first retrieve or inspect it using the appropriate capabilities.
2. Only plan actions **after verifying the target exists** or meets the right conditions.
3. Be comprehensive—include ALL capabilities needed to fully satisfy the request, even if they're only for internal verification.
4. Use prior context or capabilities to reason about the current request. This system assumes prior data is retrievable.
5. Err on the side of being conservative and explicit. Avoid hallucinating behaviors that haven't been defined as capabilities.

Example dependency mapping:
"dependencies": {{
    "schedule_appointment": ["get_today_schedule"],
    "update_event": ["view_calendar_events"],
    "reschedule_appointment": ["check_calendar_availability"]
}}

Make sure the result enables deterministic scheduling and coordination between agents. Think like a task planner, not an LLM."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        response = await self.ai_client.strong_chat(messages, [])
        self.logger.log(
            "DEBUG",
            "Analysis raw response",
            getattr(response[0], "content", str(response)),
        )

        analysis = extract_json_from_text(response[0].content)
        if analysis is None:
            self.logger.log("ERROR", "Failed to analyze request", response[0].content)
            return {"analysis_failed": True}

        self.logger.log("DEBUG", "Analysis result", json.dumps(analysis))
        return analysis

    @track_async("orchestrator_response")
    async def _format_response(
        self,
        request_id: str,
        responses: Dict[str, Any],
        tz_name: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Format a natural language response from agent results."""
        request_data = self.pending_requests.get(request_id, {})
        user_input = request_data.get("user_input", "")

        # Build context
        context = {
            "original_request": user_input,
            "agent_responses": responses,
            "timestamp": datetime.now(ZoneInfo(tz_name)).isoformat(),
        }
        if history:
            context["execution_history"] = history

        system_prompt = """You are JARVIS, Tony Stark's AI assistant for Owen Stepan.

Your primary objective is to respond in a natural, conversational tone, just as you would if speaking aloud to Tony Stark (except address to Owen Stepan).

CRITICAL INSTRUCTIONS:
1. Always keep the user's original request in mind when formulating your response
2. Directly address what the user asked for, using their own words when appropriate
3. Frame your response as a direct answer to their specific question or request
4. If the user asked for something specific (like viewing a schedule, creating a reminder, etc.), acknowledge that specific request in your response

FORMATTING RULES:
- NEVER use bullet points, numbered lists, or special formatting symbols
- No asterisks, dashes, emojis, or markdown formatting
- Reword everything into flowing, natural speech
- Break down any structured data into conversational explanations

RESPONSE STYLE:
- Be concise, clear, and natural
- Speak as if having a calm, intelligent conversation
- Don't reference internal system behavior or "agents"
- Always relate your response back to what the user originally asked for"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Original request: '{user_input}'\n\nSystem data: {json.dumps(context)}\n\nPlease provide a natural response that directly addresses the original request.",
            },
        ]

        result = await self.ai_client.strong_chat(messages, [])
        return result[0].content
