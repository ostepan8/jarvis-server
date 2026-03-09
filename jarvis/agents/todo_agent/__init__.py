"""TodoAgent — manages a Linear-style task board.

Capabilities:
    create_task, list_tasks, update_task, complete_task, delete_task

The agent uses an AI client to parse natural-language requests into
structured operations against the TodoService (SQLite-backed).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...services.todo_service import TodoService
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger


_SYSTEM_PROMPT = """\
You are a task-management assistant inside JARVIS. Parse the user's message
and return **only** a JSON object describing the operation.

Operations:
1. create  — {"op":"create","title":"...","description":"...","priority":"medium","tags":["dev"],"due_date":"2024-03-10"}
2. list    — {"op":"list","status":null,"priority":null,"tag":null}
3. update  — {"op":"update","id":"abc123","fields":{"title":"new","status":"in_progress","priority":"high"}}
4. complete — {"op":"complete","id":"abc123"}
5. start   — {"op":"start","id":"abc123"}
6. delete  — {"op":"delete","id":"abc123"}
7. show    — {"op":"show","id":"abc123"}

Rules:
- priority values: urgent, high, medium, low
- status values: todo, in_progress, done
- If the user says "finish" / "done" / "mark complete" → complete
- If the user says "start" / "work on" / "begin" → start
- If the user lists multiple tasks, return a JSON array of operations.
- Return ONLY the JSON, no prose.
"""

class TodoAgent(NetworkAgent):
    """Manages todo tasks via natural language."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        todo_service: TodoService,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__("TodoAgent", logger)
        self.ai_client = ai_client
        self.todo_service = todo_service
        self.intent_map = {
            "create_task": self._handle_create,
            "list_tasks": self._handle_list,
            "update_task": self._handle_update,
            "complete_task": self._handle_complete,
            "delete_task": self._handle_delete,
        }

    @property
    def description(self) -> str:
        return "Manages a Linear-style task board with create, list, update, complete, and delete operations"

    @property
    def capabilities(self) -> Set[str]:
        return {"create_task", "list_tasks", "update_task", "complete_task", "delete_task"}

    # ------------------------------------------------------------------
    # Network message handler
    # ------------------------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"TodoAgent handling: {capability}", str(data)[:200])

        try:
            prompt = data.get("prompt", "")
            result = await self._process(prompt)
            await self.send_capability_response(
                message.from_agent,
                result.to_dict(),
                message.request_id,
                message.id,
            )
        except Exception as exc:
            self.logger.log("ERROR", "TodoAgent error", str(exc))
            err = AgentResponse.from_exception(exc, "Something went wrong managing your tasks.")
            await self.send_capability_response(
                message.from_agent,
                err.to_dict(),
                message.request_id,
                message.id,
            )

    async def _handle_capability_response(self, message: Message) -> None:
        pass

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

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
                response="I couldn't understand that task command. Try something like 'add a task to fix the login bug'.",
                error=ErrorInfo(message="Failed to parse LLM output", error_type="ParseError"),
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
            metadata={"agent": "todo", "batch_size": len(results)},
        )

    # ------------------------------------------------------------------
    # Operation dispatch
    # ------------------------------------------------------------------

    def _execute_op(self, op: Dict[str, Any]) -> AgentResponse:
        name = op.get("op", "")
        try:
            if name == "create":
                return self._handle_create(op)
            elif name == "list":
                return self._handle_list(op)
            elif name == "update":
                return self._handle_update(op)
            elif name == "complete":
                return self._handle_complete(op)
            elif name == "start":
                return self._handle_start(op)
            elif name == "delete":
                return self._handle_delete(op)
            elif name == "show":
                return self._handle_show(op)
            else:
                return AgentResponse.error_response(
                    response=f"Unknown operation: {name}",
                    error=ErrorInfo(message=f"Unknown op: {name}", error_type="InvalidOperation"),
                )
        except Exception as exc:
            return AgentResponse.from_exception(exc)

    # ------------------------------------------------------------------
    # Individual handlers
    # ------------------------------------------------------------------

    def _handle_create(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        title = op.get("title", "Untitled task")
        item = self.todo_service.create(
            title=title,
            description=op.get("description", ""),
            priority=op.get("priority", "medium"),
            tags=op.get("tags"),
            due_date=op.get("due_date"),
        )
        return AgentResponse.success_response(
            response=f"Created task [{item.id}] \"{item.title}\" ({item.priority.value} priority).",
            actions=[{"type": "task_created", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "todo"},
        )

    def _handle_list(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        items = self.todo_service.list(
            status=op.get("status"),
            priority=op.get("priority"),
            tag=op.get("tag"),
        )
        if not items:
            return AgentResponse.success_response(
                response="No tasks found. Your board is empty!",
                data={"tasks": [], "counts": self.todo_service.counts_by_status()},
                metadata={"agent": "todo"},
            )

        lines = []
        for item in items:
            status_icon = {"todo": "○", "in_progress": "◐", "done": "●"}[item.status.value]
            priority_flag = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}[item.priority.value]
            lines.append(f"  {status_icon} [{item.id}] {priority_flag} {item.title}")

        counts = self.todo_service.counts_by_status()
        summary = f"Todo: {counts['todo']} | In Progress: {counts['in_progress']} | Done: {counts['done']}"
        text = summary + "\n" + "\n".join(lines)

        return AgentResponse.success_response(
            response=text,
            data={"tasks": [i.to_dict() for i in items], "counts": counts},
            metadata={"agent": "todo"},
        )

    def _handle_update(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        todo_id = op.get("id", "")
        fields = op.get("fields", {})
        item = self.todo_service.update(todo_id, **fields)
        if not item:
            return AgentResponse.error_response(
                response=f"Task '{todo_id}' not found.",
                error=ErrorInfo(message="Task not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Updated task [{item.id}] \"{item.title}\".",
            actions=[{"type": "task_updated", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "todo"},
        )

    def _handle_complete(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        todo_id = op.get("id", "")
        item = self.todo_service.complete(todo_id)
        if not item:
            return AgentResponse.error_response(
                response=f"Task '{todo_id}' not found.",
                error=ErrorInfo(message="Task not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Completed task [{item.id}] \"{item.title}\". Nice work!",
            actions=[{"type": "task_completed", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "todo"},
        )

    def _handle_start(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        todo_id = op.get("id", "")
        item = self.todo_service.start(todo_id)
        if not item:
            return AgentResponse.error_response(
                response=f"Task '{todo_id}' not found.",
                error=ErrorInfo(message="Task not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Started task [{item.id}] \"{item.title}\". Let's go!",
            actions=[{"type": "task_started", "details": item.to_dict()}],
            data=item.to_dict(),
            metadata={"agent": "todo"},
        )

    def _handle_delete(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        todo_id = op.get("id", "")
        deleted = self.todo_service.delete(todo_id)
        if not deleted:
            return AgentResponse.error_response(
                response=f"Task '{todo_id}' not found.",
                error=ErrorInfo(message="Task not found", error_type="NotFound"),
            )
        return AgentResponse.success_response(
            response=f"Deleted task '{todo_id}'.",
            actions=[{"type": "task_deleted", "details": {"id": todo_id}}],
            metadata={"agent": "todo"},
        )

    def _handle_show(self, op: Dict[str, Any] | None = None, **kw: Any) -> AgentResponse:
        op = op or kw
        todo_id = op.get("id", "")
        item = self.todo_service.get(todo_id)
        if not item:
            return AgentResponse.error_response(
                response=f"Task '{todo_id}' not found.",
                error=ErrorInfo(message="Task not found", error_type="NotFound"),
            )
        tags_str = ", ".join(item.tags) if item.tags else "none"
        text = (
            f"[{item.id}] {item.title}\n"
            f"  Status: {item.status.value} | Priority: {item.priority.value}\n"
            f"  Tags: {tags_str}\n"
            f"  Due: {item.due_date or 'no due date'}\n"
            f"  Description: {item.description or '(none)'}\n"
            f"  Created: {item.created_at}"
        )
        return AgentResponse.success_response(
            response=text,
            data=item.to_dict(),
            metadata={"agent": "todo"},
        )
