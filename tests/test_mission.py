"""Tests for mission data structures (Phase 1).

Tests cover MissionBudget arithmetic, MissionContext tracking,
MissionBrief serialization, and edge cases.
"""

import time

import pytest

from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)
from jarvis.core.errors import BudgetExhaustedError, CircularRecruitmentError


class TestMissionComplexity:
    """Tests for MissionComplexity enum."""

    def test_simple_value(self):
        assert MissionComplexity.SIMPLE.value == "simple"

    def test_complex_value(self):
        assert MissionComplexity.COMPLEX.value == "complex"

    def test_from_string(self):
        assert MissionComplexity("simple") == MissionComplexity.SIMPLE
        assert MissionComplexity("complex") == MissionComplexity.COMPLEX


class TestMissionBudget:
    """Tests for MissionBudget resource tracking."""

    def test_default_values(self):
        budget = MissionBudget()
        assert budget.max_depth == 3
        assert budget.remaining_depth == 3
        assert budget.max_recruitments == 5
        assert budget.remaining_recruitments == 5

    def test_child_budget_decrements_depth(self):
        budget = MissionBudget(
            remaining_depth=3,
            remaining_recruitments=5,
            deadline=time.time() + 60,
        )
        child = budget.child_budget()
        assert child.remaining_depth == 2
        assert child.remaining_recruitments == 4
        assert child.deadline == budget.deadline
        assert child.max_depth == budget.max_depth

    def test_child_budget_preserves_max_depth(self):
        budget = MissionBudget(max_depth=5, remaining_depth=3, deadline=time.time() + 60)
        child = budget.child_budget()
        assert child.max_depth == 5

    def test_can_recruit_with_remaining_budget(self):
        budget = MissionBudget(
            remaining_depth=2,
            remaining_recruitments=3,
            deadline=time.time() + 60,
        )
        assert budget.can_recruit is True

    def test_cannot_recruit_zero_depth(self):
        budget = MissionBudget(
            remaining_depth=0,
            remaining_recruitments=3,
            deadline=time.time() + 60,
        )
        assert budget.can_recruit is False

    def test_cannot_recruit_zero_recruitments(self):
        budget = MissionBudget(
            remaining_depth=2,
            remaining_recruitments=0,
            deadline=time.time() + 60,
        )
        assert budget.can_recruit is False

    def test_cannot_recruit_expired_deadline(self):
        budget = MissionBudget(
            remaining_depth=2,
            remaining_recruitments=3,
            deadline=time.time() - 1,  # Already expired
        )
        assert budget.can_recruit is False

    def test_is_expired_past_deadline(self):
        budget = MissionBudget(deadline=time.time() - 1)
        assert budget.is_expired is True

    def test_is_not_expired_future_deadline(self):
        budget = MissionBudget(deadline=time.time() + 60)
        assert budget.is_expired is False

    def test_time_remaining_positive(self):
        budget = MissionBudget(deadline=time.time() + 10)
        assert budget.time_remaining > 0
        assert budget.time_remaining <= 10

    def test_time_remaining_zero_when_expired(self):
        budget = MissionBudget(deadline=time.time() - 10)
        assert budget.time_remaining == 0.0

    def test_successive_child_budgets(self):
        """Test creating multiple nested child budgets."""
        budget = MissionBudget(
            max_depth=3,
            remaining_depth=3,
            remaining_recruitments=5,
            deadline=time.time() + 60,
        )
        child1 = budget.child_budget()
        child2 = child1.child_budget()
        child3 = child2.child_budget()

        assert child1.remaining_depth == 2
        assert child2.remaining_depth == 1
        assert child3.remaining_depth == 0
        assert child3.can_recruit is False

    def test_zero_budget_creation(self):
        """Edge case: budget created with zero values."""
        budget = MissionBudget(
            max_depth=0,
            remaining_depth=0,
            deadline=time.time() + 60,
            max_recruitments=0,
            remaining_recruitments=0,
        )
        assert budget.can_recruit is False


class TestMissionContext:
    """Tests for MissionContext tracking."""

    def test_empty_context(self):
        ctx = MissionContext()
        assert ctx.user_input == ""
        assert ctx.conversation_history == []
        assert ctx.recruitment_results == []
        assert ctx.recruitment_chain == []

    def test_add_result(self):
        ctx = MissionContext()
        ctx.add_result("WeatherAgent", "get_weather", {"temp": 72})
        assert len(ctx.recruitment_results) == 1
        assert ctx.recruitment_results[0]["agent"] == "WeatherAgent"
        assert ctx.recruitment_results[0]["capability"] == "get_weather"
        assert ctx.recruitment_results[0]["result"] == {"temp": 72}

    def test_add_multiple_results(self):
        ctx = MissionContext()
        ctx.add_result("WeatherAgent", "get_weather", {"temp": 72})
        ctx.add_result("LightingAgent", "set_color", {"success": True})
        assert len(ctx.recruitment_results) == 2

    def test_has_visited_true(self):
        ctx = MissionContext(recruitment_chain=["ChatAgent", "WeatherAgent"])
        assert ctx.has_visited("ChatAgent") is True
        assert ctx.has_visited("WeatherAgent") is True

    def test_has_visited_false(self):
        ctx = MissionContext(recruitment_chain=["ChatAgent"])
        assert ctx.has_visited("WeatherAgent") is False

    def test_has_visited_empty_chain(self):
        ctx = MissionContext()
        assert ctx.has_visited("ChatAgent") is False

    def test_format_context_for_llm_empty(self):
        ctx = MissionContext()
        assert ctx.format_context_for_llm() == ""

    def test_format_context_for_llm_with_results(self):
        ctx = MissionContext()
        ctx.add_result("WeatherAgent", "get_weather", {"response": "72°F and sunny"})
        formatted = ctx.format_context_for_llm()
        assert "WeatherAgent" in formatted
        assert "get_weather" in formatted
        assert "72°F and sunny" in formatted

    def test_format_context_for_llm_with_history(self):
        ctx = MissionContext(
            conversation_history=[
                {"user": "Hello", "assistant": "Hi there!"},
                {"user": "What's the weather?", "assistant": "Let me check."},
            ]
        )
        formatted = ctx.format_context_for_llm()
        assert "User: Hello" in formatted
        assert "Assistant: Hi there!" in formatted

    def test_format_context_for_llm_with_non_dict_result(self):
        ctx = MissionContext()
        ctx.add_result("SearchAgent", "search", "Some search results")
        formatted = ctx.format_context_for_llm()
        assert "Some search results" in formatted

    def test_format_context_truncates_long_history(self):
        """Only last 5 turns of conversation history should be included."""
        ctx = MissionContext(
            conversation_history=[
                {"user": f"msg{i}", "assistant": f"reply{i}"} for i in range(10)
            ]
        )
        formatted = ctx.format_context_for_llm()
        # Should have last 5 turns (5-9)
        assert "msg5" in formatted
        assert "msg9" in formatted
        # First entries should be excluded
        assert "msg0" not in formatted
        assert "msg4" not in formatted


class TestMissionBrief:
    """Tests for MissionBrief creation and serialization."""

    def _make_brief(self, **overrides) -> MissionBrief:
        defaults = {
            "user_input": "Check weather and set lights",
            "complexity": MissionComplexity.COMPLEX,
            "lead_agent": "ChatAgent",
            "lead_capability": "chat",
            "budget": MissionBudget(
                max_depth=3,
                remaining_depth=3,
                deadline=1000000.0,
                max_recruitments=5,
                remaining_recruitments=5,
            ),
            "context": MissionContext(
                user_input="Check weather and set lights",
                conversation_history=[],
                recruitment_results=[],
                recruitment_chain=["ChatAgent"],
            ),
            "available_capabilities": {
                "WeatherAgent": ["get_weather", "get_forecast"],
                "LightingAgent": ["set_color", "set_brightness"],
            },
            "metadata": {"source": "test"},
        }
        defaults.update(overrides)
        return MissionBrief(**defaults)

    def test_creation(self):
        brief = self._make_brief()
        assert brief.user_input == "Check weather and set lights"
        assert brief.complexity == MissionComplexity.COMPLEX
        assert brief.lead_agent == "ChatAgent"

    def test_to_dict(self):
        brief = self._make_brief()
        d = brief.to_dict()
        assert d["user_input"] == "Check weather and set lights"
        assert d["complexity"] == "complex"
        assert d["lead_agent"] == "ChatAgent"
        assert d["lead_capability"] == "chat"
        assert d["budget"]["max_depth"] == 3
        assert d["context"]["recruitment_chain"] == ["ChatAgent"]
        assert "WeatherAgent" in d["available_capabilities"]

    def test_from_dict(self):
        brief = self._make_brief()
        d = brief.to_dict()
        restored = MissionBrief.from_dict(d)
        assert restored.user_input == brief.user_input
        assert restored.complexity == brief.complexity
        assert restored.lead_agent == brief.lead_agent
        assert restored.lead_capability == brief.lead_capability
        assert restored.budget.max_depth == brief.budget.max_depth
        assert restored.context.recruitment_chain == brief.context.recruitment_chain

    def test_round_trip_serialization(self):
        """to_dict() -> from_dict() should preserve all fields."""
        brief = self._make_brief()
        d = brief.to_dict()
        restored = MissionBrief.from_dict(d)
        assert restored.to_dict() == d

    def test_from_dict_with_defaults(self):
        """from_dict with minimal data should use sensible defaults."""
        brief = MissionBrief.from_dict({})
        assert brief.user_input == ""
        assert brief.complexity == MissionComplexity.SIMPLE
        assert brief.lead_agent == ""
        assert brief.budget.max_depth == 3

    def test_from_dict_with_recruitment_results(self):
        ctx = MissionContext()
        ctx.add_result("WeatherAgent", "get_weather", {"temp": 72})
        brief = self._make_brief(context=ctx)
        d = brief.to_dict()
        restored = MissionBrief.from_dict(d)
        assert len(restored.context.recruitment_results) == 1
        assert restored.context.recruitment_results[0]["agent"] == "WeatherAgent"


class TestErrorClasses:
    """Tests for mission-related error classes."""

    def test_budget_exhausted_error(self):
        err = BudgetExhaustedError("No budget remaining")
        assert str(err) == "No budget remaining"
        assert err.error_type == "BudgetExhaustedError"

    def test_circular_recruitment_error(self):
        err = CircularRecruitmentError("Cycle detected: A -> B -> A")
        assert str(err) == "Cycle detected: A -> B -> A"
        assert err.error_type == "CircularRecruitmentError"

    def test_budget_exhausted_error_with_details(self):
        err = BudgetExhaustedError(
            "Budget exhausted",
            details={"remaining_depth": 0, "remaining_recruitments": 0},
        )
        response = err.to_response()
        assert response.error_type == "BudgetExhaustedError"
        assert response.details["remaining_depth"] == 0

    def test_circular_recruitment_error_with_details(self):
        err = CircularRecruitmentError(
            "Circular recruitment",
            details={"chain": ["ChatAgent", "WeatherAgent", "ChatAgent"]},
        )
        response = err.to_response()
        assert response.error_type == "CircularRecruitmentError"
        assert "ChatAgent" in response.details["chain"]
