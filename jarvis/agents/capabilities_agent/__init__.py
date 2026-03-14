"""CapabilitiesAgent — the capabilities librarian.

Maintains a living knowledge base of everything Jarvis can (and cannot) do.
Uses progressive disclosure: high-level summaries first, drilling into
agent-specific details only when asked.  Introspects the agent network at
runtime so answers reflect what is *actually* live, not just what is
documented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ..response import AgentResponse
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger

# Knowledge base lives next to this file
_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Maps keyword hints to knowledge files for targeted lookup
_SKILL_KEYWORDS: Dict[str, str] = {
    "smart home": "skills/smart_home.md",
    "light": "skills/smart_home.md",
    "lighting": "skills/smart_home.md",
    "hue": "skills/smart_home.md",
    "yeelight": "skills/smart_home.md",
    "tv": "skills/smart_home.md",
    "roku": "skills/smart_home.md",
    "television": "skills/smart_home.md",
    "device monitor": "skills/smart_home.md",
    "productivity": "skills/productivity.md",
    "calendar": "skills/productivity.md",
    "event": "skills/productivity.md",
    "schedule": "skills/productivity.md",
    "task": "skills/productivity.md",
    "todo": "skills/productivity.md",
    "reminder": "skills/productivity.md",
    "protocol": "skills/productivity.md",
    "workflow": "skills/productivity.md",
    "information": "skills/information.md",
    "search": "skills/information.md",
    "memory": "skills/information.md",
    "remember": "skills/information.md",
    "chat": "skills/information.md",
    "canvas": "skills/information.md",
    "homework": "skills/information.md",
    "course": "skills/information.md",
    "system": "skills/system.md",
    "health": "skills/system.md",
    "server": "skills/system.md",
    "night": "skills/system.md",
    "incident": "skills/system.md",
    "limitation": "limitations.md",
    "can't": "limitations.md",
    "cannot": "limitations.md",
    "unable": "limitations.md",
    "not able": "limitations.md",
}

# Maps agent name hints to agent detail files
_AGENT_KEYWORDS: Dict[str, str] = {
    "lighting": "agents/lighting.md",
    "light": "agents/lighting.md",
    "hue": "agents/lighting.md",
    "yeelight": "agents/lighting.md",
    "roku": "agents/roku.md",
    "tv": "agents/roku.md",
    "television": "agents/roku.md",
    "calendar": "agents/calendar.md",
    "event": "agents/calendar.md",
    "meeting": "agents/calendar.md",
    "chat": "agents/chat.md",
    "conversation": "agents/chat.md",
    "search": "agents/search.md",
    "google": "agents/search.md",
    "web": "agents/search.md",
    "memory": "agents/memory.md",
    "remember": "agents/memory.md",
    "fact": "agents/memory.md",
    "recall": "agents/memory.md",
    "todo": "agents/todo.md",
    "task": "agents/todo.md",
    "health": "agents/health.md",
    "monitor": "agents/device_monitor.md",
    "device": "agents/device_monitor.md",
    "cpu": "agents/device_monitor.md",
    "ram": "agents/device_monitor.md",
    "disk": "agents/device_monitor.md",
    "scheduler": "agents/scheduler.md",
    "reminder": "agents/scheduler.md",
    "canvas": "agents/canvas.md",
    "homework": "agents/canvas.md",
    "protocol": "agents/protocol.md",
    "workflow": "agents/protocol.md",
    "server manager": "agents/server_manager.md",
    "nlu": "agents/nlu.md",
    "routing": "agents/nlu.md",
    "classify": "agents/nlu.md",
}


class CapabilitiesAgent(NetworkAgent):
    """The capabilities librarian.

    Reads a structured markdown knowledge base and answers questions about
    what Jarvis can do.  Uses progressive disclosure — overview first, then
    drills into specifics on follow-up.
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        knowledge_dir: Optional[str] = None,
    ) -> None:
        super().__init__("CapabilitiesAgent", logger)
        self.ai_client = ai_client
        self._knowledge_dir = Path(knowledge_dir) if knowledge_dir else _KNOWLEDGE_DIR
        self._index_cache: Optional[str] = None
        self._file_cache: Dict[str, str] = {}

        self.intent_map = {
            "describe_capabilities": self._describe_capabilities,
            "explain_capability": self._explain_capability,
        }

    @property
    def description(self) -> str:
        return (
            "Capabilities librarian — answers questions about what Jarvis "
            "can and cannot do using a structured knowledge base"
        )

    @property
    def capabilities(self) -> Set[str]:
        return {"describe_capabilities", "explain_capability"}

    # ------------------------------------------------------------------
    # Knowledge base I/O
    # ------------------------------------------------------------------
    def _read_knowledge_file(self, relative_path: str) -> Optional[str]:
        """Read a knowledge base file, with caching."""
        if relative_path in self._file_cache:
            return self._file_cache[relative_path]

        full_path = self._knowledge_dir / relative_path
        if not full_path.exists():
            return None

        content = full_path.read_text(encoding="utf-8")
        self._file_cache[relative_path] = content
        return content

    def _load_index(self) -> str:
        """Load the top-level index (Level 0 disclosure)."""
        if self._index_cache is None:
            self._index_cache = self._read_knowledge_file("_index.md") or ""
        return self._index_cache

    def _find_relevant_files(self, query: str) -> List[str]:
        """Match a query to relevant knowledge files using keyword lookup."""
        query_lower = query.lower()
        matched: list[str] = []
        seen: set[str] = set()

        # Check agent-level keywords first (more specific)
        for keyword, path in _AGENT_KEYWORDS.items():
            if keyword in query_lower and path not in seen:
                matched.append(path)
                seen.add(path)

        # Then skill-level keywords
        for keyword, path in _SKILL_KEYWORDS.items():
            if keyword in query_lower and path not in seen:
                matched.append(path)
                seen.add(path)

        return matched

    def _gather_context(self, query: str) -> str:
        """Build context string from knowledge base for a given query.

        Progressive disclosure:
        - Broad queries ("what can you do") → index only
        - Targeted queries ("how does calendar work") → skill + agent doc
        - Deep flag forces agent-level detail
        """
        relevant = self._find_relevant_files(query)

        if not relevant:
            # Broad query — return the index
            return self._load_index()

        parts: list[str] = []
        for path in relevant[:3]:  # Cap at 3 files to avoid context bloat
            content = self._read_knowledge_file(path)
            if content:
                parts.append(content)

        if not parts:
            return self._load_index()

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Runtime introspection
    # ------------------------------------------------------------------
    def _get_live_capabilities(self) -> Dict[str, List[str]]:
        """Introspect the agent network for currently registered capabilities."""
        if not self.network:
            return {}
        return dict(self.network.capability_registry)

    def _get_live_agents(self) -> List[str]:
        """Get names of currently registered agents."""
        if not self.network:
            return []
        return list(self.network.agents.keys())

    def _build_runtime_summary(self) -> str:
        """Build a summary of what's actually live right now."""
        agents = self._get_live_agents()
        caps = self._get_live_capabilities()

        if not agents:
            return "No agents currently registered."

        lines = [f"**Live Agents** ({len(agents)}): {', '.join(sorted(agents))}"]
        lines.append(f"**Registered Capabilities** ({len(caps)}):")
        for cap_name in sorted(caps.keys()):
            providers = caps[cap_name]
            lines.append(f"  - `{cap_name}` → {', '.join(providers)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Capability handlers
    # ------------------------------------------------------------------
    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        prompt = data.get("prompt", "")

        handler = self.intent_map.get(capability)
        if not handler:
            await self.send_error(
                message.from_agent,
                f"Unknown capability: {capability}",
                message.request_id,
            )
            return

        try:
            result = await handler(prompt=prompt, data=data)
            await self.send_capability_response(
                to_agent=message.from_agent,
                result=result.to_dict(),
                request_id=message.request_id,
                original_message_id=message.id,
            )
        except Exception as exc:
            await self.send_error(
                message.from_agent,
                f"Capabilities query error: {exc}",
                message.request_id,
            )

    async def _handle_capability_response(self, message: Message) -> None:  # noqa: ARG002
        pass  # Leaf agent — does not request other capabilities

    async def _describe_capabilities(self, **kwargs) -> AgentResponse:
        """High-level overview of all capabilities (Level 0/1 disclosure)."""
        prompt = kwargs.get("prompt", "")
        context = self._gather_context(prompt)
        runtime = self._build_runtime_summary()

        system_prompt = (
            "You are Jarvis's capabilities librarian. You have access to a "
            "structured knowledge base describing every capability in the system. "
            "Answer the user's question using ONLY the knowledge base content "
            "provided below. Be concise and well-organized.\n\n"
            "Use progressive disclosure: give a high-level overview first. "
            "If the user asks about something specific, drill into details. "
            "Always mention which capabilities are actually live right now.\n\n"
            "KNOWLEDGE BASE:\n" + context + "\n\n"
            "RUNTIME STATE:\n" + runtime + "\n\n"
            "Respond naturally — no JSON, no code blocks unless showing examples. "
            "If asked about something Jarvis cannot do, say so clearly."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt or "What can you do?"},
        ]

        try:
            response, _ = await self.ai_client.weak_chat(messages, [])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception:
            # Fallback: return the index directly without AI synthesis
            text = context

        return AgentResponse.success_response(
            response=text,
            data={"live_agents": self._get_live_agents()},
            metadata={"agent": "capabilities"},
        )

    async def _explain_capability(self, **kwargs) -> AgentResponse:
        """Deep dive on a specific capability or agent (Level 2 disclosure)."""
        prompt = kwargs.get("prompt", "")
        context = self._gather_context(prompt)

        # If we couldn't find specific docs, add the limitations file
        if context == self._load_index():
            limitations = self._read_knowledge_file("limitations.md")
            if limitations:
                context += "\n\n---\n\n" + limitations

        runtime = self._build_runtime_summary()

        system_prompt = (
            "You are Jarvis's capabilities librarian. The user is asking about "
            "a specific capability or feature. Provide detailed information "
            "from the knowledge base below. Include:\n"
            "- What it does and example phrases\n"
            "- Requirements and configuration needed\n"
            "- Whether it is currently active (check runtime state)\n"
            "- Any limitations or caveats\n\n"
            "KNOWLEDGE BASE:\n" + context + "\n\n"
            "RUNTIME STATE:\n" + runtime + "\n\n"
            "Be thorough but organized. Use the knowledge base — don't invent "
            "capabilities that aren't documented."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response, _ = await self.ai_client.weak_chat(messages, [])
            text = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            text = context

        return AgentResponse.success_response(
            response=text,
            data={"live_agents": self._get_live_agents()},
            metadata={"agent": "capabilities"},
        )
