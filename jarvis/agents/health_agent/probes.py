from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from .models import ProbeResult, ComponentStatus

if TYPE_CHECKING:
    from jarvis.agents.agent_network import AgentNetwork


def probe_agents(network: Optional[AgentNetwork]) -> List[ProbeResult]:
    """Check all registered agents in the network."""
    results = []
    if not network:
        return [ProbeResult(
            component="AgentNetwork",
            component_type="network",
            status=ComponentStatus.UNHEALTHY,
            message="Network not available",
        )]

    for agent_name, agent in network.agents.items():
        try:
            caps = agent.capabilities
            has_caps = len(caps) > 0
            # Check if agent has capabilities registered in network
            registered_caps = set()
            for cap, providers in network.capability_registry.items():
                if agent_name in providers:
                    registered_caps.add(cap)

            if has_caps and registered_caps:
                status = ComponentStatus.HEALTHY
                msg = f"Registered with {len(registered_caps)} capabilities"
            elif has_caps and not registered_caps:
                status = ComponentStatus.DEGRADED
                msg = f"Agent has {len(caps)} capabilities but none registered in network"
            else:
                status = ComponentStatus.DEGRADED
                msg = "Agent has no capabilities"

            results.append(ProbeResult(
                component=agent_name,
                component_type="agent",
                status=status,
                message=msg,
                details={"capabilities": list(caps), "registered": list(registered_caps)},
            ))
        except Exception as exc:
            results.append(ProbeResult(
                component=agent_name,
                component_type="agent",
                status=ComponentStatus.UNHEALTHY,
                message=f"Error probing agent: {exc}",
            ))

    return results


def probe_network(network: Optional[AgentNetwork]) -> List[ProbeResult]:
    """Check network health via metrics."""
    if not network:
        return [ProbeResult(
            component="AgentNetwork",
            component_type="network",
            status=ComponentStatus.UNHEALTHY,
            message="Network not available",
        )]

    results = []
    try:
        metrics = network.get_metrics()

        # Check circuit breaker
        cb_active = metrics.get("circuit_breaker_active", False)
        dropped = metrics.get("dropped_messages", 0)
        total_queue = metrics.get("total_queue_size", 0)

        if cb_active:
            status = ComponentStatus.UNHEALTHY
            msg = f"Circuit breaker ACTIVE. Dropped: {dropped}, Queue: {total_queue}"
        elif dropped > 0:
            status = ComponentStatus.DEGRADED
            msg = f"Messages dropped: {dropped}, Queue depth: {total_queue}"
        else:
            status = ComponentStatus.HEALTHY
            msg = f"Queue depth: {total_queue}, Messages processed: {metrics.get('direct_messages', 0) + metrics.get('queued_messages', 0)}"

        results.append(ProbeResult(
            component="MessageBroker",
            component_type="network",
            status=status,
            message=msg,
            details=metrics,
        ))

        # Check queue depths
        queue_depths = metrics.get("queue_depths", {})
        for priority, depth in queue_depths.items():
            if depth > 100:
                results.append(ProbeResult(
                    component=f"Queue_{priority}",
                    component_type="network",
                    status=ComponentStatus.DEGRADED,
                    message=f"{priority} queue depth: {depth}",
                ))

    except Exception as exc:
        results.append(ProbeResult(
            component="NetworkMetrics",
            component_type="network",
            status=ComponentStatus.UNHEALTHY,
            message=f"Error reading network metrics: {exc}",
        ))

    return results
