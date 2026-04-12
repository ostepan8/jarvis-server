"""Startup smoke tests — verify that JarvisSystem and JarvisBuilder can
initialize without crashing.  These catch integration-level issues like
missing methods, broken imports, or misconfigured wiring that unit tests
on individual modules would miss.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from jarvis.core.config import JarvisConfig, FeatureFlags
from jarvis.core.system import JarvisSystem
from jarvis.core.builder import JarvisBuilder


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_flags():
    """Feature flags with all optional services disabled."""
    return FeatureFlags(

        enable_lights=False,
        enable_canvas=False,
        enable_night_mode=False,
        enable_roku=False,
        enable_coordinator=False,
    )


@pytest.fixture
def minimal_config(minimal_flags):
    """Config that avoids network/API calls during startup."""
    return JarvisConfig(
        ai_provider="openai",
        api_key="sk-test-fake-key",
        flags=minimal_flags,
        google_search_api_key=None,
        google_search_engine_id=None,
    )


@pytest.fixture
def mock_mongo():
    """Prevent real MongoDB connections."""
    with patch("jarvis.core.system.ProtocolUsageLogger") as usage_cls, \
         patch("jarvis.core.system.InteractionLogger") as interaction_cls:
        usage_inst = MagicMock()
        usage_inst.connect = AsyncMock()
        usage_inst.close = AsyncMock()
        usage_cls.return_value = usage_inst

        interaction_inst = MagicMock()
        interaction_inst.connect = AsyncMock()
        interaction_inst.close = AsyncMock()
        interaction_cls.return_value = interaction_inst

        yield


@pytest.fixture
def mock_vector_memory():
    """Prevent VectorMemoryService from requiring OPENAI_API_KEY."""
    with patch("jarvis.agents.factory.VectorMemoryService") as cls:
        cls.return_value = MagicMock()
        yield


# ---------------------------------------------------------------------------
# JarvisSystem.initialize smoke tests
# ---------------------------------------------------------------------------

class TestSystemInitSmoke:
    """Verify JarvisSystem.initialize runs without errors."""

    @pytest.mark.asyncio
    async def test_initialize_completes(
        self, minimal_config, mock_mongo, mock_vector_memory
    ):
        """Full initialize path should succeed with minimal config."""
        system = JarvisSystem(minimal_config)
        try:
            await system.initialize(load_protocol_directory=False)

            # Basic sanity: agents are registered
            assert len(system.network.agents) > 0
            # Orchestrator is wired
            assert system._orchestrator is not None
            # Protocol runtime is set
            assert system.protocol_runtime is not None
        finally:
            await system.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_registers_core_agents(
        self, minimal_config, mock_mongo, mock_vector_memory
    ):
        """Core agents (NLU, Chat, Memory) should always be registered."""
        system = JarvisSystem(minimal_config)
        try:
            await system.initialize(load_protocol_directory=False)
            agent_names = set(system.network.agents.keys())
            for expected in ("NLUAgent", "ChatAgent", "MemoryAgent"):
                assert expected in agent_names, f"{expected} not registered"
        finally:
            await system.shutdown()


# ---------------------------------------------------------------------------
# JarvisBuilder.build smoke tests
# ---------------------------------------------------------------------------

class TestBuilderBuildSmoke:
    """Verify JarvisBuilder.build() produces a working JarvisSystem."""

    @pytest.mark.asyncio
    async def test_builder_build_completes(
        self, minimal_config, mock_mongo, mock_vector_memory
    ):
        """builder.build() should return a fully-initialized JarvisSystem."""
        builder = JarvisBuilder(minimal_config)
        builder.lights(False).roku(False).night_agents(False)
        jarvis = await builder.build()
        try:
            assert jarvis is not None
            assert isinstance(jarvis, JarvisSystem)
            assert jarvis._orchestrator is not None
            assert jarvis.protocol_runtime is not None
            assert len(jarvis.network.agents) > 0
        finally:
            await jarvis.shutdown()

    @pytest.mark.asyncio
    async def test_builder_with_all_disabled(
        self, minimal_config, mock_mongo, mock_vector_memory
    ):
        """Builder with everything disabled should still produce a valid system."""
        builder = JarvisBuilder(minimal_config)
        builder.memory(False).nlu(False).calendar(False).chat(False)
        builder.search(False).protocols(False)
        builder.lights(False).roku(False).night_agents(False)
        jarvis = await builder.build()
        try:
            assert isinstance(jarvis, JarvisSystem)
            assert jarvis._orchestrator is not None
        finally:
            await jarvis.shutdown()

    @pytest.mark.asyncio
    async def test_builder_protocol_runtime_initialized(
        self, minimal_config, mock_mongo, mock_vector_memory
    ):
        """_setup_protocol_system must be called and set protocol_runtime."""
        builder = JarvisBuilder(minimal_config)
        builder.lights(False).roku(False).night_agents(False)
        jarvis = await builder.build()
        try:
            assert jarvis.protocol_runtime is not None
            assert hasattr(jarvis.protocol_runtime, "registry")
        finally:
            await jarvis.shutdown()


# ---------------------------------------------------------------------------
# Regression: _setup_protocol_system must exist on JarvisSystem
# ---------------------------------------------------------------------------

class TestSetupProtocolSystemExists:
    """Regression guard: builder.py calls _setup_protocol_system on the
    JarvisSystem instance, so the method must always be present."""

    def test_method_exists(self):
        assert hasattr(JarvisSystem, "_setup_protocol_system")
        assert callable(getattr(JarvisSystem, "_setup_protocol_system"))

    def test_method_assigns_protocol_runtime(self, minimal_config, mock_mongo):
        system = JarvisSystem(minimal_config)
        assert system.protocol_runtime is None
        system._setup_protocol_system(load_protocol_directory=False)
        assert system.protocol_runtime is not None
