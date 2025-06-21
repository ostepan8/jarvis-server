# protocols/executor.py
from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
from functools import partial
import time

from ..logger import JarvisLogger
from ..agents.agent_network import AgentNetwork
from . import Protocol
from .mongo_logger import ProtocolUsageLogger, generate_protocol_log


class ProtocolExecutor:
    """Executes Protocol steps directly without AI reasoning."""

    def __init__(
        self,
        network: AgentNetwork,
        logger: JarvisLogger,
        usage_logger: ProtocolUsageLogger | None = None,
    ) -> None:
        self.network = network
        self.logger = logger
        self.usage_logger = usage_logger

    async def run_protocol(
        self,
        protocol: Protocol,
        arguments: Dict[str, Any] | None = None,
        *,
        trigger_phrase: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Public helper to execute a protocol."""
        return await self.execute(protocol, arguments, trigger_phrase, metadata)

    async def execute(
        self,
        protocol: Protocol,
        context: Dict[str, Any] | None = None,
        trigger_phrase: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Execute each step in protocol directly."""

        start = time.monotonic()
        results: Dict[str, Any] = {}
        context = context or {}

        for i, step in enumerate(protocol.steps):
            step_id = f"step_{i}_{step.function}"

            # Get the agent
            agent = self.network.agents.get(step.agent)
            if not agent:
                self.logger.log(
                    "ERROR",
                    f"Agent '{step.agent}' not found",
                )
                results[step_id] = {"error": "agent_not_found"}
                continue

            # Get the function from intent_map
            intent_map = getattr(agent, "intent_map", {})
            func = intent_map.get(step.function)

            if not func:
                self.logger.log(
                    "ERROR",
                    f"Function '{step.function}' not found in {step.agent}",
                )
                results[step_id] = {"error": "function_not_found"}
                continue

            # Prepare parameters
            params = dict(step.parameters)

            # Apply parameter mappings (use results from previous steps)
            for param_name, mapping in step.parameter_mappings.items():
                if mapping.startswith("$"):
                    # Reference to previous result
                    ref = mapping[1:]  # Remove $
                    if ref in results:
                        params[param_name] = results[ref]
                    elif ref in context:
                        params[param_name] = context[ref]

            # Execute the function
            try:
                self.logger.log(
                    "INFO", f"Executing {step.agent}.{step.function}", str(params)
                )

                if asyncio.iscoroutinefunction(func):
                    result = await func(**params)
                else:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, partial(func, **params))

                results[step_id] = result
                self.logger.log("INFO", f"Step {step_id} completed", str(result))

            except Exception as exc:
                self.logger.log(
                    "ERROR",
                    f"Error executing {step.agent}.{step.function}",
                    str(exc),
                )
                results[step_id] = {"error": str(exc)}

        # Determine overall execution result
        errors = [r for r in results.values() if isinstance(r, dict) and "error" in r]
        if errors:
            execution_result = (
                "partial" if len(errors) < len(protocol.steps) else "failure"
            )
        else:
            execution_result = "success"

        latency_ms = int((time.monotonic() - start) * 1000)

        if self.usage_logger:
            log_doc = generate_protocol_log(
                protocol,
                context,
                trigger_phrase,
                {
                    **(metadata or {}),
                    "execution_result": execution_result,
                    "latency_ms": latency_ms,
                },
            )
            await self.usage_logger.log_usage(log_doc)  # <- Use log_usage_raw

        return results
