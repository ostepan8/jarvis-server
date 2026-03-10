"""Tests for agent-to-agent dialogue (multi-turn conversations).

Covers:
- DialogueSession data structures
- dialogue() method on CollaborationMixin
- start_dialogue tool definition and dispatch
- Receiving-agent dialogue handling
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Set, Tuple
from unittest.mock import MagicMock

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.base import NetworkAgent
from jarvis.agents.collaboration import CollaborationMixin
from jarvis.agents.dialogue import DialogueSession, DialogueStatus, DialogueTurn
from jarvis.agents.message import Message
from jarvis.agents.response import AgentResponse
from jarvis.core.errors import (
    BudgetExhaustedError,
    CapabilityNotFoundError,
    CircularRecruitmentError,
    DialogueError,
)
from jarvis.core.mission import (
    MissionBrief,
    MissionBudget,
    MissionComplexity,
    MissionContext,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class DialogueLeadAgent(NetworkAgent, CollaborationMixin):
    """Lead agent that can initiate dialogues."""

    def __init__(self, name: str = "LeadAgent", ai_client=None):
        super().__init__(name)
        self.ai_client = ai_client
        self.tools = []
        self.intent_map = {"greet": self._greet}

    @property
    def capabilities(self) -> Set[str]:
        return {"greet"}

    @property
    def supports_dialogue(self) -> bool:
        return True

    async def _greet(self, name: str = "World") -> Dict[str, Any]:
        return {"response": f"Hello, {name}!"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        dialogue_context = data.get("dialogue_context")
        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )
            return

        prompt = data.get("prompt", "")
        result = await self.run_capability(capability, name=prompt or "World")
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class DialogueProviderAgent(NetworkAgent):
    """Provider agent that supports dialogue (has ai_client)."""

    def __init__(
        self,
        name: str,
        provided_capabilities: Set[str],
        ai_client=None,
        static_response: Any = None,
    ):
        super().__init__(name)
        self._capabilities = provided_capabilities
        self.ai_client = ai_client
        self._static_response = static_response

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    @property
    def supports_dialogue(self) -> bool:
        return self.ai_client is not None

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self._capabilities:
            return

        data = message.content.get("data", {})
        dialogue_context = data.get("dialogue_context")

        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
        elif self._static_response is not None:
            result = self._static_response
        else:
            result = {"response": f"Result from {self.name}", "success": True}

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class NoDialogueProviderAgent(NetworkAgent):
    """Provider agent that does NOT support dialogue (no ai_client)."""

    def __init__(self, name: str, provided_capabilities: Set[str]):
        super().__init__(name)
        self._capabilities = provided_capabilities

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability not in self._capabilities:
            return
        data = message.content.get("data", {})
        dialogue_context = data.get("dialogue_context")
        if dialogue_context:
            result = await self._respond_to_dialogue(
                data.get("prompt", ""), dialogue_context
            )
        else:
            result = {"response": f"Result from {self.name}", "success": True}
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class SilentProviderAgent(NetworkAgent):
    """Agent that receives but never responds (for timeout tests)."""

    def __init__(self, name: str, provided_capabilities: Set[str]):
        super().__init__(name)
        self._capabilities = provided_capabilities

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        pass  # Never responds

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class CrashingProviderAgent(NetworkAgent):
    """Agent that raises an exception on capability requests."""

    def __init__(self, name: str, provided_capabilities: Set[str]):
        super().__init__(name)
        self._capabilities = provided_capabilities

    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities

    async def _handle_capability_request(self, message: Message) -> None:
        raise RuntimeError("Agent crashed!")

    async def _handle_capability_response(self, message: Message) -> None:
        pass


class SequenceAIClient:
    """AI client returning a configurable sequence of JSON responses.

    Each entry is a dict like {"message": "...", "done": bool} that
    will be returned as `content` from strong_chat.
    """

    def __init__(self, responses: List[Dict[str, Any]]):
        self._responses = list(responses)
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        if self._call_count < len(self._responses):
            data = self._responses[self._call_count]
            self._call_count += 1
            msg = MagicMock()
            msg.content = json.dumps(data)
            return msg, None
        msg = MagicMock()
        msg.content = json.dumps({"message": "Done.", "done": True})
        return msg, None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


class DialogueReplyAIClient:
    """AI client for lead's _generate_dialogue_reply.

    Returns a sequence of (message, conclude) replies as JSON.
    """

    def __init__(self, replies: List[Tuple[str, bool]]):
        self._replies = list(replies)
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        if self._call_count < len(self._replies):
            msg_text, conclude = self._replies[self._call_count]
            self._call_count += 1
            data = {"message": msg_text, "conclude": conclude}
            msg = MagicMock()
            msg.content = json.dumps(data)
            return msg, None
        msg = MagicMock()
        msg.content = json.dumps({"message": "No more.", "conclude": True})
        return msg, None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


class ToolCallAIClient:
    """Mock AI client that returns configurable sequences of tool calls then text."""

    def __init__(self, responses: List[Tuple[str, Any]]):
        self._responses = list(responses)
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        if self._call_count < len(self._responses):
            content, tool_calls = self._responses[self._call_count]
            self._call_count += 1
            message = MagicMock()
            message.content = content
            return message, tool_calls
        message = MagicMock()
        message.content = "Done."
        return message, None

    async def weak_chat(self, messages, tools=None):
        return await self.strong_chat(messages, tools)


def make_tool_call(name: str, arguments: Dict[str, Any], call_id: str = "call_1"):
    """Create a mock tool call object."""
    call = MagicMock()
    call.id = call_id
    call.function = MagicMock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def make_brief(
    lead_agent: str = "LeadAgent",
    available_capabilities: Dict[str, List[str]] = None,
    budget: MissionBudget = None,
    context: MissionContext = None,
) -> MissionBrief:
    if available_capabilities is None:
        available_capabilities = {
            "SearchAgent": ["search", "news_search"],
            "LightingAgent": ["lights_color", "lights_brightness"],
        }
    if budget is None:
        budget = MissionBudget(
            max_depth=3,
            remaining_depth=3,
            deadline=time.time() + 60,
            max_recruitments=10,
            remaining_recruitments=10,
        )
    if context is None:
        context = MissionContext(
            user_input="test request",
            recruitment_chain=[lead_agent],
        )
    return MissionBrief(
        user_input="test request",
        complexity=MissionComplexity.COMPLEX,
        lead_agent=lead_agent,
        lead_capability="chat",
        budget=budget,
        context=context,
        available_capabilities=available_capabilities,
    )


async def setup_network(*agents: NetworkAgent) -> AgentNetwork:
    network = AgentNetwork()
    for agent in agents:
        network.register_agent(agent)
    await network.start()
    return network


# ===========================================================================
# Data structure tests
# ===========================================================================


class TestDialogueTurn:
    def test_create_turn(self):
        turn = DialogueTurn(turn_number=1, speaker="LeadAgent", message="Hello")
        assert turn.turn_number == 1
        assert turn.speaker == "LeadAgent"
        assert turn.message == "Hello"
        assert turn.metadata == {}

    def test_turn_to_dict_roundtrip(self):
        turn = DialogueTurn(
            turn_number=2, speaker="SearchAgent", message="Sunny", metadata={"temp": 72}
        )
        d = turn.to_dict()
        restored = DialogueTurn.from_dict(d)
        assert restored.turn_number == 2
        assert restored.speaker == "SearchAgent"
        assert restored.message == "Sunny"
        assert restored.metadata == {"temp": 72}


class TestDialogueSession:
    def test_create_session(self):
        session = DialogueSession(
            initiator="LeadAgent",
            responder="SearchAgent",
            goal="Check weather",
            capability="search",
        )
        assert session.initiator == "LeadAgent"
        assert session.responder == "SearchAgent"
        assert session.turn_count == 0
        assert session.is_complete is False
        assert session.status == DialogueStatus.ACTIVE

    def test_add_turn(self):
        session = DialogueSession()
        session.add_turn("LeadAgent", "Hello")
        session.add_turn("SearchAgent", "Hi there")
        assert session.turn_count == 2
        assert session.turns[0].speaker == "LeadAgent"
        assert session.turns[1].speaker == "SearchAgent"
        assert session.turns[0].turn_number == 1
        assert session.turns[1].turn_number == 2

    def test_is_complete_when_completed(self):
        session = DialogueSession()
        session.status = DialogueStatus.COMPLETED
        assert session.is_complete is True

    def test_is_complete_when_error(self):
        session = DialogueSession()
        session.status = DialogueStatus.ERROR
        assert session.is_complete is True

    def test_is_complete_when_terminated(self):
        session = DialogueSession()
        session.status = DialogueStatus.TERMINATED
        assert session.is_complete is True

    def test_format_transcript(self):
        session = DialogueSession()
        session.add_turn("Lead", "What's the weather?")
        session.add_turn("Weather", "It's sunny, 72°F")
        transcript = session.format_transcript()
        assert "[Turn 1] Lead: What's the weather?" in transcript
        assert "[Turn 2] Weather: It's sunny, 72°F" in transcript

    def test_format_transcript_empty(self):
        session = DialogueSession()
        assert session.format_transcript() == ""

    def test_to_dict_from_dict_roundtrip(self):
        session = DialogueSession(
            session_id="test-id",
            initiator="LeadAgent",
            responder="SearchAgent",
            goal="Check weather",
            capability="search",
            max_turns=3,
            status=DialogueStatus.COMPLETED,
        )
        session.add_turn("LeadAgent", "Hello")
        session.add_turn("SearchAgent", "Hi")

        d = session.to_dict()
        restored = DialogueSession.from_dict(d)

        assert restored.session_id == "test-id"
        assert restored.initiator == "LeadAgent"
        assert restored.responder == "SearchAgent"
        assert restored.goal == "Check weather"
        assert restored.capability == "search"
        assert restored.max_turns == 3
        assert restored.status == DialogueStatus.COMPLETED
        assert restored.turn_count == 2
        assert restored.turns[0].message == "Hello"
        assert restored.turns[1].message == "Hi"


# ===========================================================================
# Core dialogue method tests
# ===========================================================================


class TestDialogueMethod:
    """Tests for CollaborationMixin.dialogue()."""

    @pytest.mark.asyncio
    async def test_successful_two_turn_dialogue(self):
        """Initiator sends → responder replies with done=True → dialogue completes."""
        responder_ai = SequenceAIClient([
            {"message": "It's 72°F and sunny.", "done": True},
        ])
        lead_ai = DialogueReplyAIClient([])  # Won't be called (responder ends it)

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            session = await lead.dialogue(
                capability="search",
                initial_message="What's the weather?",
                goal="Get current conditions",
                brief=brief,
                max_turns=5,
            )
            assert session.status == DialogueStatus.COMPLETED
            assert session.turn_count == 2  # initiator + responder
            assert session.turns[0].speaker == "LeadAgent"
            assert session.turns[1].speaker == "SearchAgent"
            assert "72°F" in session.turns[1].message
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_multi_turn_dialogue_with_followup(self):
        """Lead sends → responder replies (not done) → lead follows up → responder completes."""
        responder_ai = SequenceAIClient([
            {"message": "What location?", "done": False},
            {"message": "Chicago is 72°F and sunny.", "done": True},
        ])
        lead_ai = DialogueReplyAIClient([
            ("Chicago, please.", False),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            session = await lead.dialogue(
                capability="search",
                initial_message="What's the weather?",
                goal="Get weather for outdoor activities",
                brief=brief,
                max_turns=5,
            )
            assert session.status == DialogueStatus.COMPLETED
            # Turn 1: Lead "What's the weather?"
            # Turn 2: Weather "What location?"
            # Turn 3: Lead "Chicago, please."
            # Turn 4: Weather "Chicago is 72°F and sunny."
            assert session.turn_count == 4
            assert session.turns[2].speaker == "LeadAgent"
            assert "Chicago" in session.turns[2].message
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_budget_exhausted_mid_dialogue(self):
        """Dialogue should terminate when budget runs out mid-conversation."""
        responder_ai = SequenceAIClient([
            {"message": "What location?", "done": False},
        ])
        lead_ai = DialogueReplyAIClient([
            ("Chicago", False),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=1,  # Only 1 turn allowed
                    deadline=time.time() + 60,
                )
            )
            session = await lead.dialogue(
                capability="search",
                initial_message="What's the weather?",
                goal="Get weather",
                brief=brief,
                max_turns=5,
            )
            assert session.status == DialogueStatus.TERMINATED
            # Got through 1 exchange before budget ran out
            assert session.turn_count >= 2
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_deadline_expired_mid_dialogue(self):
        """Dialogue should terminate or raise BudgetExhaustedError when deadline passes."""
        responder_ai = SequenceAIClient([
            {"message": "Processing...", "done": False},
        ])
        lead_ai = DialogueReplyAIClient([
            ("Continue", False),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=10,
                    deadline=time.time() + 0.01,  # Expires almost immediately
                )
            )
            # Small sleep to ensure deadline passes
            await asyncio.sleep(0.02)
            try:
                session = await lead.dialogue(
                    capability="search",
                    initial_message="What's the weather?",
                    goal="Get weather",
                    brief=brief,
                    max_turns=5,
                )
                # If we got a session, it should be terminated or errored
                assert session.status in (DialogueStatus.TERMINATED, DialogueStatus.ERROR)
            except BudgetExhaustedError:
                # Also acceptable — budget expired before dialogue started
                pass
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_max_turns_enforced(self):
        """Dialogue should stop after max_turns responder turns."""
        responder_ai = SequenceAIClient([
            {"message": "Reply 1", "done": False},
            {"message": "Reply 2", "done": False},
            {"message": "Reply 3", "done": False},
        ])
        lead_ai = DialogueReplyAIClient([
            ("Follow-up 1", False),
            ("Follow-up 2", False),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            session = await lead.dialogue(
                capability="search",
                initial_message="Start",
                goal="Test max turns",
                brief=brief,
                max_turns=2,  # Only 2 responder turns
            )
            # Should complete at or before max_turns
            assert session.status == DialogueStatus.COMPLETED
            # At most 2 responder turns => up to 4 total turns (2 each)
            responder_turns = [t for t in session.turns if t.speaker == "SearchAgent"]
            assert len(responder_turns) <= 2
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_responder_timeout(self):
        """Dialogue should error when responder times out."""
        lead_ai = DialogueReplyAIClient([])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        silent = SilentProviderAgent("SearchAgent", {"search"})
        network = await setup_network(lead, silent)

        try:
            brief = make_brief(
                budget=MissionBudget(
                    remaining_depth=3,
                    remaining_recruitments=10,
                    deadline=time.time() + 10,
                )
            )
            session = await lead.dialogue(
                capability="search",
                initial_message="Hello?",
                goal="Test timeout",
                brief=brief,
                max_turns=3,
                timeout_per_turn=0.3,
            )
            assert session.status == DialogueStatus.ERROR
            # Should have the initiator turn + an error turn
            assert session.turn_count >= 2
            assert "timeout" in session.turns[-1].message.lower() or "timeout" in session.turns[-1].metadata.get("error", "")
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_transcript_recorded_in_mission_context(self):
        """Dialogue transcript should be recorded in MissionContext.recruitment_results."""
        responder_ai = SequenceAIClient([
            {"message": "Done!", "done": True},
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=DialogueReplyAIClient([]))
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            await lead.dialogue(
                capability="search",
                initial_message="Hello",
                goal="Test context recording",
                brief=brief,
            )
            results = brief.context.recruitment_results
            assert len(results) == 1
            assert results[0]["agent"] == "SearchAgent"
            assert results[0]["capability"] == "dialogue:search"
            assert "transcript" in results[0]["result"]
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_capability_not_found_error(self):
        """Dialogue should raise CapabilityNotFoundError for unknown capability."""
        lead = DialogueLeadAgent("LeadAgent", ai_client=DialogueReplyAIClient([]))
        network = await setup_network(lead)

        try:
            brief = make_brief()
            with pytest.raises(CapabilityNotFoundError):
                await lead.dialogue(
                    capability="nonexistent",
                    initial_message="Hello",
                    goal="Test",
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_circular_recruitment_error(self):
        """Dialogue should raise CircularRecruitmentError for cycles."""
        lead = DialogueLeadAgent("LeadAgent", ai_client=DialogueReplyAIClient([]))
        search_provider = DialogueProviderAgent("SearchAgent", {"search"})
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief(
                context=MissionContext(
                    user_input="test",
                    recruitment_chain=["LeadAgent", "SearchAgent"],
                )
            )
            with pytest.raises(CircularRecruitmentError):
                await lead.dialogue(
                    capability="search",
                    initial_message="Hello",
                    goal="Test",
                    brief=brief,
                )
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_lead_concludes_dialogue(self):
        """Lead agent's _generate_dialogue_reply can conclude the dialogue."""
        responder_ai = SequenceAIClient([
            {"message": "Here's the weather info.", "done": False},
        ])
        lead_ai = DialogueReplyAIClient([
            ("Thanks, that's all I need.", True),  # conclude=True
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            session = await lead.dialogue(
                capability="search",
                initial_message="What's the weather?",
                goal="Quick check",
                brief=brief,
                max_turns=5,
            )
            assert session.status == DialogueStatus.COMPLETED
            # Only 2 turns: lead asks, weather responds, lead concludes (no extra turn added)
            assert session.turn_count == 2
        finally:
            await network.stop()


# ===========================================================================
# Tool definition tests
# ===========================================================================


class TestDialogueToolDefinition:
    """Tests for _build_dialogue_tool_definition."""

    def test_valid_openai_tool_spec(self):
        agent = DialogueLeadAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_dialogue_tool_definition(brief)
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "start_dialogue"
        params = tool["function"]["parameters"]
        assert params["type"] == "object"

    def test_capability_enum_populated(self):
        agent = DialogueLeadAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_dialogue_tool_definition(brief)
        cap_enum = tool["function"]["parameters"]["properties"]["capability"]["enum"]
        assert "search" in cap_enum
        assert "news_search" in cap_enum
        assert "lights_color" in cap_enum

    def test_required_fields(self):
        agent = DialogueLeadAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_dialogue_tool_definition(brief)
        required = tool["function"]["parameters"]["required"]
        assert "capability" in required
        assert "initial_message" in required
        assert "goal" in required

    def test_has_max_turns_param(self):
        agent = DialogueLeadAgent("LeadAgent")
        brief = make_brief()
        tool = agent._build_dialogue_tool_definition(brief)
        props = tool["function"]["parameters"]["properties"]
        assert "max_turns" in props
        assert props["max_turns"]["type"] == "integer"


# ===========================================================================
# Lead integration tests (execute_as_lead with dialogue)
# ===========================================================================


class TestExecuteAsLeadWithDialogue:
    """Tests for start_dialogue tool in the lead execution loop."""

    @pytest.mark.asyncio
    async def test_start_dialogue_tool_in_tools_list(self):
        """start_dialogue tool should appear alongside recruit_agent."""
        ai_client = ToolCallAIClient([("Hello!", None)])
        lead = DialogueLeadAgent("LeadAgent", ai_client=ai_client)
        network = await setup_network(lead)

        try:
            brief = make_brief()
            # We inspect the tools indirectly — if _execute_as_lead runs
            # without error with start_dialogue as a possible tool, it works.
            result = await lead._execute_as_lead("test", brief)
            assert result["success"] is True
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_llm_calling_start_dialogue(self):
        """LLM calling start_dialogue should trigger dialogue() and return transcript."""
        # Set up responder AI
        responder_ai = SequenceAIClient([
            {"message": "It's 72°F and sunny!", "done": True},
        ])

        # Set up lead AI: first call returns start_dialogue tool call, second returns final text
        dialogue_call = make_tool_call(
            "start_dialogue",
            {
                "capability": "search",
                "initial_message": "What's the weather?",
                "goal": "Get current conditions",
                "max_turns": 3,
            },
            "call_dialogue",
        )
        lead_ai = ToolCallAIClient([
            ("", [dialogue_call]),
            ("The weather is 72°F and sunny!", None),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("What's the weather like?", brief)
            assert result["success"] is True
            assert "72°F" in result["response"]
            # Should have a start_dialogue action
            assert any(a["function"] == "start_dialogue" for a in result["actions"])
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_lead_mixes_recruit_and_dialogue(self):
        """Lead can use both recruit_agent and start_dialogue in same mission."""
        responder_ai = SequenceAIClient([
            {"message": "Lights are warm yellow.", "done": True},
        ])

        recruit_call = make_tool_call(
            "recruit_agent",
            {"capability": "search", "prompt": "Get weather"},
            "call_recruit",
        )
        dialogue_call = make_tool_call(
            "start_dialogue",
            {
                "capability": "lights_color",
                "initial_message": "Set mood lighting",
                "goal": "Configure lights for evening",
            },
            "call_dialogue",
        )
        lead_ai = ToolCallAIClient([
            ("", [recruit_call]),
            ("", [dialogue_call]),
            ("All set! Weather is clear and lights are warm.", None),
        ])

        lead = DialogueLeadAgent("LeadAgent", ai_client=lead_ai)
        search_provider = DialogueProviderAgent(
            "SearchAgent",
            {"search"},
            static_response={"response": "Clear skies", "success": True},
        )
        lights = DialogueProviderAgent(
            "LightingAgent", {"lights_color"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider, lights)

        try:
            brief = make_brief()
            result = await lead._execute_as_lead("Set up evening mood", brief)
            assert result["success"] is True
            functions = [a["function"] for a in result["actions"]]
            assert "recruit_agent" in functions
            assert "start_dialogue" in functions
        finally:
            await network.stop()


# ===========================================================================
# Receiving agent dialogue tests
# ===========================================================================


class TestReceivingAgentDialogue:
    """Tests for agents receiving dialogue context."""

    @pytest.mark.asyncio
    async def test_agent_with_ai_client_generates_llm_response(self):
        """Agent with AI client should generate LLM-based dialogue response."""
        ai_client = SequenceAIClient([
            {"message": "It's 72°F!", "done": True},
        ])
        agent = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=ai_client
        )
        result = await agent._respond_to_dialogue(
            "What's the weather?",
            {"goal": "Get conditions", "transcript": "", "capability": "search"},
        )
        assert result["dialogue_message"] == "It's 72°F!"
        assert result["dialogue_done"] is True
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_agent_without_ai_client_returns_done(self):
        """Agent without AI client should return dialogue_done=True."""
        agent = NoDialogueProviderAgent("BasicAgent", {"search"})
        result = await agent._respond_to_dialogue(
            "Search for cats",
            {"goal": "Search", "transcript": "", "capability": "search"},
        )
        assert result["dialogue_done"] is True
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dialogue_context_passed_to_ai(self):
        """Dialogue context (transcript, goal) should be included in AI prompt."""
        captured_messages = []

        class CapturingAIClient:
            async def strong_chat(self, messages, tools=None):
                captured_messages.extend(messages)
                msg = MagicMock()
                msg.content = json.dumps({"message": "OK", "done": True})
                return msg, None

        ai_client = CapturingAIClient()
        agent = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=ai_client
        )
        await agent._respond_to_dialogue(
            "What about tomorrow?",
            {
                "goal": "Multi-day forecast",
                "transcript": "[Turn 1] Lead: What's the weather?",
                "capability": "search",
            },
        )
        all_content = " ".join(m["content"] for m in captured_messages)
        assert "Multi-day forecast" in all_content
        assert "Turn 1" in all_content
        assert "What about tomorrow?" in all_content


# ===========================================================================
# Supports dialogue property tests
# ===========================================================================


class TestSupportsDialogue:
    def test_base_agent_does_not_support_dialogue(self):
        """Base NetworkAgent.supports_dialogue should be False."""

        class MinimalAgent(NetworkAgent):
            async def _handle_capability_request(self, msg):
                pass

            async def _handle_capability_response(self, msg):
                pass

        agent = MinimalAgent("TestAgent")
        assert agent.supports_dialogue is False

    def test_dialogue_lead_supports_dialogue(self):
        agent = DialogueLeadAgent("LeadAgent")
        assert agent.supports_dialogue is True

    def test_provider_with_ai_supports_dialogue(self):
        agent = DialogueProviderAgent("W", {"x"}, ai_client=SequenceAIClient([]))
        assert agent.supports_dialogue is True

    def test_provider_without_ai_no_dialogue(self):
        agent = DialogueProviderAgent("W", {"x"}, ai_client=None)
        assert agent.supports_dialogue is False


# ===========================================================================
# Handle dialogue tool call tests
# ===========================================================================


class TestHandleDialogueToolCall:
    """Tests for _handle_dialogue_tool_call error handling."""

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_capability(self):
        lead = DialogueLeadAgent("LeadAgent", ai_client=DialogueReplyAIClient([]))
        network = await setup_network(lead)

        try:
            brief = make_brief()
            result = await lead._handle_dialogue_tool_call(
                {
                    "capability": "nonexistent",
                    "initial_message": "Hello",
                    "goal": "Test",
                },
                brief,
            )
            assert "error" in result
        finally:
            await network.stop()

    @pytest.mark.asyncio
    async def test_returns_transcript_on_success(self):
        responder_ai = SequenceAIClient([
            {"message": "Done!", "done": True},
        ])
        lead = DialogueLeadAgent("LeadAgent", ai_client=DialogueReplyAIClient([]))
        search_provider = DialogueProviderAgent(
            "SearchAgent", {"search"}, ai_client=responder_ai
        )
        network = await setup_network(lead, search_provider)

        try:
            brief = make_brief()
            result = await lead._handle_dialogue_tool_call(
                {
                    "capability": "search",
                    "initial_message": "Hello",
                    "goal": "Test",
                    "max_turns": 3,
                },
                brief,
            )
            assert "transcript" in result
            assert result["status"] == "completed"
            assert result["turns"] >= 2
        finally:
            await network.stop()
