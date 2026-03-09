"""Collaboration mixin for lead agent pattern.

Provides the ability for agents to recruit other agents dynamically,
manage recruitment budgets, and execute as mission leads.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, List

from ..core.errors import (
    BudgetExhaustedError,
    CapabilityNotFoundError,
    CircularRecruitmentError,
)
from ..core.mission import MissionBrief
from .response import AgentResponse


class CollaborationMixin:
    """Mixin that adds recruitment and lead-agent capabilities to a NetworkAgent.

    When mixed into a NetworkAgent subclass, this provides:
    - recruit(): ask another agent to perform a capability
    - _execute_as_lead(): run an LLM tool-calling loop with own tools + recruit_agent
    - Budget enforcement, cycle detection, and context accumulation
    """

    # Lock protecting budget mutations during parallel recruits
    _budget_lock: asyncio.Lock

    @property
    def budget_lock(self) -> asyncio.Lock:
        """Lazy-init lock to avoid __init__ requirements in mixin."""
        if not hasattr(self, "_budget_lock") or self._budget_lock is None:
            self._budget_lock = asyncio.Lock()
        return self._budget_lock

    async def recruit(
        self,
        capability: str,
        data: Dict[str, Any],
        brief: MissionBrief,
        timeout: float | None = None,
    ) -> Dict[str, Any]:
        """Recruit another agent to perform a capability.

        Args:
            capability: The capability to request (e.g. "get_weather")
            data: Data to send with the capability request
            brief: The current mission brief (contains budget + context)
            timeout: Optional timeout override (defaults to budget.time_remaining)

        Returns:
            Result dict from the recruited agent

        Raises:
            BudgetExhaustedError: If budget has no remaining depth or recruitments
            CircularRecruitmentError: If the target agent is already in the chain
            CapabilityNotFoundError: If no agent provides the requested capability
            asyncio.TimeoutError: If the recruitment times out
        """
        budget = brief.budget
        context = brief.context

        # Atomic budget check + decrement under lock to prevent race
        # conditions when multiple recruits run concurrently
        async with self.budget_lock:
            if not budget.can_recruit:
                raise BudgetExhaustedError(
                    f"Cannot recruit: depth={budget.remaining_depth}, "
                    f"recruitments={budget.remaining_recruitments}, "
                    f"expired={budget.is_expired}",
                    details={
                        "remaining_depth": budget.remaining_depth,
                        "remaining_recruitments": budget.remaining_recruitments,
                        "is_expired": budget.is_expired,
                    },
                )

            # Guard: find provider agent for this capability
            provider_agent = self._find_capability_provider(capability, brief)
            if not provider_agent:
                raise CapabilityNotFoundError(
                    f"No agent provides capability '{capability}'",
                    details={"capability": capability},
                )

            # Guard: cycle detection
            if context.has_visited(provider_agent):
                raise CircularRecruitmentError(
                    f"Circular recruitment detected: {' -> '.join(context.recruitment_chain)} -> {provider_agent}",
                    details={"chain": context.recruitment_chain + [provider_agent]},
                )

            # Decrement parent budget (inside lock)
            budget.remaining_recruitments -= 1

        # Calculate timeout
        effective_timeout = timeout if timeout is not None else budget.time_remaining

        # Make the request via the network
        request_id = str(uuid.uuid4())
        result = await self._request_and_wait_for_agent(
            capability=capability,
            data=data,
            request_id=request_id,
            timeout=effective_timeout,
        )

        # Record result in context
        context.add_result(provider_agent, capability, result)

        return result

    def get_recruitable_capabilities(
        self, brief: MissionBrief
    ) -> Dict[str, List[str]]:
        """Get capabilities available for recruitment, excluding own agent.

        Args:
            brief: Mission brief containing available capabilities

        Returns:
            Dict mapping agent names to their capability lists,
            excluding the current agent.
        """
        return {
            agent: caps
            for agent, caps in brief.available_capabilities.items()
            if agent != self.name
        }

    def format_recruitment_context(self, brief: MissionBrief) -> str:
        """Format available capabilities into a string for LLM context.

        Args:
            brief: Mission brief containing available capabilities

        Returns:
            Formatted string describing available agents and capabilities.
        """
        recruitable = self.get_recruitable_capabilities(brief)
        if not recruitable:
            return "No other agents available for recruitment."

        lines = ["Available agents you can recruit:"]
        for agent, caps in recruitable.items():
            lines.append(f"  - {agent}: {', '.join(caps)}")
        return "\n".join(lines)

    def _build_recruit_tool_definition(
        self, brief: MissionBrief
    ) -> Dict[str, Any]:
        """Build the recruit_agent tool spec dynamically from available capabilities.

        Args:
            brief: Mission brief with available capabilities

        Returns:
            OpenAI-format tool definition for the recruit_agent function.
        """
        recruitable = self.get_recruitable_capabilities(brief)

        # Build enum of valid capabilities
        all_capabilities: List[str] = []
        for caps in recruitable.values():
            all_capabilities.extend(caps)
        all_capabilities = sorted(set(all_capabilities))

        return {
            "type": "function",
            "function": {
                "name": "recruit_agent",
                "description": (
                    "Recruit another agent to perform a specific capability. "
                    "Use this to delegate tasks to specialized agents."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "capability": {
                            "type": "string",
                            "description": "The capability to request from another agent",
                            "enum": all_capabilities if all_capabilities else ["none"],
                        },
                        "prompt": {
                            "type": "string",
                            "description": "The natural language instruction for the recruited agent",
                        },
                    },
                    "required": ["capability", "prompt"],
                },
            },
        }

    async def _execute_as_lead(
        self, message: str, brief: MissionBrief
    ) -> Dict[str, Any]:
        """Execute as lead agent with LLM tool-calling loop.

        This method:
        1. Checks budget upfront (returns partial if already expired)
        2. Builds a system prompt with mission context + available capabilities
        3. Combines agent's own tools with the recruit_agent tool
        4. Runs an LLM tool-calling loop with deadline checks each iteration
        5. Executes tool calls concurrently via asyncio.gather
        6. Returns the final synthesized response (or partial on expiry)

        Args:
            message: The user's input message
            brief: The mission brief with budget and context

        Returns:
            AgentResponse dict with the synthesized result
        """
        # Bail early if budget already expired
        if brief.budget.is_expired:
            return AgentResponse.success_response(
                response="The request deadline has passed before processing could begin.",
                actions=[],
                metadata={
                    "lead_agent": self.name,
                    "mission_complexity": "complex",
                    "budget_expired": True,
                },
            ).to_dict()

        # Build system prompt
        system_prompt = self._build_lead_system_prompt(brief)

        # Build tools: own tools + recruit_agent
        tools = list(getattr(self, "tools", []))
        recruit_tool = self._build_recruit_tool_definition(brief)
        tools.append(recruit_tool)

        # Build messages
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add context from previous recruitments
        context_str = brief.context.format_context_for_llm()
        if context_str:
            messages.append(
                {"role": "system", "content": f"Context:\n{context_str}"}
            )

        messages.append({"role": "user", "content": message})

        actions: List[Dict[str, Any]] = []
        iterations = 0
        max_iterations = brief.budget.max_recruitments + 3  # Allow some extra for own tools
        response_message = None

        while iterations < max_iterations:
            # Check deadline each iteration
            if brief.budget.is_expired:
                break

            # Wrap LLM call with budget timeout to prevent API hangs
            llm_timeout = brief.budget.time_remaining
            try:
                response_message, tool_calls = await asyncio.wait_for(
                    self.ai_client.strong_chat(messages, tools),
                    timeout=llm_timeout if llm_timeout > 0 else 0.1,
                )
            except asyncio.TimeoutError:
                break
            if not tool_calls:
                break

            # Build assistant message with tool_calls
            content = response_message.content if response_message.content is not None else ""
            assistant_msg: Dict[str, Any] = {
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

            # Execute tool calls concurrently
            async def _exec_tool(call):
                fn_name = call.function.name
                try:
                    args = json.loads(call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                    return call, fn_name, args, {
                        "error": f"Invalid arguments for {fn_name}: "
                        f"{call.function.arguments!r}"
                    }
                if fn_name == "recruit_agent":
                    result = await self._handle_recruit_tool_call(args, brief)
                else:
                    try:
                        result = await self.run_capability(fn_name, **args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                return call, fn_name, args, result

            tool_results = await asyncio.gather(
                *[_exec_tool(c) for c in tool_calls]
            )

            for call, fn_name, args, result in tool_results:
                actions.append(
                    {"function": fn_name, "arguments": args, "result": result}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(
                            result if isinstance(result, (dict, list, str)) else str(result)
                        ),
                    }
                )

            iterations += 1

        response_text = response_message.content if response_message else ""

        # If we broke out due to deadline with no final LLM response, provide partial
        if not response_text and brief.budget.is_expired and actions:
            response_text = (
                "I gathered some information but ran out of time to complete "
                "the full request."
            )

        metadata: Dict[str, Any] = {
            "lead_agent": self.name,
            "mission_complexity": "complex",
        }
        if brief.budget.is_expired:
            metadata["budget_expired"] = True

        return AgentResponse.success_response(
            response=response_text,
            actions=actions,
            metadata=metadata,
        ).to_dict()

    async def _handle_recruit_tool_call(
        self, args: Dict[str, Any], brief: MissionBrief
    ) -> Dict[str, Any]:
        """Handle a recruit_agent tool call from the LLM.

        Args:
            args: Tool call arguments with "capability" and "prompt"
            brief: Current mission brief

        Returns:
            Result dict from the recruited agent, or error dict on failure
        """
        capability = args.get("capability", "")
        prompt = args.get("prompt", "")

        try:
            result = await self.recruit(
                capability=capability,
                data={"prompt": prompt, "input": prompt},
                brief=brief,
            )
            return result if isinstance(result, dict) else {"response": str(result)}
        except (BudgetExhaustedError, CircularRecruitmentError, CapabilityNotFoundError) as exc:
            return {"error": str(exc)}
        except Exception as exc:
            return {"error": f"Recruitment failed: {str(exc)}"}

    def _build_lead_system_prompt(self, brief: MissionBrief) -> str:
        """Build the system prompt for lead agent execution.

        Subclasses can override this to add agent-specific personality.

        Args:
            brief: Mission brief with context

        Returns:
            System prompt string
        """
        capability_info = self.format_recruitment_context(brief)

        return (
            f"You are {self.name}, acting as the lead agent for a complex user request.\n\n"
            f"Original request: {brief.user_input}\n\n"
            f"{capability_info}\n\n"
            "Your job is to fulfill the user's request by:\n"
            "1. Using your own capabilities when appropriate\n"
            "2. Recruiting other agents via the recruit_agent tool when you need specialized help\n"
            "3. Synthesizing all results into a coherent final response\n\n"
            "Be efficient - only recruit when needed. Provide a complete, natural response."
        )

    def _find_capability_provider(
        self, capability: str, brief: MissionBrief
    ) -> str | None:
        """Find the agent that provides a given capability.

        Args:
            capability: The capability to look up
            brief: Mission brief with available capabilities

        Returns:
            Agent name or None if not found
        """
        for agent, caps in brief.available_capabilities.items():
            if capability in caps and agent != self.name:
                return agent
        return None
