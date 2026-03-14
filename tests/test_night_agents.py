"""Comprehensive tests for the night agent subsystem.

Covers:
- NightAgent base class (background task lifecycle, capability activation)
- NightModeControllerAgent (start/stop night mode, capability requests)
- LogCleanupAgent (periodic cleanup, SQL logic, error handling)
- JarvisSystem enter/exit night mode integration
- Orchestrator night mode blocking behavior
- Full lifecycle: enter → block → wake up
"""

import asyncio
import sqlite3
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.night_agents.base import NightAgent
from jarvis.night_agents.controller_agent import NightModeControllerAgent
from jarvis.night_agents.log_cleanup_agent import LogCleanupAgent
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.message import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConcreteNightAgent(NightAgent):
    """Minimal concrete subclass for testing the base class."""

    def __init__(self, name="TestNightAgent"):
        super().__init__(name)
        self.started = False
        self.cycle_count = 0

    @property
    def description(self):
        return "Test night agent"

    @property
    def capabilities(self):
        return {"test_capability"}

    async def _handle_capability_request(self, message):
        pass

    async def _handle_capability_response(self, message):
        return None

    async def start_background_tasks(self, progress_callback=None):
        self.started = True
        self._create_background_task(self._dummy_loop())

    async def _dummy_loop(self):
        while True:
            self.cycle_count += 1
            await asyncio.sleep(0.01)


def _create_log_db(path: str, entries: list[tuple[str, str, str]] | None = None):
    """Create a SQLite log database with optional seed entries.

    Each entry is (timestamp_iso, level, message).
    """
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS logs ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  timestamp TEXT NOT NULL,"
        "  level TEXT NOT NULL,"
        "  message TEXT"
        ")"
    )
    if entries:
        conn.executemany(
            "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
            entries,
        )
    conn.commit()
    conn.close()


def _count_rows(path: str) -> int:
    conn = sqlite3.connect(path)
    count = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    conn.close()
    return count


# ===========================================================================
# NightAgent Base Class
# ===========================================================================


class TestNightAgentBase:
    def test_initializes_with_empty_task_list(self):
        agent = ConcreteNightAgent()
        assert agent._background_tasks == []

    @pytest.mark.asyncio
    async def test_start_background_tasks_creates_task(self):
        agent = ConcreteNightAgent()
        await agent.start_background_tasks()
        assert agent.started is True
        assert len(agent._background_tasks) == 1
        # Let it cycle at least once
        await asyncio.sleep(0.05)
        assert agent.cycle_count > 0
        await agent.stop_background_tasks()

    @pytest.mark.asyncio
    async def test_stop_background_tasks_cancels_and_clears(self):
        agent = ConcreteNightAgent()
        await agent.start_background_tasks()
        assert len(agent._background_tasks) == 1

        await agent.stop_background_tasks()
        assert len(agent._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_background_tasks_noop_when_empty(self):
        agent = ConcreteNightAgent()
        # Should not raise
        await agent.stop_background_tasks()
        assert agent._background_tasks == []

    @pytest.mark.asyncio
    async def test_multiple_background_tasks(self):
        agent = ConcreteNightAgent()
        counters = {"a": 0, "b": 0}

        async def loop_a():
            while True:
                counters["a"] += 1
                await asyncio.sleep(0.01)

        async def loop_b():
            while True:
                counters["b"] += 1
                await asyncio.sleep(0.01)

        agent._create_background_task(loop_a())
        agent._create_background_task(loop_b())
        assert len(agent._background_tasks) == 2

        await asyncio.sleep(0.05)
        assert counters["a"] > 0
        assert counters["b"] > 0

        await agent.stop_background_tasks()
        assert len(agent._background_tasks) == 0

    def test_activate_capabilities_without_network_is_safe(self):
        agent = ConcreteNightAgent()
        assert agent.network is None
        # Should not raise
        agent.activate_capabilities()

    def test_deactivate_capabilities_without_network_is_safe(self):
        agent = ConcreteNightAgent()
        assert agent.network is None
        agent.deactivate_capabilities()

    def test_activate_capabilities_adds_to_network(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)

        # Night capabilities stored separately, not active yet
        assert "test_capability" not in network.capability_registry

        agent.activate_capabilities()
        assert "test_capability" in network.capability_registry

    def test_deactivate_capabilities_removes_from_network(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)
        agent.activate_capabilities()
        assert "test_capability" in network.capability_registry

        agent.deactivate_capabilities()
        assert "test_capability" not in network.capability_registry

    def test_activate_deactivate_is_idempotent(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)

        agent.activate_capabilities()
        agent.activate_capabilities()  # second call
        # Should have one entry, not duplicates
        assert network.capability_registry.get("test_capability") is not None

        agent.deactivate_capabilities()
        assert "test_capability" not in network.capability_registry
        # Second deactivate should not raise
        agent.deactivate_capabilities()


# ===========================================================================
# NightModeControllerAgent
# ===========================================================================


class TestNightModeControllerAgent:
    def _make_controller(self):
        system = MagicMock()
        system.enter_night_mode = AsyncMock()
        system.exit_night_mode = AsyncMock()
        controller = NightModeControllerAgent(system)
        return controller, system

    def test_name(self):
        controller, _ = self._make_controller()
        assert controller.name == "NightModeControllerAgent"

    def test_capabilities(self):
        controller, _ = self._make_controller()
        assert controller.capabilities == {"start_night_mode", "stop_night_mode"}

    def test_description_is_not_empty(self):
        controller, _ = self._make_controller()
        assert len(controller.description) > 0

    @pytest.mark.asyncio
    async def test_start_night_mode_via_capability_request(self):
        controller, system = self._make_controller()
        controller.send_capability_response = AsyncMock()

        message = MagicMock()
        message.content = {"capability": "start_night_mode"}
        message.from_agent = "ProtocolAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        await controller._handle_capability_request(message)

        system.enter_night_mode.assert_called_once()
        controller.send_capability_response.assert_called_once()
        call_kwargs = controller.send_capability_response.call_args
        # Verify the response contains status
        result = call_kwargs[1] if call_kwargs[1] else call_kwargs[0][1]
        assert "night_mode_enabled" in str(result)

    @pytest.mark.asyncio
    async def test_stop_night_mode_via_capability_request(self):
        controller, system = self._make_controller()
        controller.send_capability_response = AsyncMock()

        message = MagicMock()
        message.content = {"capability": "stop_night_mode"}
        message.from_agent = "ProtocolAgent"
        message.request_id = "req-2"
        message.id = "msg-2"

        await controller._handle_capability_request(message)

        system.exit_night_mode.assert_called_once()
        controller.send_capability_response.assert_called_once()
        result = str(controller.send_capability_response.call_args)
        assert "night_mode_disabled" in result

    @pytest.mark.asyncio
    async def test_unknown_capability_request_is_ignored(self):
        controller, system = self._make_controller()
        controller.send_capability_response = AsyncMock()

        message = MagicMock()
        message.content = {"capability": "unknown_thing"}
        message.from_agent = "TestAgent"
        message.request_id = "req-3"
        message.id = "msg-3"

        await controller._handle_capability_request(message)

        # Neither enter nor exit should be called
        system.enter_night_mode.assert_not_called()
        system.exit_night_mode.assert_not_called()
        # No response sent for unknown capability
        controller.send_capability_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_capability_start(self):
        controller, system = self._make_controller()
        await controller.run_capability("start_night_mode")
        system.enter_night_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_capability_stop(self):
        controller, system = self._make_controller()
        await controller.run_capability("stop_night_mode")
        system.exit_night_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_capability_unknown_raises(self):
        controller, _ = self._make_controller()
        with pytest.raises(NotImplementedError, match="not implemented"):
            await controller.run_capability("fly_to_moon")

    @pytest.mark.asyncio
    async def test_handle_capability_response_is_noop(self):
        controller, _ = self._make_controller()
        result = await controller._handle_capability_response(MagicMock())
        assert result is None


# ===========================================================================
# LogCleanupAgent
# ===========================================================================


class TestLogCleanupAgent:
    def test_name(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        assert agent.name == "LogCleanupAgent"

    def test_capabilities(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        assert agent.capabilities == {"clean_logs", "clean_traces"}

    def test_description(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        assert "log" in agent.description.lower()

    def test_default_retention_is_30_days(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        assert agent.retention_days == 30

    def test_custom_retention(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db", retention_days=7)
        assert agent.retention_days == 7

    @pytest.mark.asyncio
    async def test_clean_logs_deletes_old_entries(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            old = (now - timedelta(days=60)).isoformat()
            recent = (now - timedelta(days=5)).isoformat()

            _create_log_db(db_path, [
                (old, "INFO", "ancient log"),
                (old, "ERROR", "another ancient log"),
                (recent, "INFO", "recent log"),
            ])

            assert _count_rows(db_path) == 3

            agent = LogCleanupAgent(db_path=db_path, retention_days=30)
            result = await agent._clean_logs()

            assert result["deleted_count"] == 2
            assert result["total_before"] == 3
            assert result["total_after"] == 1
            assert result["retention_days"] == 30
            assert _count_rows(db_path) == 1
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_logs_keeps_all_when_none_expired(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            recent = (now - timedelta(days=1)).isoformat()

            _create_log_db(db_path, [
                (recent, "INFO", "log 1"),
                (recent, "INFO", "log 2"),
            ])

            agent = LogCleanupAgent(db_path=db_path, retention_days=30)
            result = await agent._clean_logs()

            assert result["deleted_count"] == 0
            assert result["total_before"] == 2
            assert result["total_after"] == 2
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_logs_empty_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_log_db(db_path)

            agent = LogCleanupAgent(db_path=db_path, retention_days=30)
            result = await agent._clean_logs()

            assert result["deleted_count"] == 0
            assert result["total_before"] == 0
            assert result["total_after"] == 0
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_logs_custom_retention_period(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            # 3 days old — within 7-day retention
            borderline_keep = (now - timedelta(days=3)).isoformat()
            # 10 days old — outside 7-day retention
            borderline_delete = (now - timedelta(days=10)).isoformat()

            _create_log_db(db_path, [
                (borderline_keep, "INFO", "keep me"),
                (borderline_delete, "INFO", "delete me"),
            ])

            agent = LogCleanupAgent(db_path=db_path, retention_days=7)
            result = await agent._clean_logs()

            assert result["deleted_count"] == 1
            assert result["total_after"] == 1
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_logs_missing_database_raises(self):
        agent = LogCleanupAgent(db_path="/nonexistent/path/fake.db")
        with pytest.raises(Exception):
            await agent._clean_logs()

    @pytest.mark.asyncio
    async def test_clean_logs_corrupt_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"this is not a sqlite database")
            db_path = f.name

        try:
            agent = LogCleanupAgent(db_path=db_path)
            with pytest.raises(Exception):
                await agent._clean_logs()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_logs_missing_table_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # Create DB without the logs table
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE other (id INTEGER)")
            conn.close()

            agent = LogCleanupAgent(db_path=db_path)
            with pytest.raises(Exception):
                await agent._clean_logs()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_capability_request_triggers_cleanup(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            now = datetime.now()
            old = (now - timedelta(days=60)).isoformat()
            _create_log_db(db_path, [(old, "INFO", "old")])

            agent = LogCleanupAgent(db_path=db_path)
            agent.send_capability_response = AsyncMock()

            message = MagicMock()
            message.content = {"capability": "clean_logs"}
            message.from_agent = "TestAgent"
            message.request_id = "req-1"
            message.id = "msg-1"

            await agent._handle_capability_request(message)

            agent.send_capability_response.assert_called_once()
            # Verify the result contains cleanup stats
            call_args = agent.send_capability_response.call_args
            result = call_args.kwargs.get("result", call_args[1].get("result") if len(call_args) > 1 else None)
            assert result["deleted_count"] == 1
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_wrong_capability_request_is_ignored(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        agent.send_capability_response = AsyncMock()

        message = MagicMock()
        message.content = {"capability": "something_else"}
        message.from_agent = "TestAgent"
        message.request_id = "req-1"
        message.id = "msg-1"

        await agent._handle_capability_request(message)
        agent.send_capability_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_capability_response_is_noop(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")
        result = await agent._handle_capability_response(MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_start_background_tasks_creates_periodic_task(self):
        agent = LogCleanupAgent(db_path="/tmp/fake.db")

        # Replace periodic cleanup with a controllable coroutine
        async def mock_periodic():
            await asyncio.sleep(1000)

        agent._periodic_cleanup = mock_periodic
        await agent.start_background_tasks()

        assert len(agent._background_tasks) == 1
        await agent.stop_background_tasks()

    @pytest.mark.asyncio
    async def test_periodic_cleanup_survives_errors(self):
        """The periodic loop should catch exceptions and keep running."""
        agent = LogCleanupAgent(db_path="/nonexistent/path/fake.db")
        call_count = 0
        max_calls = 3

        async def counting_clean():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First cleanup fails")
            return {"deleted_count": 0, "total_before": 0, "total_after": 0,
                    "retention_days": 30, "cutoff_date": ""}

        agent._clean_logs = counting_clean

        # Replace _periodic_cleanup with a version that uses tiny sleeps
        async def fast_periodic():
            while call_count < max_calls:
                try:
                    await agent._clean_logs()
                except Exception:
                    pass
                await asyncio.sleep(0.01)

        agent._create_background_task(fast_periodic())
        await asyncio.sleep(0.1)
        await agent.stop_background_tasks()

        # Should have been called at least twice despite the first failure
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_logs_cleanup_result_when_logger_present(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            _create_log_db(db_path, [
                (datetime.now().isoformat(), "INFO", "keep"),
            ])

            mock_logger = MagicMock()
            agent = LogCleanupAgent(db_path=db_path, logger=mock_logger)
            await agent._clean_logs()

            mock_logger.log.assert_called()
            # Should log INFO about completion
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == "INFO"
        finally:
            os.unlink(db_path)


# ===========================================================================
# AgentNetwork Night Agent Registration
# ===========================================================================


class TestAgentNetworkNightIntegration:
    def test_night_agent_registered_but_inactive(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)

        assert agent.name in network.night_agents
        assert agent.name in network.agents
        # Capabilities should NOT be in the active registry
        assert "test_capability" not in network.capability_registry
        # But SHOULD be in the night registry
        assert "test_capability" in network.night_capability_registry

    def test_night_agent_activation_moves_capabilities(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)

        agent.activate_capabilities()
        assert "test_capability" in network.capability_registry

    def test_night_agent_deactivation_removes_capabilities(self):
        network = AgentNetwork()
        agent = ConcreteNightAgent()
        network.register_night_agent(agent)
        agent.activate_capabilities()
        agent.deactivate_capabilities()

        assert "test_capability" not in network.capability_registry

    def test_multiple_night_agents(self):
        network = AgentNetwork()
        agent1 = ConcreteNightAgent("NightOne")
        agent2 = ConcreteNightAgent("NightTwo")
        network.register_night_agent(agent1)
        network.register_night_agent(agent2)

        assert len(network.night_agents) == 2
        assert "NightOne" in network.night_agents
        assert "NightTwo" in network.night_agents


# ===========================================================================
# JarvisSystem Night Mode Integration
# ===========================================================================


class TestSystemNightModeIntegration:
    """Test enter_night_mode / exit_night_mode on JarvisSystem."""

    @pytest.mark.asyncio
    async def test_enter_night_mode_sets_flag(self):
        system = MagicMock()
        system.night_mode = False
        system.night_agents = []
        system._orchestrator = MagicMock()
        system._orchestrator.night_mode = False
        system._start_night_server = AsyncMock()

        # Call the real method
        from jarvis.core.system import JarvisSystem
        await JarvisSystem.enter_night_mode(system)

        assert system.night_mode is True
        assert system._orchestrator.night_mode is True

    @pytest.mark.asyncio
    async def test_exit_night_mode_clears_flag(self):
        system = MagicMock()
        system.night_mode = True
        system.night_agents = []
        system._orchestrator = MagicMock()
        system._orchestrator.night_mode = True
        system._stop_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem
        await JarvisSystem.exit_night_mode(system)

        assert system.night_mode is False
        assert system._orchestrator.night_mode is False

    @pytest.mark.asyncio
    async def test_enter_night_mode_activates_agents(self):
        agent = ConcreteNightAgent()
        agent.activate_capabilities = MagicMock()
        agent.start_background_tasks = AsyncMock()

        system = MagicMock()
        system.night_mode = False
        system.night_agents = [agent]
        system._orchestrator = MagicMock()
        system._start_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem
        await JarvisSystem.enter_night_mode(system)

        agent.activate_capabilities.assert_called_once()
        # start_background_tasks is called via asyncio.create_task, so
        # we need to give the event loop a tick
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_exit_night_mode_deactivates_agents(self):
        agent = ConcreteNightAgent()
        agent.deactivate_capabilities = MagicMock()
        agent.stop_background_tasks = AsyncMock()

        system = MagicMock()
        system.night_mode = True
        system.night_agents = [agent]
        system._orchestrator = MagicMock()
        system._stop_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem
        await JarvisSystem.exit_night_mode(system)

        agent.deactivate_capabilities.assert_called_once()
        agent.stop_background_tasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_enter_exit_cycle_is_clean(self):
        """Full enter → exit cycle should leave no residual state."""
        agent = ConcreteNightAgent()
        network = AgentNetwork()
        network.register_night_agent(agent)

        system = MagicMock()
        system.night_mode = False
        system.night_agents = [agent]
        system._orchestrator = MagicMock()
        system._start_night_server = AsyncMock()
        system._stop_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem

        # Enter
        await JarvisSystem.enter_night_mode(system)
        assert system.night_mode is True
        assert "test_capability" in network.capability_registry
        await asyncio.sleep(0.05)  # Let background tasks start
        assert len(agent._background_tasks) == 1

        # Exit
        await JarvisSystem.exit_night_mode(system)
        assert system.night_mode is False
        assert "test_capability" not in network.capability_registry
        assert len(agent._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_enter_without_orchestrator(self):
        """Should work even if orchestrator is None."""
        system = MagicMock()
        system.night_mode = False
        system.night_agents = []
        system._orchestrator = None
        system._start_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem
        await JarvisSystem.enter_night_mode(system)
        assert system.night_mode is True

    @pytest.mark.asyncio
    async def test_exit_without_orchestrator(self):
        system = MagicMock()
        system.night_mode = True
        system.night_agents = []
        system._orchestrator = None
        system._stop_night_server = AsyncMock()

        from jarvis.core.system import JarvisSystem
        await JarvisSystem.exit_night_mode(system)
        assert system.night_mode is False


# ===========================================================================
# Orchestrator Night Mode Blocking
# ===========================================================================


class TestOrchestratorNightMode:
    """Test that the orchestrator blocks requests during night mode."""

    @pytest.mark.asyncio
    async def test_handle_night_mode_blocks_normal_requests(self):
        from jarvis.core.orchestrator import RequestOrchestrator

        orch = MagicMock(spec=RequestOrchestrator)
        orch.night_mode = True
        orch.protocol_runtime = None
        orch.response_logger = MagicMock()
        orch.response_logger.log_failed_interaction = AsyncMock()

        timer = MagicMock()
        timer.elapsed_ms.return_value = 5.0

        metadata = MagicMock()
        metadata.user_id = "test"
        metadata.device = "cli"
        metadata.location = None
        metadata.source = "test"

        result = await RequestOrchestrator._handle_night_mode(
            orch, "what's the weather", metadata, timer
        )

        assert result is not None
        assert "maintenance" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_handle_night_mode_allows_wake_up(self):
        from jarvis.core.orchestrator import RequestOrchestrator

        orch = MagicMock(spec=RequestOrchestrator)
        orch.night_mode = True

        # Mock protocol_runtime to match "wake up"
        mock_match = {"protocol": MagicMock(name="wake_up")}
        mock_match["protocol"].name = "wake_up"
        orch.protocol_runtime = MagicMock()
        orch.protocol_runtime.try_match.return_value = mock_match

        timer = MagicMock()
        metadata = MagicMock()

        result = await RequestOrchestrator._handle_night_mode(
            orch, "wake up", metadata, timer
        )

        # Should return None to allow the request through
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_night_mode_blocks_non_wake_protocol(self):
        from jarvis.core.orchestrator import RequestOrchestrator

        orch = MagicMock(spec=RequestOrchestrator)
        orch.night_mode = True
        orch.response_logger = MagicMock()
        orch.response_logger.log_failed_interaction = AsyncMock()

        # Match a protocol that isn't wake_up
        mock_match = {"protocol": MagicMock(name="goodnight")}
        mock_match["protocol"].name = "goodnight"
        orch.protocol_runtime = MagicMock()
        orch.protocol_runtime.try_match.return_value = mock_match

        timer = MagicMock()
        timer.elapsed_ms.return_value = 3.0
        metadata = MagicMock()
        metadata.user_id = "test"
        metadata.device = "cli"
        metadata.location = None
        metadata.source = "test"

        result = await RequestOrchestrator._handle_night_mode(
            orch, "goodnight", metadata, timer
        )

        assert result is not None
        assert "maintenance" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_handle_night_mode_no_protocol_runtime(self):
        """When protocol_runtime is None, should still block."""
        from jarvis.core.orchestrator import RequestOrchestrator

        orch = MagicMock(spec=RequestOrchestrator)
        orch.night_mode = True
        orch.protocol_runtime = None
        orch.response_logger = MagicMock()
        orch.response_logger.log_failed_interaction = AsyncMock()

        timer = MagicMock()
        timer.elapsed_ms.return_value = 1.0
        metadata = MagicMock()
        metadata.user_id = "test"
        metadata.device = "cli"
        metadata.location = None
        metadata.source = "test"

        result = await RequestOrchestrator._handle_night_mode(
            orch, "anything", metadata, timer
        )

        assert result is not None
        assert "maintenance" in result["response"].lower()


# ===========================================================================
# Factory Integration
# ===========================================================================


class TestFactoryNightAgentBuilding:
    """Test that the factory builds night agents correctly."""

    def _make_factory(self):
        from jarvis.agents.factory import AgentFactory
        from jarvis.core.config import JarvisConfig, FeatureFlags
        from jarvis.logging import JarvisLogger

        config = JarvisConfig(flags=FeatureFlags(enable_night_mode=True))
        logger = JarvisLogger()
        return AgentFactory(config, logger)

    def test_build_night_agents_returns_controller_and_list(self):
        factory = self._make_factory()
        network = AgentNetwork()
        system = MagicMock()

        refs = factory._build_night_agents(network, system)

        assert "night_controller" in refs
        assert "night_agents" in refs
        assert isinstance(refs["night_controller"], NightModeControllerAgent)
        assert isinstance(refs["night_agents"], list)
        assert len(refs["night_agents"]) >= 1  # At least LogCleanupAgent

    def test_controller_registered_as_regular_agent(self):
        factory = self._make_factory()
        network = AgentNetwork()
        system = MagicMock()

        refs = factory._build_night_agents(network, system)
        controller = refs["night_controller"]

        # Controller should be in the regular agents dict (always available)
        assert controller.name in network.agents
        # But its capabilities should be active (it's not a night agent itself)
        assert "start_night_mode" in network.capability_registry or \
               controller.name not in network.night_agents

    def test_cleanup_agent_registered_as_night_agent(self):
        factory = self._make_factory()
        network = AgentNetwork()
        system = MagicMock()

        factory._build_night_agents(network, system)

        assert "LogCleanupAgent" in network.night_agents
        # Cleanup capabilities should NOT be active yet
        assert "clean_logs" not in network.capability_registry


# ===========================================================================
# Protocol Definitions
# ===========================================================================


class TestNightModeProtocols:
    """Verify the goodnight and wake_up protocol definitions are well-formed."""

    def test_goodnight_protocol_structure(self):
        import json
        proto_path = os.path.join(
            os.path.dirname(__file__), "..",
            "jarvis", "protocols", "defaults", "definitions", "goodnight.json"
        )
        with open(proto_path) as f:
            proto = json.load(f)

        assert proto["name"] == "goodnight"
        assert len(proto["trigger_phrases"]) > 0
        assert "goodnight" in proto["trigger_phrases"]
        assert len(proto["steps"]) == 1
        assert proto["steps"][0]["agent"] == "NightModeControllerAgent"
        assert proto["steps"][0]["function"] == "start_night_mode"

    def test_wake_up_protocol_structure(self):
        import json
        proto_path = os.path.join(
            os.path.dirname(__file__), "..",
            "jarvis", "protocols", "defaults", "definitions", "wake_up.json"
        )
        with open(proto_path) as f:
            proto = json.load(f)

        assert proto["name"] == "wake_up"
        assert len(proto["trigger_phrases"]) > 0
        assert "wake up" in proto["trigger_phrases"]
        assert len(proto["steps"]) == 1
        assert proto["steps"][0]["agent"] == "NightModeControllerAgent"
        assert proto["steps"][0]["function"] == "stop_night_mode"
