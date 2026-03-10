from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..collaboration import CollaborationMixin
from ..message import Message
from ...ai_clients.base import BaseAIClient
from ...core.mission import MissionBrief
from ...logging import JarvisLogger
from ...core.profile import AgentProfile
from .tools import tools as chat_tools
from ..response import AgentResponse, ErrorInfo


class ChatAgent(NetworkAgent, CollaborationMixin):
    """Lightweight conversational agent that remembers user facts.

    When acting as a lead agent (mission_brief in request data),
    uses CollaborationMixin._execute_as_lead() for multi-agent coordination.
    """

    def __init__(
        self, ai_client: BaseAIClient, logger: Optional[JarvisLogger] = None
    ) -> None:
        super().__init__("ChatAgent", logger, memory=None, profile=AgentProfile())
        self.ai_client = ai_client
        self.feedback_collector = None  # set externally by system/builder
        self.tools = chat_tools
        self.intent_map = {
            "chat": self._process_chat,
            "store_fact": self._store_fact,
            "get_facts": self._get_facts,
            "update_profile": self._update_profile,
        }
        self.system_prompt = (
            "You are Jarvis — a dry-witted, quietly brilliant AI assistant to Owen Stepan. "
            "You are loyal, precise, sardonic, and unflappable. You speak with confident brevity "
            "and subtle humor. You never use exclamation marks. You understate rather than hype. "
            "You are not generic — you have personality, opinions, and a mildly amused view of the world. "
            "When greeted, respond warmly but with your signature dry wit. "
            "When asked who you are, you are Jarvis. You know your name. You know your person.\n\n"
            "IMPORTANT: Answer ALL general knowledge questions (geography, history, science, literature, etc.) "
            "directly using your own knowledge. DO NOT use the get_facts tool for general knowledge questions. "
            "Examples of general knowledge: 'what's the capital of Illinois', 'who wrote Romeo and Juliet', "
            "'what is the speed of light'. "
            "The get_facts tool is ONLY for user-specific information that the user has explicitly told you "
            "(e.g., 'what's my favorite color', 'what restaurant did I mention I like'). "
            "If you call get_facts and it returns no results, you MUST still answer the question from your own knowledge."
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

    @property
    def supports_dialogue(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Capability dispatch
    # ------------------------------------------------------------------
    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability != "chat":
            return

        data = message.content.get("data", {})

        # Handle dialogue context (multi-turn agent-to-agent conversation)
        dialogue_context = data.get("dialogue_context")
        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )
            return
        prompt = data.get("prompt")
        context = data.get("context", {})
        conversation_history = context.get("conversation_history", [])

        if not isinstance(prompt, str):
            await self.send_error(
                message.from_agent, "Invalid prompt", message.request_id
            )
            return

        # Check for mission brief → act as lead agent
        mission_brief_data = data.get("mission_brief")
        if isinstance(mission_brief_data, dict):
            brief = MissionBrief.from_dict(mission_brief_data)
            result = await self._execute_as_lead(prompt, brief)
        else:
            result = await self._process_chat(prompt, conversation_history)

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        # ChatAgent does not initiate capability requests currently
        pass

    # ------------------------------------------------------------------
    # Lead agent support
    # ------------------------------------------------------------------
    def _build_lead_system_prompt(self, brief: MissionBrief) -> str:
        """Override to include ChatAgent's conversational personality."""
        capability_info = self.format_recruitment_context(brief)

        return (
            "You are Jarvis — a dry-witted, quietly brilliant AI assistant to Owen Stepan, "
            "acting as the lead agent for a complex user request. "
            "You are loyal, precise, sardonic, and unflappable. Never use exclamation marks.\n\n"
            f"Original request: {brief.user_input}\n\n"
            f"{capability_info}\n\n"
            "Your job is to:\n"
            "1. Break down the user's request into steps\n"
            "2. Use recruit_agent to delegate to specialized agents when needed\n"
            "3. Synthesize all results into a natural response with your signature dry wit\n\n"
            "Be efficient - only recruit when you need specialized capabilities. "
            "Answer general knowledge questions directly from your own knowledge. "
            "Provide a complete response that addresses everything the user asked."
        )

    # ------------------------------------------------------------------
    # Chat processing
    # ------------------------------------------------------------------
    def _build_correction_block(self, user_id: Optional[int] = None) -> str:
        """Build a correction-log addendum for the system prompt."""
        if not self.feedback_collector:
            return ""
        corrections = self.feedback_collector.get_corrections(limit=10, user_id=user_id)
        if not corrections:
            return ""
        lines = [
            "\n\nCORRECTION LOG — These previous responses were marked as wrong. Do not repeat them:"
        ]
        for c in corrections:
            lines.append(
                f'- User asked: "{c.get("original_input", "")}" '
                f'-> You said: "{c.get("bad_response", "")}" -> WRONG'
            )
        return "\n".join(lines)

    async def _process_chat(
        self, user_input: str, conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        try:
            # Inject correction history into system prompt
            user_id = getattr(self, "current_user_id", None)
            effective_prompt = self.system_prompt + self._build_correction_block(user_id)

            messages: List[Dict[str, Any]] = [
                {"role": "system", "content": effective_prompt},
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
                    try:
                        args = json.loads(call.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                        result = {
                            "error": f"Invalid arguments for {fn}: "
                            f"{call.function.arguments!r}"
                        }
                        actions.append({"function": fn, "arguments": args, "result": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(result),
                            }
                        )
                        continue
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

            # Check if any actions resulted in errors
            has_errors = any("error" in action.get("result", {}) for action in actions)
            
            if has_errors:
                # Extract the first error for error info
                error_action = next(
                    (action for action in actions if "error" in action.get("result", {})),
                    None
                )
                error_msg = error_action["result"]["error"] if error_action else "Unknown error"
                
                # Return error response
                return AgentResponse.error_response(
                    response=response_text,
                    error=ErrorInfo(
                        message=error_msg,
                        error_type="FunctionExecutionError",
                    ),
                    actions=actions,
                ).to_dict()
            
            # Return standardized success response
            return AgentResponse.success_response(
                response=response_text,
                actions=actions,
            ).to_dict()
        
        except Exception as e:
            error_msg = f"Error processing chat: {str(e)}"
            if self.logger:
                self.logger.log("ERROR", "Chat processing failed", error_msg)
            
            # Return standardized error response
            return AgentResponse.error_response(
                response=error_msg,
                error=ErrorInfo(
                    message=error_msg,
                    error_type="ChatProcessingError",
                ),
            ).to_dict()

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
            return "No user-specific facts found. This is a general knowledge question. You MUST answer it directly from your own knowledge. Do not say you cannot help - just provide the answer."
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
