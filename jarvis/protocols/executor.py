from __future__ import annotations

import uuid
from typing import Any, Dict

from ..logger import JarvisLogger
from ..agents.agent_network import AgentNetwork
from . import Protocol


class ProtocolExecutor:
    """Executes Protocol steps sequentially using the agent network."""

    def __init__(self, network: AgentNetwork, logger: JarvisLogger) -> None:
        self.network = network
        self.logger = logger

    async def execute(self, protocol: Protocol, extra_params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        extra_params = extra_params or {}
        for step in protocol.steps:
            capability = step.intent
            providers = self.network.capability_registry.get(capability, [])
            if not providers:
                self.logger.log(
                    "ERROR", f"No provider for capability '{capability}'"
                )
                results[step.intent] = {"error": "no_provider"}
                continue

            request_id = str(uuid.uuid4())
            params = {**step.parameters, **extra_params}
            await self.network.request_capability(
                from_agent="ProtocolExecutor",
                capability=capability,
                data=params,
                request_id=request_id,
            )
            try:
                response = await self.network.wait_for_response(request_id)
                results[step.intent] = response
            except Exception as exc:
                results[step.intent] = {"error": str(exc)}
        return results
