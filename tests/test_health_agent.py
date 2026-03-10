"""Tests for HealthAgent."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from jarvis.agents.health_agent import HealthAgent
from jarvis.agents.health_agent.models import (
    ComponentStatus,
    IncidentSeverity,
    IncidentRecord,
    ProbeResult,
    SystemHealthSnapshot,
    DependencyNode,
)
from jarvis.agents.health_agent.probes import probe_agents, probe_network
from jarvis.agents.health_agent.dependency_map import build_dependency_graph
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.response import AgentResponse
from jarvis.services.health_service import HealthService
from jarvis.logging import JarvisLogger


def _make_mock_network(agent_names=None, capabilities=None):
    """Create a mock AgentNetwork with agents."""
    network = MagicMock(spec=AgentNetwork)
    network.agents = {}
    network.capability_registry = capabilities or {}

    for name in (agent_names or []):
        agent = MagicMock()
        agent.name = name
        agent.capabilities = {"cap1", "cap2"}
        agent.receive_message = AsyncMock()
        network.agents[name] = agent

    # Wire capability registry if not provided
    if capabilities is None and agent_names:
        for name in agent_names:
            for cap in ["cap1", "cap2"]:
                network.capability_registry.setdefault(cap, []).append(name)

    network.get_metrics.return_value = {
        "direct_messages": 10,
        "queued_messages": 5,
        "broadcast_messages": 2,
        "future_cleanups": 0,
        "dropped_messages": 0,
        "backpressure_events": 0,
        "active_futures": 0,
        "queue_depths": {"high": 0, "normal": 0, "low": 0},
        "total_queue_size": 0,
        "backpressure_threshold": 800,
        "circuit_breaker_active": False,
        "response_aggregator": {},
    }

    return network


def _make_health_agent(report_dir, network=None):
    """Create a HealthAgent for testing."""
    service = HealthService(timeout=1.0)
    agent = HealthAgent(
        health_service=service,
        logger=JarvisLogger(),
        probe_interval=9999,  # Don't auto-probe in tests
        report_dir=report_dir,
    )
    if network:
        # Don't start background task in tests
        agent.network = network
    return agent


class TestHealthAgentProperties:
    """Test agent metadata."""

    def test_name(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        assert agent.name == "HealthAgent"

    def test_capabilities(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        expected = {
            "system_health_check",
            "agent_health_status",
            "service_health_status",
            "system_resource_status",
            "health_report",
            "dependency_map",
            "incident_list",
        }
        assert agent.capabilities == expected

    def test_description(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        assert "health" in agent.description.lower()

    def test_intent_map_matches_capabilities(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        assert set(agent.intent_map.keys()) == agent.capabilities


class TestProbeLogic:
    """Test probe functions."""

    def test_probe_agents_healthy(self, tmp_path):
        network = _make_mock_network(["TestAgent"])
        results = probe_agents(network)
        assert len(results) == 1
        assert results[0].status == ComponentStatus.HEALTHY
        assert results[0].component == "TestAgent"

    def test_probe_agents_no_network(self):
        results = probe_agents(None)
        assert len(results) == 1
        assert results[0].status == ComponentStatus.UNHEALTHY

    def test_probe_agents_no_registered_caps(self):
        network = _make_mock_network(["TestAgent"], capabilities={})
        results = probe_agents(network)
        assert results[0].status == ComponentStatus.DEGRADED

    def test_probe_network_healthy(self):
        network = _make_mock_network()
        results = probe_network(network)
        assert len(results) >= 1
        assert results[0].component == "MessageBroker"
        assert results[0].status == ComponentStatus.HEALTHY

    def test_probe_network_circuit_breaker(self):
        network = _make_mock_network()
        metrics = network.get_metrics.return_value
        metrics["circuit_breaker_active"] = True
        metrics["dropped_messages"] = 10
        results = probe_network(network)
        assert results[0].status == ComponentStatus.UNHEALTHY

    def test_probe_network_dropped_messages(self):
        network = _make_mock_network()
        metrics = network.get_metrics.return_value
        metrics["dropped_messages"] = 5
        results = probe_network(network)
        assert results[0].status == ComponentStatus.DEGRADED

    def test_probe_network_no_network(self):
        results = probe_network(None)
        assert results[0].status == ComponentStatus.UNHEALTHY


class TestIncidentLifecycle:
    """Test incident open/resolve logic."""

    @pytest.mark.asyncio
    async def test_incident_opens_on_failure(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["TestAgent"]))

        # First probe sets baseline
        agent._component_statuses["TestComp"] = ComponentStatus.HEALTHY

        # Simulate transition to unhealthy
        snapshot = SystemHealthSnapshot(
            agent_statuses=[
                ProbeResult("TestComp", "agent", ComponentStatus.UNHEALTHY, message="Down")
            ],
        )
        await agent._process_transitions(snapshot)

        active = [i for i in agent._incidents if i.is_active]
        assert len(active) == 1
        assert active[0].component == "TestComp"
        assert active[0].severity == IncidentSeverity.ERROR

    @pytest.mark.asyncio
    async def test_incident_resolves_on_recovery(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["TestAgent"]))

        # Create active incident
        agent._component_statuses["TestComp"] = ComponentStatus.UNHEALTHY
        agent._incidents.append(
            IncidentRecord(
                component="TestComp",
                severity=IncidentSeverity.ERROR,
                title="TestComp down",
            )
        )

        # Simulate recovery
        snapshot = SystemHealthSnapshot(
            agent_statuses=[
                ProbeResult("TestComp", "agent", ComponentStatus.HEALTHY, message="Up")
            ],
        )
        await agent._process_transitions(snapshot)

        active = [i for i in agent._incidents if i.is_active]
        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_no_duplicate_incident_on_stable_state(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network())

        # Already unhealthy
        agent._component_statuses["TestComp"] = ComponentStatus.UNHEALTHY

        snapshot = SystemHealthSnapshot(
            agent_statuses=[
                ProbeResult("TestComp", "agent", ComponentStatus.UNHEALTHY, message="Still down")
            ],
        )
        await agent._process_transitions(snapshot)

        # No new incidents (status didn't change)
        assert len(agent._incidents) == 0


class TestHealthAlertBroadcast:
    """Test health alert broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcasts_on_transition(self, tmp_path):
        network = _make_mock_network(["AgentA", "AgentB"])
        agent = _make_health_agent(str(tmp_path), network)
        agent._component_statuses["SomeComp"] = ComponentStatus.HEALTHY

        snapshot = SystemHealthSnapshot(
            agent_statuses=[
                ProbeResult("SomeComp", "agent", ComponentStatus.UNHEALTHY, message="Failed")
            ],
        )
        await agent._process_transitions(snapshot)

        # Both agents should have received a health_alert
        for name in ["AgentA", "AgentB"]:
            mock_agent = network.agents[name]
            assert mock_agent.receive_message.called
            call_args = mock_agent.receive_message.call_args[0][0]
            assert call_args.message_type == "health_alert"
            assert call_args.content["component"] == "SomeComp"
            assert call_args.content["new_status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_no_broadcast_on_stable_state(self, tmp_path):
        network = _make_mock_network(["AgentA"])
        agent = _make_health_agent(str(tmp_path), network)
        agent._component_statuses["SomeComp"] = ComponentStatus.HEALTHY

        snapshot = SystemHealthSnapshot(
            agent_statuses=[
                ProbeResult("SomeComp", "agent", ComponentStatus.HEALTHY, message="OK")
            ],
        )
        await agent._process_transitions(snapshot)

        # No broadcasts on stable state
        assert not network.agents["AgentA"].receive_message.called


class TestCapabilityHandlers:
    """Test capability request handling."""

    @pytest.mark.asyncio
    async def test_system_health_check(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["TestAgent"]))
        result = await agent._system_health_check()
        assert isinstance(result, AgentResponse)
        assert result.success
        assert result.data is not None
        assert "overall_status" in result.data

    @pytest.mark.asyncio
    async def test_agent_health_status(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["TestAgent"]))
        result = await agent._agent_health_status(prompt="")
        assert result.success
        assert "agents" in result.data

    @pytest.mark.asyncio
    async def test_service_health_status(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network())
        result = await agent._service_health_status()
        assert result.success
        assert "services" in result.data

    @pytest.mark.asyncio
    async def test_system_resource_status(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network())
        result = await agent._system_resource_status()
        assert result.success
        assert "resources" in result.data

    @pytest.mark.asyncio
    async def test_health_report(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["TestAgent"]))
        result = await agent._health_report()
        assert result.success
        assert result.response  # Should have report content

    @pytest.mark.asyncio
    async def test_dependency_map(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network(["CalendarAgent"]))
        result = await agent._dependency_map()
        assert result.success
        assert "nodes" in result.data
        assert len(result.data["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_incident_list(self, tmp_path):
        agent = _make_health_agent(str(tmp_path), _make_mock_network())
        agent._incidents.append(
            IncidentRecord(component="Test", title="Test incident")
        )
        result = await agent._incident_list(data={"prompt": ""})
        assert result.success
        assert len(result.data["incidents"]) == 1


class TestDependencyGraph:
    """Test dependency map building."""

    def test_static_graph(self):
        nodes = build_dependency_graph()
        names = {n.name for n in nodes}
        assert "CalendarAgent" in names
        assert "CalendarService" in names

    def test_graph_with_network(self):
        network = _make_mock_network(["CustomAgent"])
        nodes = build_dependency_graph(network=network)
        names = {n.name for n in nodes}
        assert "CustomAgent" in names

    def test_graph_with_statuses(self):
        statuses = {"CalendarAgent": ComponentStatus.UNHEALTHY}
        nodes = build_dependency_graph(latest_statuses=statuses)
        cal = next(n for n in nodes if n.name == "CalendarAgent")
        assert cal.status == ComponentStatus.UNHEALTHY


class TestOverallStatus:
    """Test overall status computation."""

    def test_all_healthy(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        results = [
            ProbeResult("A", "agent", ComponentStatus.HEALTHY),
            ProbeResult("B", "service", ComponentStatus.HEALTHY),
        ]
        assert agent._compute_overall_status(results) == ComponentStatus.HEALTHY

    def test_any_unhealthy(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        results = [
            ProbeResult("A", "agent", ComponentStatus.HEALTHY),
            ProbeResult("B", "service", ComponentStatus.UNHEALTHY),
        ]
        assert agent._compute_overall_status(results) == ComponentStatus.UNHEALTHY

    def test_degraded_only(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        results = [
            ProbeResult("A", "agent", ComponentStatus.HEALTHY),
            ProbeResult("B", "service", ComponentStatus.DEGRADED),
        ]
        assert agent._compute_overall_status(results) == ComponentStatus.DEGRADED

    def test_all_unknown(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        results = [
            ProbeResult("A", "agent", ComponentStatus.UNKNOWN),
        ]
        assert agent._compute_overall_status(results) == ComponentStatus.UNKNOWN

    def test_empty_results(self, tmp_path):
        agent = _make_health_agent(str(tmp_path))
        assert agent._compute_overall_status([]) == ComponentStatus.UNKNOWN
