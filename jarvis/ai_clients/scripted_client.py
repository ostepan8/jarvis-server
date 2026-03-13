"""ScriptedAIClient — deterministic AI client for E2E testing.

Pattern-matches on message content to return pre-scripted responses.
Same interface as real clients, zero network calls, fully reproducible.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAIClient

logger = logging.getLogger(__name__)


def _msg(content: str) -> Any:
    """Create a lightweight message object with a .content attribute."""
    return type("Message", (), {"content": content})


# ---------------------------------------------------------------------------
# Default script tables
# ---------------------------------------------------------------------------

DEFAULT_NLU_SCRIPTS: Dict[str, Dict[str, Any]] = {
    "weather": {"dag": {"search": []}},
    "search for": {"dag": {"search": []}},
    "schedule": {"dag": {"schedule_appointment": []}},
    "create an event": {"dag": {"schedule_appointment": []}},
    "what's on my calendar": {"dag": {"get_today_schedule": []}},
    "what's on my": {"dag": {"get_today_schedule": []}},
    "turn on the lights": {"dag": {"lights_on": []}},
    "hello": {"dag": {"chat": []}},
    "how are you": {"dag": {"chat": []}},
    "add a task": {"dag": {"create_task": []}},
    "show my tasks": {"dag": {"list_tasks": []}},
    "search for news and tell me my schedule": {
        "dag": {"search": [], "get_today_schedule": []}
    },
}

DEFAULT_SEARCH_SYNTHESIS = (
    "Based on the search results, the current weather is 72F and sunny "
    "with a light breeze from the west."
)

DEFAULT_CHAT_RESPONSE = (
    "All systems nominal. How may I be of service."
)

DEFAULT_CALENDAR_RESPONSE = "Meeting scheduled for 3pm tomorrow."

DEFAULT_TODO_RESPONSE = json.dumps({"op": "list"})


class ScriptedAIClient(BaseAIClient):
    """Deterministic AI client that pattern-matches on message content.

    Call type is detected from system message content (priority order):
    1. NLU Classification — system msg contains "Available Capabilities"
    2. Coordinator Triage — message contains "simple' or 'complex"
    3. Search Synthesis — system msg contains "search results" or "Synthesize"
    4. Calendar Command — system msg contains "calendar" with tool definitions
    5. Todo Command — system msg contains "task-management"
    6. DAG Response Formatting — system msg contains "Format a natural"
    7. Chat (strong_chat) — system msg contains "Jarvis" or "assistant"
    8. Fallback — nothing matched
    """

    def __init__(
        self,
        nlu_scripts: Optional[Dict[str, Dict[str, Any]]] = None,
        search_synthesis: Optional[str] = None,
        chat_response: Optional[str] = None,
        calendar_response: Optional[str] = None,
        todo_response: Optional[str] = None,
    ) -> None:
        self.nlu_scripts = nlu_scripts or dict(DEFAULT_NLU_SCRIPTS)
        self.search_synthesis = search_synthesis or DEFAULT_SEARCH_SYNTHESIS
        self.chat_response = chat_response or DEFAULT_CHAT_RESPONSE
        self.calendar_response = calendar_response or DEFAULT_CALENDAR_RESPONSE
        self.todo_response = todo_response or DEFAULT_TODO_RESPONSE
        self.call_log: List[Dict[str, Any]] = []

    async def strong_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
    ) -> Tuple[Any, Any]:
        self._log_call("strong_chat", messages, tools)
        content = self._resolve(messages, tools, strong=True)
        return _msg(content), None

    async def weak_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None = None,
    ) -> Tuple[Any, Any]:
        self._log_call("weak_chat", messages, tools)
        content = self._resolve(messages, tools, strong=False)
        return _msg(content), None

    # ------------------------------------------------------------------
    # Internal resolution
    # ------------------------------------------------------------------

    def _resolve(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
        strong: bool,
    ) -> str:
        system_msg = self._get_system_content(messages)
        user_msg = self._get_user_content(messages)

        # 1. NLU Classification
        if "Available Capabilities" in system_msg or "Natural Language Understanding" in system_msg:
            return self._nlu_classify(user_msg)

        # 2. Coordinator Triage
        if "simple' or 'complex" in system_msg or "'simple' or 'complex'" in system_msg:
            return json.dumps({"complexity": "simple"})

        # 3. Search Synthesis
        if "search results" in system_msg.lower() or "synthesize" in system_msg.lower():
            return self.search_synthesis

        # 4. Calendar Command (weak_chat with tools for calendar)
        if "calendar" in system_msg.lower() and tools:
            return self.calendar_response

        # 5. Todo Command
        if "task-management" in system_msg.lower() or "task management" in system_msg.lower():
            return self._todo_resolve(user_msg)

        # 6. DAG Response Formatting
        if "format a natural" in system_msg.lower():
            return self._format_dag_response(messages)

        # 7. Chat (strong_chat path)
        if strong:
            return self.chat_response

        # 8. Fallback
        logger.warning("ScriptedAIClient: no script matched for: %s", user_msg[:80])
        return "Scripted response not found."

    def _nlu_classify(self, user_input: str) -> str:
        """Match user input against NLU script table."""
        lower = user_input.lower().strip()
        for trigger, dag in self.nlu_scripts.items():
            if trigger.lower() in lower:
                return json.dumps(dag)
        # Default: route to chat
        return json.dumps({"dag": {"chat": []}})

    def _todo_resolve(self, user_input: str) -> str:
        """Return a deterministic todo operation based on input."""
        lower = user_input.lower()
        if "add" in lower or "create" in lower:
            title = "buy groceries"
            # Try to extract title from "add a task: <title>" pattern
            if ":" in user_input:
                title = user_input.split(":", 1)[1].strip()
            return json.dumps({
                "op": "create",
                "title": title,
                "priority": "medium",
            })
        if "show" in lower or "list" in lower:
            return json.dumps({"op": "list"})
        if "complete" in lower or "done" in lower or "finish" in lower:
            return json.dumps({"op": "complete", "id": "task-001"})
        if "delete" in lower or "remove" in lower:
            return json.dumps({"op": "delete", "id": "task-001"})
        return self.todo_response

    def _format_dag_response(self, messages: List[Dict[str, Any]]) -> str:
        """Synthesize a combined prose string from multi-agent results."""
        user_content = self._get_user_content(messages)
        if "agent results" in user_content.lower():
            return "The weather is sunny at 72F. Your calendar shows a team standup at 10am."
        return "Request completed."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_system_content(messages: List[Dict[str, Any]]) -> str:
        for msg in messages:
            if msg.get("role") == "system":
                return msg.get("content", "")
        return ""

    @staticmethod
    def _get_user_content(messages: List[Dict[str, Any]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    def _log_call(
        self,
        method: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] | None,
    ) -> None:
        self.call_log.append({
            "method": method,
            "system": self._get_system_content(messages)[:200],
            "user": self._get_user_content(messages)[:200],
            "has_tools": bool(tools),
        })
