from __future__ import annotations

from typing import Any, Dict

import asyncio
from functools import partial

from ..logger import JarvisLogger
from ..agents.agent_network import AgentNetwork
from . import Protocol


class ProtocolExecutor:
    """Executes Protocol steps sequentially using the agent network."""

    def __init__(self, network: AgentNetwork, logger: JarvisLogger) -> None:
        self.network = network
        self.logger = logger

    async def execute(
        self, protocol: Protocol, args: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Run each step in *protocol* synchronously without AI reasoning."""

        results: Dict[str, Any] = {}
        args = {**protocol.arguments, **(args or {})}

        for step in protocol.steps:
            capability = step.intent
            providers = self.network.capability_registry.get(capability, [])
            if not providers:
                self.logger.log(
                    "ERROR",
                    f"No provider for capability '{capability}'",
                )
                results[step.intent] = {"error": "no_provider"}
                continue

            provider = self.network.agents.get(providers[0])
            if not provider:
                self.logger.log(
                    "ERROR",
                    f"Provider '{providers[0]}' not found for '{capability}'",
                )
                results[step.intent] = {"error": "no_provider"}
                continue

            mapping = (
                getattr(provider, "intent_map", None)
                or getattr(provider, "intent_tool_map", None)
            )
            if not mapping or capability not in mapping:
                self.logger.log(
                    "ERROR",
                    f"Provider '{provider.name}' lacks intent map for '{capability}'",
                )
                results[step.intent] = {"error": "no_handler"}
                continue

            func = mapping[capability]
            params = {**args}
            for k, v in step.parameters.items():
                if isinstance(v, str):
                    try:
                        params[k] = v.format(**args)
                    except Exception:
                        params[k] = v
                else:
                    params[k] = v

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(**params)
                else:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, partial(func, **params))
                results[step.intent] = result
            except Exception as exc:  # pragma: no cover - error path
                self.logger.log(
                    "ERROR",
                    f"Error executing {capability} via direct call",
                    str(exc),
                )
                results[step.intent] = {"error": str(exc)}

        return results
