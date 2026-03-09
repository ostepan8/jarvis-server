"""Mission data structures for coordinator + lead agent pattern.

This module defines the data structures used by the coordinator to create
mission briefs and by lead agents to manage recruitment budgets and context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class MissionComplexity(Enum):
    """Complexity classification for incoming requests."""

    SIMPLE = "simple"
    COMPLEX = "complex"


@dataclass
class MissionBudget:
    """Resource budget for a mission, controlling recruitment depth and limits.

    Attributes:
        max_depth: Maximum nesting depth for recruitment chains
        remaining_depth: Current remaining depth (decremented on each recruit)
        deadline: Absolute timestamp (time.time()) when the mission expires
        max_recruitments: Total recruitment calls allowed for the mission
        remaining_recruitments: Remaining recruitment calls available
    """

    max_depth: int = 3
    remaining_depth: int = 3
    deadline: float = 0.0
    max_recruitments: int = 5
    remaining_recruitments: int = 5

    @property
    def time_remaining(self) -> float:
        """Seconds remaining before the mission deadline."""
        return max(0.0, self.deadline - time.time())

    @property
    def is_expired(self) -> bool:
        """Whether the mission has exceeded its deadline."""
        return time.time() >= self.deadline

    @property
    def can_recruit(self) -> bool:
        """Whether recruitment is still allowed within budget constraints."""
        return (
            self.remaining_depth > 0
            and self.remaining_recruitments > 0
            and not self.is_expired
        )

    def child_budget(self) -> MissionBudget:
        """Create a child budget with decremented depth and recruitments.

        Returns:
            A new MissionBudget with depth and recruitments decremented by 1.
        """
        return MissionBudget(
            max_depth=self.max_depth,
            remaining_depth=self.remaining_depth - 1,
            deadline=self.deadline,
            max_recruitments=self.max_recruitments,
            remaining_recruitments=self.remaining_recruitments - 1,
        )


@dataclass
class MissionContext:
    """Accumulated context for a mission, tracking recruitment results and history.

    Attributes:
        user_input: The original user request
        conversation_history: Prior conversation turns
        recruitment_results: Results from recruited agents
        recruitment_chain: Agent names visited in the current recruitment chain
    """

    user_input: str = ""
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    recruitment_results: List[Dict[str, Any]] = field(default_factory=list)
    recruitment_chain: List[str] = field(default_factory=list)

    def add_result(self, agent: str, capability: str, result: Any) -> None:
        """Record a recruitment result.

        Args:
            agent: Name of the agent that produced the result
            capability: The capability that was executed
            result: The result data from the agent
        """
        self.recruitment_results.append(
            {
                "agent": agent,
                "capability": capability,
                "result": result,
            }
        )

    def has_visited(self, agent: str) -> bool:
        """Check if an agent has already been visited in the recruitment chain.

        Args:
            agent: Agent name to check

        Returns:
            True if the agent is already in the recruitment chain
        """
        return agent in self.recruitment_chain

    def format_context_for_llm(self) -> str:
        """Format the accumulated context into a string suitable for LLM prompts.

        Returns:
            A formatted string summarizing recruitment results and history.
        """
        parts: List[str] = []

        if self.recruitment_results:
            parts.append("## Previous recruitment results")
            for i, entry in enumerate(self.recruitment_results, 1):
                agent = entry.get("agent", "unknown")
                capability = entry.get("capability", "unknown")
                result = entry.get("result", {})

                # Extract human-readable response if available
                if isinstance(result, dict):
                    response_text = result.get("response", str(result))
                else:
                    response_text = str(result)

                parts.append(f"{i}. {agent}.{capability}: {response_text}")

        if self.conversation_history:
            parts.append("\n## Conversation history")
            for turn in self.conversation_history[-5:]:
                user = turn.get("user", "")
                assistant = turn.get("assistant", "")
                if user:
                    parts.append(f"User: {user}")
                if assistant:
                    parts.append(f"Assistant: {assistant}")

        return "\n".join(parts) if parts else ""


@dataclass
class MissionBrief:
    """Complete mission specification created by the coordinator.

    Attributes:
        user_input: The original user request
        complexity: Classified complexity level
        lead_agent: Name of the agent selected to lead the mission
        lead_capability: The capability to invoke on the lead agent
        budget: Resource budget for the mission
        context: Accumulated mission context
        available_capabilities: Map of agent names to their capability lists
        metadata: Additional metadata for the mission
    """

    user_input: str
    complexity: MissionComplexity
    lead_agent: str
    lead_capability: str
    budget: MissionBudget
    context: MissionContext
    available_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the mission brief to a dictionary for message passing.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "user_input": self.user_input,
            "complexity": self.complexity.value,
            "lead_agent": self.lead_agent,
            "lead_capability": self.lead_capability,
            "budget": {
                "max_depth": self.budget.max_depth,
                "remaining_depth": self.budget.remaining_depth,
                "deadline": self.budget.deadline,
                "max_recruitments": self.budget.max_recruitments,
                "remaining_recruitments": self.budget.remaining_recruitments,
            },
            "context": {
                "user_input": self.context.user_input,
                "conversation_history": self.context.conversation_history,
                "recruitment_results": self.context.recruitment_results,
                "recruitment_chain": self.context.recruitment_chain,
            },
            "available_capabilities": self.available_capabilities,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MissionBrief:
        """Deserialize a mission brief from a dictionary.

        Args:
            data: Dictionary representation of a MissionBrief

        Returns:
            MissionBrief instance
        """
        budget_data = data.get("budget", {})
        budget = MissionBudget(
            max_depth=budget_data.get("max_depth", 3),
            remaining_depth=budget_data.get("remaining_depth", 3),
            deadline=budget_data.get("deadline", 0.0),
            max_recruitments=budget_data.get("max_recruitments", 5),
            remaining_recruitments=budget_data.get("remaining_recruitments", 5),
        )

        context_data = data.get("context", {})
        context = MissionContext(
            user_input=context_data.get("user_input", ""),
            conversation_history=context_data.get("conversation_history", []),
            recruitment_results=context_data.get("recruitment_results", []),
            recruitment_chain=context_data.get("recruitment_chain", []),
        )

        return cls(
            user_input=data.get("user_input", ""),
            complexity=MissionComplexity(data.get("complexity", "simple")),
            lead_agent=data.get("lead_agent", ""),
            lead_capability=data.get("lead_capability", ""),
            budget=budget,
            context=context,
            available_capabilities=data.get("available_capabilities", {}),
            metadata=data.get("metadata", {}),
        )
