from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict

from ..logger import JarvisLogger
from ..agents.agent_network import AgentNetwork
from .loggers import ProtocolUsageLogger
from .models import Protocol, ResponseMode
from .executor import ProtocolExecutor
from .registry import ProtocolRegistry
from .voice_trigger import VoiceTriggerMatcher
from .loader import ProtocolLoader


class ProtocolRuntime:
    """Facade responsible for protocol matching, execution and formatting."""

    def __init__(
        self,
        network: AgentNetwork,
        logger: JarvisLogger,
        *,
        usage_logger: ProtocolUsageLogger | None = None,
    ) -> None:
        self.network = network
        self.logger = logger
        self.registry = ProtocolRegistry(logger=logger)
        self.executor = ProtocolExecutor(network, logger, usage_logger=usage_logger)
        self.voice_matcher: VoiceTriggerMatcher | None = None
        self.loader = ProtocolLoader(self.registry, logger)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def initialize(
        self,
        load_directory: bool = True,
        definitions_dir: Path | None = None,
    ) -> None:
        """Load protocol definitions and prepare matcher."""
        if load_directory:
            if definitions_dir is None:
                definitions_dir = Path(__file__).parent / "defaults" / "definitions"
            self.loader.load_directory(definitions_dir)
        self.voice_matcher = VoiceTriggerMatcher(self.registry.protocols)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    def try_match(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Attempt to match ``user_input`` against known protocols."""
        match_result = None
        if self.voice_matcher:
            match_result = self.voice_matcher.match_command(user_input)
        if not match_result:
            proto = self.registry.find_matching_protocol(user_input)
            if proto:
                match_result = {
                    "protocol": proto,
                    "arguments": {},
                    "matched_phrase": user_input,
                }
        return match_result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def run_and_format(
        self,
        match: Dict[str, Any],
        *,
        trigger_phrase: str,
        metadata: Dict[str, Any] | None = None,
        allowed_agents: set[str] | None = None,
    ) -> str:
        """Execute a matched protocol and return a formatted response."""
        results = await self.executor.run_protocol_with_match(
            match,
            trigger_phrase=trigger_phrase,
            metadata=metadata,
            allowed_agents=allowed_agents,
        )
        protocol = match["protocol"]
        return await self._format_protocol_response(protocol, results, match.get("arguments"))

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------
    def list_protocols(self, allowed_agents: set[str] | None = None) -> list[Protocol]:
        """Return protocols whose required agents are available and allowed."""
        available = set(self.network.agents.keys())
        protocols = []
        for proto in self.registry.protocols.values():
            required = {step.agent for step in proto.steps}
            if not required.issubset(available):
                continue
            if allowed_agents is not None and not required.issubset(allowed_agents):
                continue
            protocols.append(proto)
        return protocols

    def get_available_commands(self, allowed_agents: set[str] | None = None) -> Dict[str, list[str]]:
        """Return available trigger phrases grouped by protocol name."""
        commands: Dict[str, list[str]] = {}
        for proto in self.list_protocols(allowed_agents):
            commands[proto.name] = proto.trigger_phrases
        return commands

    # ------------------------------------------------------------------
    # Response formatting
    # ------------------------------------------------------------------
    async def _format_protocol_response(
        self,
        protocol: Protocol,
        results: Dict[str, Any],
        arguments: Dict[str, Any] | None = None,
    ) -> str:
        """Format protocol execution results in Jarvis style."""
        errors = []
        successes = []
        for step_id, result in results.items():
            if isinstance(result, dict) and "error" in result:
                errors.append(result["error"])
            else:
                successes.append(step_id)

        if errors:
            return (
                "I encountered some issues executing that command, sir. "
                + ". ".join(errors)
            )

        response_cfg = protocol.response
        if response_cfg is None:
            resp = f"{protocol.name} completed successfully, sir."
            if arguments:
                for k, v in arguments.items():
                    resp = resp.replace(f"{{{k}}}", str(v))
            return resp

        if response_cfg.mode == ResponseMode.STATIC:
            if not response_cfg.phrases:
                return ""
            resp = random.choice(response_cfg.phrases)
            if arguments:
                for k, v in arguments.items():
                    resp = resp.replace(f"{{{k}}}", str(v))
            return resp

        if response_cfg.mode == ResponseMode.AI:
            base_prompt = response_cfg.prompt or ""
            context_prompt = base_prompt
            if arguments:
                for k, v in arguments.items():
                    context_prompt = context_prompt.replace(f"{{{k}}}", str(v))
                    base_prompt = base_prompt.replace(f"{{{k}}}", str(v))
            chat_agent = self.network.agents.get("ChatAgent")
            if chat_agent is None:
                return base_prompt
            message, _ = await chat_agent.ai_client.weak_chat(
                [{"role": "user", "content": context_prompt}], [],
            )
            return message.content

        return ""
