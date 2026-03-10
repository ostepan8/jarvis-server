from __future__ import annotations
from typing import Dict, List, Optional, TYPE_CHECKING
from .models import DependencyNode, ComponentStatus

if TYPE_CHECKING:
    from jarvis.agents.agent_network import AgentNetwork


# Static knowledge of agent -> service -> API dependencies
STATIC_DEPENDENCIES: Dict[str, List[str]] = {
    "CalendarAgent": ["CalendarService"],
    "WeatherAgent": ["WeatherAPI"],
    "MemoryAgent": ["ChromaDB", "VectorMemoryService"],
    "SearchAgent": ["GoogleSearchAPI"],
    "LightingAgent": ["HueBridge"],
    "RokuAgent": ["RokuDevice"],
    "ChatAgent": ["OpenAI_API"],
    "NLUAgent": ["OpenAI_API"],
    "TodoAgent": ["SQLite"],
    "ProtocolAgent": [],
    "CanvasAgent": ["CanvasService"],
}

SERVICE_TYPES: Dict[str, str] = {
    "CalendarService": "service",
    "WeatherAPI": "external_api",
    "ChromaDB": "service",
    "VectorMemoryService": "service",
    "GoogleSearchAPI": "external_api",
    "HueBridge": "external_api",
    "RokuDevice": "external_api",
    "OpenAI_API": "external_api",
    "SQLite": "service",
    "CanvasService": "service",
}


def build_dependency_graph(
    network: Optional[AgentNetwork] = None,
    latest_statuses: Optional[Dict[str, ComponentStatus]] = None,
) -> List[DependencyNode]:
    """Build a dependency graph from static knowledge + live network state."""
    nodes: Dict[str, DependencyNode] = {}
    statuses = latest_statuses or {}

    # Build from static knowledge
    for agent_name, deps in STATIC_DEPENDENCIES.items():
        nodes.setdefault(
            agent_name,
            DependencyNode(
                name=agent_name,
                node_type="agent",
                status=statuses.get(agent_name, ComponentStatus.UNKNOWN),
                depends_on=list(deps),
            ),
        )
        for dep in deps:
            dep_node = nodes.setdefault(
                dep,
                DependencyNode(
                    name=dep,
                    node_type=SERVICE_TYPES.get(dep, "service"),
                    status=statuses.get(dep, ComponentStatus.UNKNOWN),
                ),
            )
            if agent_name not in dep_node.depended_by:
                dep_node.depended_by.append(agent_name)

    # Enrich from live network
    if network:
        for agent_name in network.agents:
            if agent_name not in nodes:
                nodes[agent_name] = DependencyNode(
                    name=agent_name,
                    node_type="agent",
                    status=statuses.get(agent_name, ComponentStatus.HEALTHY),
                )

    return list(nodes.values())
