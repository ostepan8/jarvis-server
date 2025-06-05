from __future__ import annotations

from typing import Any, Dict

from ..logger import JarvisLogger


class AgentNetwork:
    """Simple network coordinating multiple agents."""

    def __init__(self, logger: JarvisLogger | None = None) -> None:
        self.logger = logger or JarvisLogger()
        self.agents: Dict[str, Any] = {}

    def add_agent(self, name: str, agent: Any) -> None:
        """Register an agent in the network."""
        self.agents[name] = agent
        self.logger.log("INFO", "Agent added", name)

    async def dispatch(self, agent_name: str, command: str) -> Dict[str, Any]:
        """Send a command to a specific agent and return its response."""
        agent = self.agents.get(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        if hasattr(agent, "process_request_with_reasoning"):
            return await agent.process_request_with_reasoning(command)
        if hasattr(agent, "process_request"):
            response, actions = await agent.process_request(command)
            return {"response": response, "actions": actions}

        raise ValueError(f"Agent {agent_name} cannot handle requests")
