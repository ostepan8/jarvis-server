from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...ai_clients.base import BaseAIClient
from ...logging import JarvisLogger
from ...core.profile import AgentProfile
from .tools import tools as chat_tools


class ChatAgent(NetworkAgent):
    """Lightweight conversational agent that remembers user facts."""

    def __init__(
        self, ai_client: BaseAIClient, logger: Optional[JarvisLogger] = None
    ) -> None:
        super().__init__("ChatAgent", logger, memory=None, profile=AgentProfile())
        self.ai_client = ai_client
        self.tools = chat_tools
        self.intent_map = {
            "chat": self._process_chat,
            "store_fact": self._store_fact,
            "get_facts": self._get_facts,
            "update_profile": self._update_profile,
        }
        self.system_prompt = (
            "You are a friendly assistant chatting with the user. "
            "Use the available tools to remember facts and preferences when helpful."
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    @property
    def description(self) -> str:
        return "Conversational agent that chats and stores simple facts"

    @property
    def capabilities(self) -> Set[str]:
        return {"chat"}

    # ------------------------------------------------------------------
    # Capability dispatch
    # ------------------------------------------------------------------
    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability != "chat":
            return

        data = message.content.get("data", {})
        prompt = data.get("prompt")
        context = data.get("context", {})
        conversation_history = context.get("conversation_history", [])

        if not isinstance(prompt, str):
            await self.send_error(
                message.from_agent, "Invalid prompt", message.request_id
            )
            return

        result = await self._process_chat(prompt, conversation_history)
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        # ChatAgent does not initiate capability requests currently
        pass

    # ------------------------------------------------------------------
    # Chat processing
    # ------------------------------------------------------------------
    async def _process_chat(
        self, user_input: str, conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Add conversation history (last 5 turns for context)
        # Validate content to avoid API errors with None/empty values
        if conversation_history:
            for turn in conversation_history[-5:]:
                user_content = turn.get("user") or ""
                assistant_content = turn.get("assistant") or ""

                # Only add if content is non-empty
                if user_content.strip():
                    messages.append({"role": "user", "content": user_content})
                if assistant_content.strip():
                    messages.append({"role": "assistant", "content": assistant_content})

        # Add current user input
        messages.append({"role": "user", "content": user_input})

        actions: List[Dict[str, Any]] = []
        iterations = 0
        message = None
        tool_calls = None

        while iterations < 5:
            message, tool_calls = await self.ai_client.strong_chat(messages, self.tools)
            if not tool_calls:
                break

            # Build assistant message with tool_calls
            # OpenAI requires tool_calls field when there are tool messages following
            content = message.content if message.content is not None else ""
            assistant_msg = {
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ],
            }
            messages.append(assistant_msg)

            for call in tool_calls:
                fn = call.function.name
                args = json.loads(call.function.arguments)
                try:
                    result = await self.run_capability(fn, **args)
                except Exception as exc:
                    result = {"error": str(exc)}
                actions.append({"function": fn, "arguments": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
            iterations += 1

        response_text = message.content if message else ""

        # Store conversation in memory
        user_id = getattr(self, "current_user_id", None)
        try:
            await self.store_memory(
                f"User: {user_input}\nAssistant: {response_text}",
                {"type": "conversation"},
                user_id=user_id,
            )
        except Exception:
            pass

        # Automatically extract and store facts from the conversation
        if user_id is not None and user_input:
            try:
                conversation_text = f"User: {user_input}\nAssistant: {response_text}"
                if self.network:
                    req_id = await self.request_capability(
                        "extract_facts",
                        {
                            "conversation_text": conversation_text,
                            "user_id": user_id,
                        },
                    )
                    # Don't wait for this - run it asynchronously
                    # Facts will be stored by MemoryAgent
            except Exception:
                pass  # Don't fail the chat if fact extraction fails

        return {"response": response_text, "actions": actions}

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------
    async def _store_fact(self, fact: str) -> str:
        user_id = getattr(self, "current_user_id", None)
        await self.store_memory(fact, {"type": "fact"}, user_id=user_id)

        # Also store as structured fact if user_id is available
        if user_id is not None and self.network:
            try:
                req_id = await self.request_capability(
                    "store_fact",
                    {
                        "fact_text": fact,
                        "category": "general",
                        "user_id": user_id,
                        "source": "explicit",
                    },
                )
            except Exception:
                pass

        return "fact stored"

    async def _get_facts(self, query: str, top_k: int = 3) -> str:
        user_id = getattr(self, "current_user_id", None)
        results = await self.search_memory(query, top_k=top_k, user_id=user_id)
        if not results:
            return "no relevant facts found"
        return "\n".join(r.get("text", "") for r in results)

    async def _update_profile(self, field: str, value: str) -> str:
        self.update_profile(**{field: value})
        user_id = getattr(self, "current_user_id", None)
        await self.store_memory(
            f"Updated profile {field} to {value}",
            {"type": "preference", "field": field},
            user_id=user_id,
        )

        # Also store as a structured fact
        if user_id is not None and self.network:
            try:
                req_id = await self.request_capability(
                    "store_fact",
                    {
                        "fact_text": f"Profile {field} is {value}",
                        "category": "preference",
                        "entity": field,
                        "user_id": user_id,
                        "source": "explicit",
                    },
                )
            except Exception:
                pass

        return f"updated {field}"
