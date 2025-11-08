# jarvis/main_network.py

import asyncio
from os import getenv
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..agents.agent_network import AgentNetwork
from ..agents.nlu_agent import NLUAgent
from ..agents.protocol_agent import ProtocolAgent
from ..agents.lights_agent.lighting_agent import LightingAgent
from ..agents.chat_agent import ChatAgent
from .profile import AgentProfile
from ..services.vector_memory import VectorMemoryService
from ..services.calendar_service import CalendarService
from ..services.canvas_service import CanvasService  # ← NEW
from ..night_agents import NightAgent, NightModeControllerAgent
from ..ai_clients import AIClientFactory, BaseAIClient
from ..logging import JarvisLogger
from .config import JarvisConfig
from .method_recorder import MethodRecorder
from ..protocols.loggers import ProtocolUsageLogger, InteractionLogger
from ..protocols.runtime import ProtocolRuntime
from ..utils.performance import PerfTracker, get_tracker
from ..agents.factory import AgentFactory


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

        # Placeholders for your agents
        self.nlu_agent: NLUAgent | None = None
        self.calendar_service: CalendarService | None = None
        self.canvas_service: CanvasService | None = None  # ← NEW
        self.lights_agent: LightingAgent | None = None
        self.chat_agent: ChatAgent | None = None
        self.protocol_agent: ProtocolAgent | None = None
        self.roku_agent = None  # Will be set during initialization
        self.vector_memory: VectorMemoryService | None = None
        self.user_profiles: dict[int, AgentProfile] = {}

        # Conversation history: user_id -> list of (user, assistant) turns
        self.conversation_history: Dict[int, List[Dict[str, str]]] = {}
        self.max_history_length = 10  # Keep last 10 turns

        # Night mode management
        self.night_mode: bool = False
        self.night_agents: list[NightAgent] = []
        self.night_controller: NightModeControllerAgent | None = None

        # Protocol runtime
        self.protocol_runtime: ProtocolRuntime | None = None
        self.protocol_registry = None  # backward compatibility
        self.voice_matcher = None  # backward compatibility
        self.usage_logger = ProtocolUsageLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name=getenv("MONGO_DB_NAME", "protocol"),
        )
        self.interaction_logger = InteractionLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name=getenv("MONGO_DB_NAME", "protocol"),
        )

    async def initialize(self, load_protocol_directory: bool = False) -> None:
        """Initialize all agents and start the network."""
        ai_client = self._create_ai_client()
        await self._connect_usage_logger()

        factory = AgentFactory(self.config, self.logger)
        refs = factory.build_all(self.network, ai_client, self)

        self.vector_memory = refs.get("vector_memory")
        self.nlu_agent = refs.get("nlu_agent")
        self.calendar_service = refs.get("calendar_service")
        self.chat_agent = refs.get("chat_agent")
        self.protocol_agent = refs.get("protocol_agent")
        self.lights_agent = refs.get("lights_agent")
        self.roku_agent = refs.get("roku_agent")
        self.canvas_service = refs.get("canvas_service")
        self.night_controller = refs.get("night_controller")
        self.night_agents = refs.get("night_agents", [])

        self._setup_protocol_system(load_protocol_directory)
        await self._start_network()

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

    async def _connect_usage_logger(self) -> None:
        await self.usage_logger.connect()

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
        self.protocol_registry = self.protocol_runtime.registry
        self.voice_matcher = self.protocol_runtime.voice_matcher

    async def _start_network(self) -> None:
        await self.network.start()

    async def enter_night_mode(self) -> None:
        """Enable night mode and launch background tasks."""
        self.night_mode = True
        for agent in self.night_agents:
            agent.activate_capabilities()
            asyncio.create_task(agent.start_background_tasks())

    async def exit_night_mode(self) -> None:
        """Disable night mode and stop background tasks."""
        self.night_mode = False
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
        """Process a user request through the network via voice trigger or NLU routing."""
        import time

        # Track interaction for logging
        start_time = time.time()
        # Default to 1 if not provided (from env or literal 1)
        default_user_id = int(getenv("DEFAULT_USER_ID", "1"))
        user_id = metadata.get("user_id") if metadata else default_user_id
        if user_id is None:
            user_id = default_user_id
        device = metadata.get("device") if metadata else None
        location = metadata.get("location") if metadata else None
        source = metadata.get("source") if metadata else None

        # Track intent and other details for logging
        captured_intent = None
        captured_capability = None
        captured_protocol = None
        captured_agent_results = None
        captured_tool_calls = None

        if self.network.method_recorder:
            self.network.start_method_recording(f"req_{uuid.uuid4()}", user_input)
        tracker = get_tracker()
        new_tracker = False
        if tracker is None:
            tracker = PerfTracker(enabled=self.perf_enabled)
            tracker.start()
            new_tracker = True
        if metadata:
            # Update user_id if it was provided in metadata (overwrites earlier extraction)
            if metadata.get("user_id") is not None:
                user_id = metadata.get("user_id")
            profile_data = metadata.get("profile")
            profile_obj = None
            if user_id is not None:
                if profile_data is not None:
                    profile_obj = AgentProfile(**profile_data)
                    self.user_profiles[user_id] = profile_obj
                else:
                    profile_obj = self.user_profiles.get(user_id)
                if profile_obj and self.chat_agent:
                    self.chat_agent.profile = profile_obj
                    self.chat_agent.current_user_id = user_id
        try:
            if not self.nlu_agent:
                raise RuntimeError("System not initialized")

            if self.night_mode:
                match_result = (
                    self.protocol_runtime.try_match(user_input)
                    if self.protocol_runtime
                    else None
                )
                if not match_result or match_result["protocol"].name != "wake_up":
                    maintenance_response = "Jarvis is in maintenance mode"
                    # Log interaction
                    latency_ms = (time.time() - start_time) * 1000
                    asyncio.create_task(
                        self.interaction_logger.log_interaction(
                            user_input=user_input,
                            response=maintenance_response,
                            intent="maintenance",
                            latency_ms=latency_ms,
                            success=False,
                            user_id=user_id,
                            device=device,
                            location=location,
                            source=source,
                        )
                    )
                    return {"response": maintenance_response}

            # 1) First check for protocol matches (fast path)
            match_result = (
                self.protocol_runtime.try_match(user_input)
                if self.protocol_runtime
                else None
            )

            if match_result:
                protocol = match_result["protocol"]
                arguments = match_result["arguments"]
                captured_protocol = protocol.name
                captured_intent = "protocol"

                self.logger.log(
                    "INFO",
                    "Trigger matched",
                    f"Command: '{user_input}' -> Protocol: '{protocol.name}', Args: {arguments}",
                )

                try:
                    async with tracker.timer(
                        "protocol_execution", metadata={"protocol": protocol.name}
                    ):
                        response = await self.protocol_runtime.run_and_format(
                            match_result,
                            trigger_phrase=user_input,
                            metadata=metadata,
                            allowed_agents=allowed_agents,
                        )

                    result_dict = {
                        "response": response,
                        "protocol_executed": protocol.name,
                        "execution_time": "fast",
                    }

                    # Log interaction
                    latency_ms = (time.time() - start_time) * 1000
                    if isinstance(response, dict):
                        response_text = response.get("response", str(response))
                    else:
                        response_text = str(response)
                    asyncio.create_task(
                        self.interaction_logger.log_interaction(
                            user_input=user_input,
                            response=response_text,
                            intent=captured_intent,
                            protocol_executed=captured_protocol,
                            latency_ms=latency_ms,
                            success=True,
                            user_id=user_id,
                            device=device,
                            location=location,
                            source=source,
                        )
                    )

                    return result_dict
                except Exception as e:
                    self.logger.log(
                        "ERROR",
                        f"Protocol execution failed for '{protocol.name}'",
                        str(e),
                    )
                    # Log failed protocol execution
                    latency_ms = (time.time() - start_time) * 1000
                    error_response = f"Protocol execution failed: {str(e)}"
                    asyncio.create_task(
                        self.interaction_logger.log_interaction(
                            user_input=user_input,
                            response=error_response,
                            intent=captured_intent,
                            protocol_executed=captured_protocol,
                            latency_ms=latency_ms,
                            success=False,
                            user_id=user_id,
                            device=device,
                            location=location,
                            source=source,
                        )
                    )
                    # Fall through to NLU on error

            # 2) No protocol match or protocol failed - use NLU agent for routing
            request_id = str(uuid.uuid4())

            # Get user_id and conversation history
            # Use the user_id we already extracted (with default fallback)
            conversation_history = self.conversation_history.get(user_id, [])

            self.logger.log(
                "DEBUG",
                f"Retrieved conversation history for user {user_id}",
                f"{len(conversation_history)} turns",
            )

            # Use "JarvisSystem" as the from_agent so NLU knows we're the original requester
            await self.network.request_capability(
                from_agent="JarvisSystem",
                capability="intent_matching",
                data={
                    "input": user_input,
                    "conversation_history": conversation_history,
                },
                request_id=request_id,
                allowed_agents=allowed_agents if allowed_agents else None,
            )

            try:
                # NLU now handles routing directly and will respond when complete
                self.logger.log(
                    "INFO",
                    f"[SYSTEM] About to call wait_for_response",
                    f"request_id={request_id}, timeout={self.config.response_timeout}",
                )
                async with tracker.timer("nlu_routing"):
                    result = await self.network.wait_for_response(
                        request_id, timeout=self.config.response_timeout
                    )
                
                self.logger.log(
                    "INFO",
                    f"[SYSTEM] Received result from wait_for_response",
                    f"request_id={request_id}, result_type={type(result).__name__}, result_keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}",
                )

                # Result should have "response" key from NLU's formatted response
                response_text = None
                self.logger.log(
                    "INFO",
                    f"[SYSTEM] Processing result dict",
                    f"request_id={request_id}, result_is_dict={isinstance(result, dict)}, has_response_key={'response' in result if isinstance(result, dict) else False}",
                )
                if isinstance(result, dict):
                    if "response" in result:
                        response_text = result["response"]
                        self.logger.log(
                            "INFO",
                            f"[SYSTEM] Extracted response text",
                            f"request_id={request_id}, response_length={len(response_text) if response_text else 0}, response_preview={response_text[:100] if response_text else 'None'}",
                        )
                        response_dict = {"response": response_text}
                        # Extract additional information for logging
                        if "results" in result:
                            captured_agent_results = result["results"]
                            # Try to extract intent and capability from agent results
                            if captured_agent_results:
                                first_result = None
                                if isinstance(captured_agent_results, list):
                                    first_result = captured_agent_results[0]
                                if first_result and isinstance(first_result, dict):
                                    captured_capability = first_result.get(
                                        "capability"
                                    )
                                    if not captured_intent:
                                        intent_default = (
                                            "perform_capability"
                                            if captured_capability
                                            else "chat"
                                        )
                                        captured_intent = first_result.get(
                                            "intent", intent_default
                                        )
                        if "intent" in result:
                            captured_intent = result["intent"]
                        if "capability" in result:
                            captured_capability = result["capability"]
                    else:
                        # Fallback for old format
                        response_dict = result
                        response_text = str(result)
                else:
                    response_text = str(result)
                    response_dict = {"response": response_text}

                # Default intent if not captured
                if not captured_intent:
                    captured_intent = "chat"

                # Store conversation history
                if response_text:
                    if user_id not in self.conversation_history:
                        self.conversation_history[user_id] = []
                    history = self.conversation_history[user_id]
                    history.append({"user": user_input, "assistant": response_text})
                    # Keep only last N turns
                    if len(history) > self.max_history_length:
                        self.conversation_history[user_id] = history[
                            -self.max_history_length :
                        ]
                    self.logger.log(
                        "DEBUG",
                        f"Stored conversation turn for user {user_id}",
                        f"History now has {len(self.conversation_history[user_id])} turns",
                    )

                # Log interaction
                latency_ms = (time.time() - start_time) * 1000
                asyncio.create_task(
                    self.interaction_logger.log_interaction(
                        user_input=user_input,
                        response=response_text or "",
                        intent=captured_intent,
                        capability=captured_capability,
                        agent_results=captured_agent_results,
                        tool_calls=captured_tool_calls,
                        latency_ms=latency_ms,
                        success=True,
                        user_id=user_id,
                        device=device,
                        location=location,
                        source=source,
                    )
                )

                return response_dict

            except asyncio.TimeoutError:
                self.logger.log(
                    "ERROR",
                    "NLU routing timed out",
                    f"request_id={request_id}",
                )
                error_response = (
                    "The request took too long to complete. Please try again."
                )
                # Log failed interaction
                latency_ms = (time.time() - start_time) * 1000
                asyncio.create_task(
                    self.interaction_logger.log_interaction(
                        user_input=user_input,
                        response=error_response,
                        intent=captured_intent or "timeout",
                        latency_ms=latency_ms,
                        success=False,
                        user_id=user_id,
                        device=device,
                        location=location,
                        source=source,
                    )
                )
                return {"response": error_response}
            except Exception as e:
                self.logger.log("ERROR", "Error in NLU routing", str(e))
                error_response = f"Sorry, I encountered an error: {str(e)}"
                # Log failed interaction
                latency_ms = (time.time() - start_time) * 1000
                asyncio.create_task(
                    self.interaction_logger.log_interaction(
                        user_input=user_input,
                        response=error_response,
                        intent=captured_intent or "error",
                        latency_ms=latency_ms,
                        success=False,
                        user_id=user_id,
                        device=device,
                        location=location,
                        source=source,
                    )
                )
                return {"response": error_response}
        finally:
            self.network.stop_method_recording()
            if new_tracker:
                tracker.stop()
                tracker.save()
                self.logger.log("INFO", "Performance summary", tracker.summary())

    def get_available_commands(
        self, allowed_agents: set[str] | None = None
    ) -> Dict[str, List[str]]:
        """Get all available voice trigger commands organized by protocol."""
        if not self.protocol_runtime:
            return {}
        return self.protocol_runtime.get_available_commands(allowed_agents)

    async def shutdown(self):
        """Shutdown the system"""
        await self.network.stop()
        if self.calendar_service:
            await self.calendar_service.close()
        if self.usage_logger:
            await self.usage_logger.close()
        self.logger.log("INFO", "Jarvis system shutdown complete")
        self.logger.close()
