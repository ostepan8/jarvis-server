"""Tests for AgentFactory - agent construction from config."""

import pytest
from unittest.mock import MagicMock, patch

from jarvis.agents.factory import AgentFactory
from jarvis.agents.agent_network import AgentNetwork
from jarvis.core.config import JarvisConfig, FeatureFlags
from jarvis.ai_clients.dummy_client import DummyAIClient
from jarvis.logging import JarvisLogger


# ---------------------------------------------------------------------------
# Shared fixtures: all build_all tests need to mock VectorMemoryService
# because it requires an OpenAI API key at construction time.
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_vector_memory():
    """Mock VectorMemoryService to avoid needing OPENAI_API_KEY."""
    with patch("jarvis.agents.factory.VectorMemoryService") as MockVMS:
        mock_instance = MagicMock()
        MockVMS.return_value = mock_instance
        yield MockVMS


class TestAgentFactoryInit:
    """Test AgentFactory initialization."""

    def test_factory_stores_config_and_logger(self):
        """Test factory stores the config and logger references."""
        config = JarvisConfig()
        logger = JarvisLogger()
        factory = AgentFactory(config, logger)
        assert factory.config is config
        assert factory.logger is logger


class TestAgentFactoryBuildAll:
    """Test AgentFactory.build_all method."""

    @pytest.fixture
    def network(self):
        """Create an AgentNetwork."""
        return AgentNetwork()

    @pytest.fixture
    def ai_client(self):
        """Create a DummyAIClient."""
        return DummyAIClient()

    @pytest.fixture
    def logger(self):
        """Create a JarvisLogger."""
        return JarvisLogger()

    @pytest.fixture
    def minimal_config(self):
        """Create a config with most optional features disabled."""
        config = JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        return config

    def test_build_all_returns_dict(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all returns a dictionary of built components."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert isinstance(refs, dict)

    def test_build_all_registers_memory_agent(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all always registers a memory agent."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "memory_agent" in refs
        assert "MemoryAgent" in network.agents

    def test_build_all_registers_nlu_agent(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all always registers an NLU agent."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "nlu_agent" in refs
        assert "NLUAgent" in network.agents

    def test_build_all_registers_calendar_agent(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all always registers a calendar agent."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "calendar_service" in refs
        assert "CalendarAgent" in network.agents

    def test_build_all_registers_chat_agent(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all always registers a chat agent."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "chat_agent" in refs
        assert "ChatAgent" in network.agents

    def test_build_all_registers_protocol_agent(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all always registers a protocol agent."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "protocol_agent" in refs
        assert "ProtocolAgent" in network.agents

    def test_build_all_skips_lights_when_disabled(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all skips lights agent when flag is disabled."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "lights_agent" not in refs

    def test_build_all_skips_canvas_when_disabled(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all skips canvas agent when flag is disabled."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "canvas_agent" not in refs

    def test_build_all_skips_roku_when_disabled(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all skips roku agent when flag is disabled."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "roku_agent" not in refs

    def test_build_all_skips_search_when_no_api_key(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all skips search agent when no Google API key."""
        factory = AgentFactory(minimal_config, logger)
        refs = factory.build_all(network, ai_client)
        assert "search_agent" not in refs


class TestAgentFactoryBuildRoku:
    """Test roku agent building."""

    @pytest.fixture
    def network(self):
        return AgentNetwork()

    @pytest.fixture
    def ai_client(self):
        return DummyAIClient()

    @pytest.fixture
    def logger(self):
        return JarvisLogger()

    def test_build_roku_skips_when_no_ip(
        self, mock_vector_memory, network, ai_client, logger
    ):
        """Test roku agent is skipped when no IP or persisted devices."""
        from jarvis.services.roku_discovery import RokuDeviceRegistry

        empty_registry = RokuDeviceRegistry()
        with patch.object(RokuDeviceRegistry, "load", return_value=empty_registry):
            config = JarvisConfig(
                flags=FeatureFlags(
                    enable_lights=False,
                    enable_canvas=False,
                    enable_night_mode=False,
                    enable_roku=True,
                ),
                roku_ip_address=None,
                google_search_api_key=None,
                google_search_engine_id=None,
            )
            factory = AgentFactory(config, logger)
            refs = factory.build_all(network, ai_client)
            assert "roku_agent" not in refs


class TestAgentFactoryBuildLights:
    """Test lighting agent building."""

    @pytest.fixture
    def network(self):
        return AgentNetwork()

    @pytest.fixture
    def ai_client(self):
        return DummyAIClient()

    @pytest.fixture
    def logger(self):
        return JarvisLogger()

    def test_build_lights_skips_hue_when_no_bridge_ip(
        self, mock_vector_memory, network, ai_client, logger
    ):
        """Test lights agent skipped for hue when no bridge IP."""
        config = JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=True,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            lighting_backend="phillips_hue",
            hue_bridge_ip=None,
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        factory = AgentFactory(config, logger)
        refs = factory.build_all(network, ai_client)
        assert "lights_agent" not in refs


class TestAgentFactoryBuildSearch:
    """Test search agent building."""

    @pytest.fixture
    def network(self):
        return AgentNetwork()

    @pytest.fixture
    def ai_client(self):
        return DummyAIClient()

    @pytest.fixture
    def logger(self):
        return JarvisLogger()

    def test_build_search_skips_without_api_key(
        self, mock_vector_memory, network, ai_client, logger
    ):
        """Test search agent skipped when no API key."""
        config = JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        factory = AgentFactory(config, logger)
        refs = factory.build_all(network, ai_client)
        assert "search_agent" not in refs

    def test_build_search_skips_without_engine_id(
        self, mock_vector_memory, network, ai_client, logger
    ):
        """Test search agent skipped when no engine ID."""
        config = JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key="some-key",
            google_search_engine_id=None,
        )
        factory = AgentFactory(config, logger)
        refs = factory.build_all(network, ai_client)
        assert "search_agent" not in refs


class TestAgentFactoryNetworkRegistration:
    """Test agents are properly registered in the network."""

    @pytest.fixture
    def minimal_config(self):
        return JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key=None,
            google_search_engine_id=None,
        )

    def test_agents_have_network_set(self, mock_vector_memory, minimal_config):
        """Test all registered agents have their network reference set."""
        network = AgentNetwork()
        logger = JarvisLogger()
        ai_client = DummyAIClient()
        factory = AgentFactory(minimal_config, logger)
        factory.build_all(network, ai_client)

        for agent_name, agent in network.agents.items():
            assert agent.network is network, (
                f"Agent {agent_name} does not have network set"
            )

    def test_capability_registry_populated(self, mock_vector_memory, minimal_config):
        """Test the network capability registry has entries."""
        network = AgentNetwork()
        logger = JarvisLogger()
        ai_client = DummyAIClient()
        factory = AgentFactory(minimal_config, logger)
        factory.build_all(network, ai_client)

        # Should have some capabilities registered
        assert len(network.capability_registry) > 0

    def test_nlu_capability_registered(self, mock_vector_memory, minimal_config):
        """Test intent_matching capability is registered."""
        network = AgentNetwork()
        logger = JarvisLogger()
        ai_client = DummyAIClient()
        factory = AgentFactory(minimal_config, logger)
        factory.build_all(network, ai_client)

        assert "intent_matching" in network.capability_registry


class TestAgentFactoryBuildAllAsync:
    """Test the async build_all_async method that parallelizes heavy I/O."""

    @pytest.fixture
    def network(self):
        return AgentNetwork()

    @pytest.fixture
    def ai_client(self):
        return DummyAIClient()

    @pytest.fixture
    def logger(self):
        return JarvisLogger()

    @pytest.fixture
    def minimal_config(self):
        return JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key=None,
            google_search_engine_id=None,
        )

    @pytest.mark.asyncio
    async def test_build_all_async_returns_dict(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all_async returns a dictionary."""
        factory = AgentFactory(minimal_config, logger)
        refs = await factory.build_all_async(network, ai_client)
        assert isinstance(refs, dict)

    @pytest.mark.asyncio
    async def test_build_all_async_registers_core_agents(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all_async registers the same core agents as sync."""
        factory = AgentFactory(minimal_config, logger)
        refs = await factory.build_all_async(network, ai_client)
        assert "memory_agent" in refs
        assert "nlu_agent" in refs
        assert "calendar_service" in refs
        assert "chat_agent" in refs
        assert "protocol_agent" in refs
        assert "MemoryAgent" in network.agents
        assert "NLUAgent" in network.agents
        assert "CalendarAgent" in network.agents
        assert "ChatAgent" in network.agents

    @pytest.mark.asyncio
    async def test_build_all_async_skips_disabled_agents(
        self, mock_vector_memory, minimal_config, network, ai_client, logger
    ):
        """Test build_all_async skips agents when flags are off."""
        factory = AgentFactory(minimal_config, logger)
        refs = await factory.build_all_async(network, ai_client)
        assert "lights_agent" not in refs
        assert "canvas_agent" not in refs
        assert "roku_agent" not in refs

    @pytest.mark.asyncio
    async def test_build_all_async_handles_chromadb_failure(
        self, network, ai_client, logger
    ):
        """Test build_all_async gracefully handles VectorMemoryService failure."""
        config = JarvisConfig(
            flags=FeatureFlags(
                                enable_lights=False,
                enable_canvas=False,
                enable_night_mode=False,
                enable_roku=False,
            ),
            google_search_api_key=None,
            google_search_engine_id=None,
        )
        with patch(
            "jarvis.agents.factory.VectorMemoryService",
            side_effect=ValueError("No API key"),
        ):
            factory = AgentFactory(config, logger)
            refs = await factory.build_all_async(network, ai_client)
            # Memory agent is always present (backed by markdown vault)
            # but vector_memory should be None when ChromaDB fails
            assert "memory_agent" in refs
            assert refs.get("vector_memory") is None
            assert refs.get("markdown_memory") is not None
            assert "nlu_agent" in refs

    @pytest.mark.asyncio
    async def test_build_all_async_matches_sync_agents(
        self, mock_vector_memory, minimal_config, ai_client, logger
    ):
        """Test async and sync build produce the same set of registered agents."""
        net_sync = AgentNetwork()
        net_async = AgentNetwork()

        factory_sync = AgentFactory(minimal_config, logger)
        factory_async = AgentFactory(minimal_config, logger)

        factory_sync.build_all(net_sync, ai_client)
        await factory_async.build_all_async(net_async, ai_client)

        assert set(net_sync.agents.keys()) == set(net_async.agents.keys())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
