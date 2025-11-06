# protocols/executor.py
from __future__ import annotations

from typing import Any, Dict, Optional
import time

from ..logging import JarvisLogger
from ..agents.agent_network import AgentNetwork
from ..core.constants import ExecutionResult
from . import Protocol
from .loggers import ProtocolUsageLogger, generate_protocol_log


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
        allowed_agents: set[str] | None = None,
    ) -> Dict[str, Any]:
        """Public helper to execute a protocol."""
        return await self.execute(
            protocol, arguments, trigger_phrase, metadata, allowed_agents
        )

    async def run_protocol_with_match(
        self,
        match_result: Dict[str, Any],
        *,
        trigger_phrase: str | None = None,
        metadata: Dict[str, Any] | None = None,
        allowed_agents: set[str] | None = None,
    ) -> Dict[str, Any]:
        """Execute a protocol using the result from enhanced voice matcher."""
        print("Running protocol with match result:", match_result)
        protocol = match_result["protocol"]
        extracted_args = match_result["arguments"]
        matched_phrase = match_result["matched_phrase"]

        # Enhanced metadata to include match information
        enhanced_metadata = {
            **(metadata or {}),
            "matched_phrase": matched_phrase,
            "extracted_arguments": extracted_args,
        }

        return await self.execute(
            protocol,
            extracted_args,
            trigger_phrase or matched_phrase,
            enhanced_metadata,
            allowed_agents,
        )

    async def execute(
        self,
        protocol: Protocol,
        context: Dict[str, Any] | None = None,
        trigger_phrase: str | None = None,
        metadata: Dict[str, Any] | None = None,
        allowed_agents: set[str] | None = None,
    ) -> Dict[str, Any]:
        """Execute each step in protocol directly."""

        start = time.monotonic()
        results: Dict[str, Any] = {}
        context = context or {}

        # Log the extracted arguments
        if context:
            self.logger.log(
                "INFO",
                f"Executing protocol '{protocol.name}' with arguments",
                str(context),
            )

        for i, step in enumerate(protocol.steps):
            step_id = f"step_{i}_{step.function}"

            if allowed_agents is not None and step.agent not in allowed_agents:
                self.logger.log(
                    "WARNING",
                    f"Agent '{step.agent}' not allowed for step {step_id}",
                )
                results[step_id] = {"error": "agent_disallowed"}
                continue

            # Get the agent
            agent = self.network.agents.get(step.agent)
            if not agent:
                self.logger.log(
                    "ERROR",
                    f"Agent '{step.agent}' not found",
                )
                results[step_id] = {"error": "agent_not_found"}
                continue

            # Prepare parameters
            params = dict(step.parameters)

            # Apply parameter mappings (enhanced to handle extracted arguments)
            for param_name, mapping in step.parameter_mappings.items():
                if mapping.startswith("$"):
                    # Reference to previous result or extracted argument
                    ref = mapping[1:]  # Remove $

                    # First check extracted arguments (from voice command)
                    if ref in context:
                        params[param_name] = context[ref]
                        self.logger.log(
                            "DEBUG",
                            f"Mapped parameter '{param_name}' from extracted argument",
                            f"{ref} -> {context[ref]}",
                        )
                    # Then check previous step results
                    elif ref in results:
                        params[param_name] = results[ref]
                        self.logger.log(
                            "DEBUG",
                            f"Mapped parameter '{param_name}' from previous result",
                            f"{ref} -> {results[ref]}",
                        )
                    else:
                        self.logger.log(
                            "WARNING",
                            f"Parameter mapping reference '{ref}' not found",
                            f"Available context: {list(context.keys())}, results: {list(results.keys())}",
                        )

            # Execute the capability
            try:
                self.logger.log(
                    "INFO", f"Executing {step.agent}.{step.function}", str(params)
                )

                result = await agent.run_capability(step.function, **params)

                # Detect string-based failures (common pattern in agent methods)
                if isinstance(result, str) and result.lower().startswith("failed to"):
                    self.logger.log(
                        "WARNING",
                        f"Step {step_id} returned failure string",
                        result,
                    )
                    results[step_id] = {"error": result}
                # Detect tuple-based errors (some methods return (None, error_message))
                elif isinstance(result, tuple) and len(result) == 2:
                    first, second = result
                    # Check if first element is falsy (None, False, empty string, etc.)
                    # and second is an error message string
                    if not first and isinstance(second, str):
                        error_msg = second if second else "Unknown error"
                        self.logger.log(
                            "WARNING",
                            f"Step {step_id} returned error tuple",
                            error_msg,
                        )
                        results[step_id] = {"error": error_msg}
                    else:
                        results[step_id] = result
                else:
                    results[step_id] = result
                self.logger.log("INFO", f"Step {step_id} completed", str(result))

            except NotImplementedError:
                self.logger.log(
                    "ERROR",
                    f"Function '{step.function}' not found in {step.agent}",
                )
                results[step_id] = {"error": "function_not_found"}
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
                ExecutionResult.PARTIAL
                if len(errors) < len(protocol.steps)
                else ExecutionResult.FAILURE
            )
        else:
            execution_result = ExecutionResult.SUCCESS

        latency_ms = int((time.monotonic() - start) * 1000)

        if self.usage_logger:
            log_doc = generate_protocol_log(
                protocol,
                context,
                trigger_phrase,
                {
                    **(metadata or {}),
                    "execution_result": execution_result.value,
                    "latency_ms": latency_ms,
                    "extracted_arguments": context,  # Log the extracted arguments
                },
            )
            await self.usage_logger.log_usage(log_doc)

        return results
