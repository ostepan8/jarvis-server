"""SchedulerAgent — manages scheduled task execution.

Capabilities:
    schedule_task  — create a new scheduled task (once, cron, or interval)
    list_schedules — list all registered schedules
    cancel_schedule — remove a schedule permanently
    pause_schedule  — disable a schedule without deleting it
    resume_schedule — re-enable a paused schedule

Two input modes:
    1. Natural language (user-facing): AI parses free-text into a JSON
       operation via ``weak_chat``, identical to the TodoAgent pattern.
    2. Structured (agent-to-agent): If ``data.get("structured")`` is a
       dict, bypass AI parsing and dispatch directly to ``_execute_op``.

A background tick loop (following the ServerManagerAgent pattern) wakes
every ``tick_interval`` seconds, queries the service for due schedules,
marks them fired, and dispatches each through the orchestrator.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..agent_network import AgentNetwork
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...services.scheduler_service import SchedulerService
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger


_SYSTEM_PROMPT = """\
You are a scheduling assistant inside JARVIS. Parse the user's message
and return **only** a JSON object describing the operation.

Operations:
1. schedule — {"op":"schedule","name":"...","schedule_type":"once|cron|interval","request_text":"...","cron_expression":"...","interval_seconds":300,"run_at":"2026-03-14T07:00:00+00:00","timezone":"America/New_York"}
2. list    — {"op":"list","enabled":null,"schedule_type":null}
3. cancel  — {"op":"cancel","id":"abc123"}
4. pause   — {"op":"pause","id":"abc123"}
5. resume  — {"op":"resume","id":"abc123"}

Rules:
- "every morning at 7am" → cron with "0 7 * * *"
- "in 30 minutes" / "at 3pm tomorrow" → once with ISO-8601 run_at
- "every 5 minutes" → interval with interval_seconds=300
- request_text is what the user wants done, e.g. "give me the weather and calendar"
- If the user lists multiple schedules to create, return a JSON array.
- Return ONLY the JSON, no prose.
"""


class SchedulerAgent(NetworkAgent):
    """Manages scheduled tasks via natural language or structured input."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        scheduler_service: SchedulerService,
        logger: Optional[JarvisLogger] = None,
        tick_interval: float = 15.0,
    ) -> None:
        super().__init__("SchedulerAgent", logger)
        self.ai_client = ai_client
        self.scheduler_service = scheduler_service
        self._tick_interval = tick_interval
        self._tick_task: Optional[asyncio.Task] = None
        self._orchestrator: Any = None
        self._fire_semaphore = asyncio.Semaphore(5)
        self.intent_map: Dict[str, Any] = {
            "schedule_task": self._handle_schedule,
            "list_schedules": self._handle_list,
            "cancel_schedule": self._handle_cancel,
            "pause_schedule": self._handle_pause,
            "resume_schedule": self._handle_resume,
        }

    @property
    def description(self) -> str:
        return (
            "Manages scheduled tasks — create one-shot, cron, or interval "
            "schedules that fire requests through the orchestrator automatically"
        )

    @property
    def capabilities(self) -> Set[str]:
        return {
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "pause_schedule",
            "resume_schedule",
        }

    # -- Orchestrator binding ------------------------------------------------

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Store a reference to the RequestOrchestrator for the tick loop."""
        self._orchestrator = orchestrator

    # -- Lifecycle -----------------------------------------------------------

    def set_network(self, network: AgentNetwork) -> None:
        """Start the background tick loop when the network is attached."""
        super().set_network(network)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop — caller will start later
        if self._tick_task is None or self._tick_task.done():
            self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """Cancel the tick loop and close the service."""
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        self.scheduler_service.close()

    # -- Message handlers ----------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"SchedulerAgent handling: {capability}", str(data)[:200])

        try:
            # Structured input bypasses AI parsing entirely
            structured = data.get("structured") if isinstance(data, dict) else None
            if isinstance(structured, dict):
                result = self._execute_op(structured)
            else:
                prompt = data.get("prompt", "")
                result = await self._process(prompt)

            await self.send_capability_response(
                message.from_agent,
                result.to_dict(),
                message.request_id,
                message.id,
            )
        except Exception as exc:
            self.logger.log("ERROR", "SchedulerAgent error", str(exc))
            err = AgentResponse.from_exception(
                exc, "Something went wrong managing your schedules."
            )
            await self.send_capability_response(
                message.from_agent,
                err.to_dict(),
                message.request_id,
                message.id,
            )

    async def _handle_capability_response(self, message: Message) -> None:
        pass

    # -- Core processing -----------------------------------------------------

    async def _process(self, prompt: str) -> AgentResponse:
        """Parse the user prompt into operations and execute them."""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = await self.ai_client.weak_chat(messages, [])
        raw = response[0].content.strip()

        # Extract JSON from potential markdown fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return AgentResponse.error_response(
                response=(
                    "I couldn't parse that scheduling request. "
                    "Try something like 'every morning at 7am give me the weather'."
                ),
                error=ErrorInfo(
                    message="Failed to parse LLM output",
                    error_type="ParseError",
                ),
            )

        # Single operation or batch
        ops = parsed if isinstance(parsed, list) else [parsed]
        results = []
        for op in ops:
            result = self._execute_op(op)
            results.append(result)

        if len(results) == 1:
            return results[0]

        # Merge multiple results
        texts = [r.response for r in results]
        all_success = all(r.success for r in results)
        combined_actions = []
        for r in results:
            combined_actions.extend(r.actions)
        return AgentResponse(
            success=all_success,
            response=" | ".join(texts),
            actions=combined_actions,
            metadata={"agent": "scheduler", "batch_size": len(results)},
        )

    # -- Operation dispatch --------------------------------------------------

    def _execute_op(self, op: Dict[str, Any]) -> AgentResponse:
        name = op.get("op", "")
        try:
            if name == "schedule":
                return self._handle_schedule(op)
            elif name == "list":
                return self._handle_list(op)
            elif name == "cancel":
                return self._handle_cancel(op)
            elif name == "pause":
                return self._handle_pause(op)
            elif name == "resume":
                return self._handle_resume(op)
            else:
                return AgentResponse.error_response(
                    response=f"Unknown operation: {name}",
                    error=ErrorInfo(
                        message=f"Unknown op: {name}",
                        error_type="InvalidOperation",
                    ),
                )
        except Exception as exc:
            return AgentResponse.from_exception(exc)

    # -- Individual handlers -------------------------------------------------

    def _handle_schedule(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        name = op.get("name", "Untitled schedule")
        schedule_type = op.get("schedule_type", "once")
        request_text = op.get("request_text", "")

        item = self.scheduler_service.create(
            name=name,
            schedule_type=schedule_type,
            request_text=request_text,
            cron_expression=op.get("cron_expression"),
            interval_seconds=op.get("interval_seconds"),
            run_at=op.get("run_at"),
            timezone=op.get("timezone", "UTC"),
        )
        return AgentResponse.success_response(
            response=(
                f"Scheduled [{item.id}] \"{item.name}\" "
                f"({schedule_type}, tz={item.timezone})."
            ),
            actions=[{"type": "schedule_created", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "scheduler"},
        )

    def _handle_list(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        items = self.scheduler_service.list(
            enabled=op.get("enabled"),
            schedule_type=op.get("schedule_type"),
        )
        if not items:
            return AgentResponse.success_response(
                response="No schedules found. The calendar is blissfully empty.",
                data={"schedules": []},
                metadata={"agent": "scheduler"},
            )

        lines = []
        for item in items:
            status_icon = "▶" if item.enabled else "⏸"
            lines.append(
                f"  {status_icon} [{item.id}] {item.name} "
                f"({item.schedule_type}, tz={item.timezone})"
            )

        text = f"{len(items)} schedule(s) registered.\n" + "\n".join(lines)
        return AgentResponse.success_response(
            response=text,
            data={"schedules": [i.to_dict() for i in items]},
            metadata={"agent": "scheduler"},
        )

    def _handle_cancel(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        schedule_id = op.get("id", "")
        deleted = self.scheduler_service.delete(schedule_id)
        if not deleted:
            return AgentResponse.error_response(
                response=f"Schedule '{schedule_id}' not found.",
                error=ErrorInfo(message="Schedule not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Cancelled schedule '{schedule_id}'. It will not be missed.",
            actions=[{"type": "schedule_cancelled", "details": {"id": schedule_id}}],
            metadata={"agent": "scheduler"},
        )

    def _handle_pause(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        schedule_id = op.get("id", "")
        item = self.scheduler_service.disable(schedule_id)
        if not item:
            return AgentResponse.error_response(
                response=f"Schedule '{schedule_id}' not found.",
                error=ErrorInfo(message="Schedule not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Paused schedule [{item.id}] \"{item.name}\".",
            actions=[{"type": "schedule_paused", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "scheduler"},
        )

    def _handle_resume(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        schedule_id = op.get("id", "")
        item = self.scheduler_service.enable(schedule_id)
        if not item:
            return AgentResponse.error_response(
                response=f"Schedule '{schedule_id}' not found.",
                error=ErrorInfo(message="Schedule not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Resumed schedule [{item.id}] \"{item.name}\". Back in business.",
            actions=[{"type": "schedule_resumed", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "scheduler"},
        )

    # -- Background tick loop ------------------------------------------------

    async def _tick_loop(self) -> None:
        """Poll for due schedules and fire them through the orchestrator."""
        while True:
            try:
                await asyncio.sleep(self._tick_interval)
                if not self._orchestrator:
                    continue
                due = self.scheduler_service.get_due_schedules()
                for schedule in due:
                    self.scheduler_service.mark_fired(schedule.id)
                    asyncio.create_task(self._fire_schedule(schedule))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.log("ERROR", "Scheduler tick error", str(exc))

    async def _fire_schedule(self, schedule: Any) -> None:
        """Fire a single schedule through the orchestrator."""
        async with self._fire_semaphore:
            try:
                self.logger.log(
                    "INFO",
                    "Firing schedule",
                    f"{schedule.id}: {schedule.name}",
                )
                await self._orchestrator.process_request(
                    user_input=schedule.request_text,
                    tz_name=schedule.timezone,
                    metadata={
                        "source": "scheduler",
                        "schedule_id": schedule.id,
                    },
                )
            except Exception as exc:
                self.logger.log(
                    "ERROR",
                    "Schedule fire failed",
                    f"{schedule.id}: {exc}",
                )
