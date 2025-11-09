# jarvis/core/system.py

import asyncio
from os import getenv
import uuid
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from ..agents.agent_network import AgentNetwork
from ..night_agents import NightAgent, NightModeControllerAgent
from ..ai_clients import AIClientFactory, BaseAIClient
from ..logging import JarvisLogger
from .config import JarvisConfig
from .method_recorder import MethodRecorder
from ..protocols.loggers import ProtocolUsageLogger, InteractionLogger
from ..protocols.runtime import ProtocolRuntime
from ..utils.performance import PerfTracker, get_tracker
from ..agents.factory import AgentFactory
from .orchestrator import RequestOrchestrator
from .response_logger import ResponseLogger


class JarvisSystem:
    """Main Jarvis system that manages the agent network."""

    def __init__(
        self,
        config: JarvisConfig | Dict[str, Any],
        record_network_methods: bool = False,
        method_recorder: MethodRecorder | None = None,
    ):
        """Create a new Jarvis system."""
        if isinstance(config, dict):
            self.config = JarvisConfig(**config)
        else:
            self.config = config

        if not record_network_methods:
            record_network_methods = self.config.record_network_methods

        # Check environment variable for verbose mode
        verbose = getenv("JARVIS_VERBOSE", "false").lower() in ("true", "1", "yes")
        self.logger = JarvisLogger(verbose=verbose)
        self.network = AgentNetwork(
            self.logger,
            record_methods=record_network_methods,
            recorder=method_recorder,
        )
        self.perf_enabled = self.config.perf_tracking
        self._tracker: PerfTracker | None = None

        # Night mode management
        self.night_mode: bool = False
        self.night_agents: list[NightAgent] = []
        self.night_controller: NightModeControllerAgent | None = None

        # Protocol runtime and loggers
        self.protocol_runtime: ProtocolRuntime | None = None
        self.usage_logger = ProtocolUsageLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name=getenv("MONGO_DB_NAME", "protocol"),
        )
        self.interaction_logger = InteractionLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name=getenv("MONGO_DB_NAME", "protocol"),
        )

        # Request orchestrator (initialized after network setup)
        self._orchestrator: RequestOrchestrator | None = None
        self._response_logger: ResponseLogger | None = None

    async def initialize(self, load_protocol_directory: bool = False) -> None:
        """Initialize all agents and start the network."""
        ai_client = self._create_ai_client()
        await self._connect_mongo_loggers()

        factory = AgentFactory(self.config, self.logger)
        refs = factory.build_all(self.network, ai_client, self)

        # Store agent references internally
        self._agent_refs = refs

        # Extract specific references needed for night mode
        self.night_controller = refs.get("night_controller")
        self.night_agents = refs.get("night_agents", [])

        self._setup_protocol_system(load_protocol_directory)
        await self._start_network()

        # Initialize orchestrator and response logger
        self._response_logger = ResponseLogger(self.interaction_logger)
        self._orchestrator = RequestOrchestrator(
            network=self.network,
            protocol_runtime=self.protocol_runtime,
            response_logger=self._response_logger,
            logger=self.logger,
            response_timeout=self.config.response_timeout,
            max_history_length=10,
        )

        loaded = (
            len(self.protocol_runtime.registry.protocols)
            if self.protocol_runtime
            else 0
        )
        self.logger.log(
            "INFO",
            "Jarvis system initialized",
            f"Active agents: {list(self.network.agents.keys())}, "
            f"Loaded protocols: {loaded}",
        )

    def _create_ai_client(self) -> BaseAIClient:
        """Instantiate the configured AI client."""
        return AIClientFactory.create(
            self.config.ai_provider, api_key=self.config.api_key
        )

    async def _connect_mongo_loggers(self) -> None:
        """Connect both MongoDB loggers during initialization."""
        await self.usage_logger.connect()
        await self.interaction_logger.connect()

    def list_agents(self) -> Dict[str, Any]:
        """List all registered agents in the network."""
        agents_info = {}
        for agent_name, agent in self.network.agents.items():
            agents_info[agent_name] = {
                "name": agent.name,
                "capabilities": agent.capabilities,
                "description": agent.description,
                "required_resources": getattr(agent.profile, "required_resources", []),
            }
        return agents_info

    def get_agent_capabilities(self, agent_name: str) -> Dict[str, Any]:
        """Get detailed capabilities for a specific agent by name."""
        if agent_name not in self.network.agents:
            return {
                "error": f"Agent '{agent_name}' not found",
                "available_agents": list(self.network.agents.keys()),
            }

        agent = self.network.agents[agent_name]
        return {
            "name": agent.name,
            "capabilities": agent.capabilities,
            "description": getattr(agent, "description", "No description available"),
            "status": "active" if agent_name in self.network.agents else "inactive",
        }

    def list_protocols(self, allowed_agents: set[str] | None = None):
        """Delegate to protocol runtime to list protocols."""
        if not self.protocol_runtime:
            return []
        return self.protocol_runtime.list_protocols(allowed_agents)

    def _setup_protocol_system(
        self,
        load_protocol_directory: bool = False,
        definition_dir: Path | None = None,
    ) -> None:
        """Initialize the protocol runtime and related helpers."""
        if definition_dir is None:
            # Path from jarvis/core/system.py to jarvis/protocols/defaults/definitions
            definition_dir = (
                Path(__file__).parent.parent / "protocols" / "defaults" / "definitions"
            )
        self.protocol_runtime = ProtocolRuntime(
            self.network, self.logger, usage_logger=self.usage_logger
        )
        self.protocol_runtime.initialize(load_protocol_directory, definition_dir)

    async def _start_network(self) -> None:
        await self.network.start()

    async def enter_night_mode(self) -> None:
        """Enable night mode and launch background tasks."""
        self.night_mode = True
        if self._orchestrator:
            self._orchestrator.night_mode = True
        for agent in self.night_agents:
            agent.activate_capabilities()
            asyncio.create_task(agent.start_background_tasks())

    async def exit_night_mode(self) -> None:
        """Disable night mode and stop background tasks."""
        self.night_mode = False
        if self._orchestrator:
            self._orchestrator.night_mode = False
        for agent in self.night_agents:
            agent.deactivate_capabilities()
            await agent.stop_background_tasks()

    async def process_request(
        self,
        user_input: str,
        tz_name: str,
        metadata: Dict[str, Any] | None = None,
        allowed_agents: set[str] | None = None,
    ) -> Dict[str, Any]:
        """Process a user request through the network via orchestrator.

        This method now delegates to RequestOrchestrator for clean separation of concerns.
        """
        if not self._orchestrator:
            raise RuntimeError("System not initialized - call initialize() first")

        # Sync night mode state with orchestrator
        if self._orchestrator.night_mode != self.night_mode:
            self._orchestrator.night_mode = self.night_mode

        # Handle method recording if enabled
        if self.network.method_recorder:
            self.network.start_method_recording(f"req_{uuid.uuid4()}", user_input)

        try:
            # Delegate to orchestrator
            return await self._orchestrator.process_request(
                user_input=user_input,
                tz_name=tz_name,
                metadata=metadata,
                allowed_agents=allowed_agents,
                perf_enabled=self.perf_enabled,
            )
        finally:
            # Stop recording
            self.network.stop_method_recording()

    def get_available_commands(
        self, allowed_agents: set[str] | None = None
    ) -> Dict[str, List[str]]:
        """Get all available voice trigger commands organized by protocol."""
        if not self.protocol_runtime:
            return {}
        return self.protocol_runtime.get_available_commands(allowed_agents)

    async def shutdown(self):
        """Shutdown the system and cleanup resources."""
        await self.network.stop()

        # Close services through agent refs
        if hasattr(self, "_agent_refs"):
            calendar_svc = self._agent_refs.get("calendar_service")
            if calendar_svc and hasattr(calendar_svc, "close"):
                await calendar_svc.close()

        # Close loggers
        if self._response_logger:
            await self._response_logger.close()
        if self.usage_logger:
            await self.usage_logger.close()
        if self.interaction_logger:
            await self.interaction_logger.close()

        self.logger.log("INFO", "Jarvis system shutdown complete")
        self.logger.close()
