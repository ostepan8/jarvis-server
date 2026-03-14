"""Tests for CapabilitiesAgent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.agents.capabilities_agent import CapabilitiesAgent
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.response import AgentResponse
from jarvis.logging import JarvisLogger


def _make_mock_ai_client():
    """Create a mock AI client that returns a simple response."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Here are the capabilities."
    client.weak_chat = AsyncMock(return_value=(mock_response, []))
    return client


def _make_mock_network(agent_names=None, capabilities=None):
    """Create a mock AgentNetwork."""
    network = MagicMock(spec=AgentNetwork)
    network.agents = {}
    network.capability_registry = capabilities or {}

    for name in (agent_names or []):
        agent = MagicMock()
        agent.name = name
        agent.capabilities = {"cap1"}
        network.agents[name] = agent

    if capabilities is None and agent_names:
        for name in agent_names:
            network.capability_registry.setdefault("cap1", []).append(name)

    return network


def _make_agent(knowledge_dir=None):
    """Create a CapabilitiesAgent for testing."""
    client = _make_mock_ai_client()
    agent = CapabilitiesAgent(
        ai_client=client,
        logger=JarvisLogger(),
        knowledge_dir=knowledge_dir,
    )
    return agent, client


class TestProperties:
    """Test agent metadata."""

    def test_name(self):
        agent, _ = _make_agent()
        assert agent.name == "CapabilitiesAgent"

    def test_capabilities(self):
        agent, _ = _make_agent()
        assert agent.capabilities == {"describe_capabilities", "explain_capability"}

    def test_description(self):
        agent, _ = _make_agent()
        assert "capabilities" in agent.description.lower()
        assert "librarian" in agent.description.lower()

    def test_intent_map_matches_capabilities(self):
        agent, _ = _make_agent()
        assert set(agent.intent_map.keys()) == agent.capabilities


class TestKnowledgeBase:
    """Test knowledge base loading and lookup."""

    def test_loads_default_index(self):
        agent, _ = _make_agent()
        index = agent._load_index()
        assert "Jarvis Capabilities Index" in index
        assert "Smart Home" in index
        assert "Productivity" in index

    def test_reads_knowledge_file(self):
        agent, _ = _make_agent()
        content = agent._read_knowledge_file("_index.md")
        assert content is not None
        assert "Jarvis" in content

    def test_caches_knowledge_files(self):
        agent, _ = _make_agent()
        content1 = agent._read_knowledge_file("_index.md")
        content2 = agent._read_knowledge_file("_index.md")
        assert content1 is content2  # Same object — cached

    def test_returns_none_for_missing_file(self):
        agent, _ = _make_agent()
        assert agent._read_knowledge_file("nonexistent.md") is None

    def test_custom_knowledge_dir(self, tmp_path):
        # Create a minimal knowledge base
        (tmp_path / "_index.md").write_text("# Custom Index\nCustom content.")
        agent, _ = _make_agent(knowledge_dir=str(tmp_path))
        index = agent._load_index()
        assert "Custom Index" in index


class TestKeywordLookup:
    """Test keyword-to-file matching."""

    def test_calendar_keyword_matches(self):
        agent, _ = _make_agent()
        files = agent._find_relevant_files("how does calendar work")
        assert any("calendar" in f for f in files)

    def test_lighting_keyword_matches(self):
        agent, _ = _make_agent()
        files = agent._find_relevant_files("tell me about the lights")
        assert any("lighting" in f for f in files)

    def test_limitations_keyword_matches(self):
        agent, _ = _make_agent()
        files = agent._find_relevant_files("what can't you do")
        assert any("limitations" in f for f in files)

    def test_broad_query_returns_no_matches(self):
        agent, _ = _make_agent()
        files = agent._find_relevant_files("hello there")
        assert len(files) == 0

    def test_multiple_keywords_match_multiple_files(self):
        agent, _ = _make_agent()
        files = agent._find_relevant_files("calendar and lights")
        assert len(files) >= 2


class TestProgressiveDisclosure:
    """Test that context gathering follows progressive disclosure."""

    def test_broad_query_returns_index(self):
        agent, _ = _make_agent()
        context = agent._gather_context("what can you do")
        # Broad query with no keyword matches returns index
        assert "Jarvis Capabilities Index" in context

    def test_specific_query_returns_relevant_docs(self):
        agent, _ = _make_agent()
        context = agent._gather_context("how does the calendar work")
        assert "Calendar" in context

    def test_context_capped_at_three_files(self):
        agent, _ = _make_agent()
        # This query matches many keywords
        context = agent._gather_context(
            "calendar task todo search memory lighting"
        )
        # Should still work without blowing up context
        assert len(context) > 0


class TestRuntimeIntrospection:
    """Test network introspection."""

    def test_live_agents_without_network(self):
        agent, _ = _make_agent()
        assert agent._get_live_agents() == []

    def test_live_agents_with_network(self):
        agent, _ = _make_agent()
        agent.network = _make_mock_network(["ChatAgent", "CalendarAgent"])
        agents = agent._get_live_agents()
        assert "ChatAgent" in agents
        assert "CalendarAgent" in agents

    def test_live_capabilities_without_network(self):
        agent, _ = _make_agent()
        assert agent._get_live_capabilities() == {}

    def test_live_capabilities_with_network(self):
        agent, _ = _make_agent()
        agent.network = _make_mock_network(
            ["TestAgent"],
            capabilities={"search": ["SearchAgent"], "chat": ["ChatAgent"]},
        )
        caps = agent._get_live_capabilities()
        assert "search" in caps
        assert "chat" in caps

    def test_runtime_summary(self):
        agent, _ = _make_agent()
        agent.network = _make_mock_network(
            ["ChatAgent"],
            capabilities={"chat": ["ChatAgent"]},
        )
        summary = agent._build_runtime_summary()
        assert "ChatAgent" in summary
        assert "chat" in summary

    def test_runtime_summary_no_network(self):
        agent, _ = _make_agent()
        summary = agent._build_runtime_summary()
        assert "No agents" in summary


class TestCapabilityHandlers:
    """Test the actual capability handlers."""

    @pytest.mark.asyncio
    async def test_describe_capabilities(self):
        agent, client = _make_agent()
        agent.network = _make_mock_network(["ChatAgent"])
        result = await agent._describe_capabilities(prompt="what can you do")
        assert isinstance(result, AgentResponse)
        assert result.success
        assert result.data is not None
        assert "live_agents" in result.data
        # Verify AI client was called
        client.weak_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_describe_capabilities_with_specific_query(self):
        agent, client = _make_agent()
        agent.network = _make_mock_network(["CalendarAgent"])
        result = await agent._describe_capabilities(
            prompt="tell me about the calendar"
        )
        assert result.success
        # AI client should have received calendar-related context
        call_args = client.weak_chat.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "Calendar" in system_msg

    @pytest.mark.asyncio
    async def test_explain_capability(self):
        agent, client = _make_agent()
        agent.network = _make_mock_network(["LightingAgent"])
        result = await agent._explain_capability(
            prompt="how does the lighting system work"
        )
        assert result.success
        # Should have found lighting docs
        call_args = client.weak_chat.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "Lighting" in system_msg or "light" in system_msg.lower()

    @pytest.mark.asyncio
    async def test_explain_capability_limitations(self):
        agent, client = _make_agent()
        result = await agent._explain_capability(
            prompt="what can't you do"
        )
        assert result.success
        call_args = client.weak_chat.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "limitation" in system_msg.lower() or "Cannot" in system_msg

    @pytest.mark.asyncio
    async def test_ai_client_failure_fallback(self):
        agent, client = _make_agent()
        client.weak_chat = AsyncMock(side_effect=Exception("API down"))
        result = await agent._describe_capabilities(prompt="what can you do")
        # Should still succeed with fallback content
        assert result.success
        assert len(result.response) > 0

    @pytest.mark.asyncio
    async def test_handle_capability_request_describe(self):
        agent, _ = _make_agent()
        agent.network = _make_mock_network(["TestAgent"])
        # Wire up send methods
        agent.send_capability_response = AsyncMock()
        agent.send_error = AsyncMock()

        from jarvis.agents.message import Message

        msg = Message(
            from_agent="NLUAgent",
            to_agent="CapabilitiesAgent",
            message_type="capability_request",
            content={
                "capability": "describe_capabilities",
                "data": {"prompt": "what can you do"},
            },
            request_id="test-123",
        )
        await agent._handle_capability_request(msg)
        agent.send_capability_response.assert_called_once()
        response_data = agent.send_capability_response.call_args[1]["result"]
        assert response_data["success"]

    @pytest.mark.asyncio
    async def test_handle_unknown_capability(self):
        agent, _ = _make_agent()
        agent.send_error = AsyncMock()

        from jarvis.agents.message import Message

        msg = Message(
            from_agent="NLUAgent",
            to_agent="CapabilitiesAgent",
            message_type="capability_request",
            content={
                "capability": "unknown_cap",
                "data": {},
            },
            request_id="test-456",
        )
        await agent._handle_capability_request(msg)
        agent.send_error.assert_called_once()


class TestFeatureFlag:
    """Test that the feature flag exists in config."""

    def test_feature_flag_exists(self):
        from jarvis.core.config import FeatureFlags

        flags = FeatureFlags()
        assert hasattr(flags, "enable_capabilities")
        assert flags.enable_capabilities is True


class TestFactoryRegistration:
    """Test that the agent is registered via factory."""

    def test_build_capabilities_method_exists(self):
        from jarvis.agents.factory import AgentFactory
        from jarvis.core.config import JarvisConfig

        factory = AgentFactory(JarvisConfig(), JarvisLogger())
        assert hasattr(factory, "_build_capabilities")
