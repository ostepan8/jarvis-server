# jarvis/main_network.py

import asyncio
import os
from os import getenv
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

from dotenv import load_dotenv

from .agents.agent_network import AgentNetwork
from .agents.nlu_agent import NLUAgent
from .agents.protocol_agent import ProtocolAgent
from .agents.lights_agent import PhillipsHueAgent

# from .agents.software_engineering_agent import SoftwareEngineeringAgent
from .agents.calendar_agent.agent import CollaborativeCalendarAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .agents.weather_agent import WeatherAgent
from .agents.memory_agent import MemoryAgent
from .agents.chat_agent import ChatAgent
from .profile import AgentProfile
from .services.vector_memory import VectorMemoryService
from .services.calendar_service import CalendarService
from .services.canvas_service import CanvasService  # ← NEW
from .agents.canvas import CanvasAgent
from .night_agents import (
    NightAgent,
    TriggerPhraseSuggesterAgent,
    NightModeControllerAgent,
)
from .ai_clients import AIClientFactory, BaseAIClient
from .logger import JarvisLogger
from .config import JarvisConfig
from .protocols.loggers import ProtocolUsageLogger
from .protocols.runtime import ProtocolRuntime
from .performance import PerfTracker, get_tracker


class JarvisSystem:
    """Main Jarvis system that manages the agent network."""

    def __init__(self, config: JarvisConfig | Dict[str, Any]):
        """Create a new Jarvis system."""
        if isinstance(config, dict):
            self.config = JarvisConfig(**config)
        else:
            self.config = config

        self.logger = JarvisLogger()
        self.network = AgentNetwork(self.logger)
        self.perf_enabled = self.config.perf_tracking
        self._tracker: PerfTracker | None = None

        # Placeholders for your agents
        self.nlu_agent: NLUAgent = None
        self.orchestrator: OrchestratorAgent = None
        self.calendar_service: CalendarService = None
        self.canvas_service: CanvasService = None  # ← NEW
        self.lights_agent: PhillipsHueAgent = None
        self.chat_agent: ChatAgent | None = None
        self.protocol_agent: ProtocolAgent | None = None
        # self.software_agent: SoftwareEngineeringAgent | None = None
        self.vector_memory: VectorMemoryService | None = None
        self.user_profiles: dict[int, AgentProfile] = {}

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
            db_name="protocals",
        )

    async def initialize(self, load_protocol_directory: bool = False) -> None:
        """Initialize all agents and start the network."""
        ai_client = self._create_ai_client()
        await self._connect_usage_logger()
        self._register_agents(ai_client)
        self.protocol_runtime = ProtocolRuntime(
            self.network, self.logger, usage_logger=self.usage_logger
        )
        self.protocol_runtime.initialize(
            load_protocol_directory,
            Path(__file__).parent / "protocols" / "defaults" / "definitions",
        )
        self.protocol_registry = self.protocol_runtime.registry
        self.voice_matcher = self.protocol_runtime.voice_matcher
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

    def _register_agents(self, ai_client: BaseAIClient) -> None:
        """Create and register all agents with the network."""
        self._create_memory_agent(ai_client)
        self._create_nlu_agent(ai_client)
        self._create_orchestrator(ai_client)
        self._create_calendar_agent(ai_client)
        self._create_chat_agent(ai_client)
        self._create_weather_agent(ai_client)
        self._create_protocol_agent()
        self._create_lights_agent(ai_client)
        self._create_software_agent(ai_client)
        self._create_night_agents()

    # Factory helpers
    def _create_memory_agent(self, ai_client: BaseAIClient) -> None:
        self.vector_memory = VectorMemoryService(
            persist_directory=self.config.memory_dir,
            api_key=self.config.api_key,
        )
        self.memory_agent = MemoryAgent(self.vector_memory, self.logger, ai_client)
        self.network.register_agent(self.memory_agent)

    def _create_nlu_agent(self, ai_client: BaseAIClient) -> None:
        self.nlu_agent = NLUAgent(ai_client, self.logger)
        self.network.register_agent(self.nlu_agent)

    def _create_orchestrator(self, ai_client: BaseAIClient) -> None:
        timeout = self.config.response_timeout
        self.orchestrator = OrchestratorAgent(
            ai_client, self.logger, response_timeout=timeout
        )
        self.network.register_agent(self.orchestrator)

    def _create_calendar_agent(self, ai_client: BaseAIClient) -> None:
        self.calendar_service = CalendarService(self.config.calendar_api_url)
        calendar_agent = CollaborativeCalendarAgent(
            ai_client, self.calendar_service, self.logger
        )
        self.network.register_agent(calendar_agent)

    def _create_chat_agent(self, ai_client: BaseAIClient) -> None:
        self.chat_agent = ChatAgent(ai_client, self.logger)
        self.network.register_agent(self.chat_agent)

    def _create_weather_agent(self, ai_client: BaseAIClient) -> None:
        weather_key = (
            self.config.weather_api_key
            or os.getenv("WEATHER_API_KEY")
            or os.getenv("OPENWEATHER_API_KEY")
        )
        try:
            self.weather_agent = WeatherAgent(
                api_key=weather_key, logger=self.logger, ai_client=ai_client
            )
            self.network.register_agent(self.weather_agent)
        except Exception as exc:
            self.logger.log("WARNING", "WeatherAgent init failed", str(exc))

    def _create_protocol_agent(self) -> None:
        self.protocol_agent = ProtocolAgent(self.logger)
        self.network.register_agent(self.protocol_agent)

    def _create_lights_agent(self, ai_client: BaseAIClient) -> None:
        load_dotenv()
        bridge_ip = self.config.hue_bridge_ip or os.getenv("HUE_BRIDGE_IP")
        self.lights_agent = PhillipsHueAgent(
            ai_client=ai_client,
            bridge_ip=bridge_ip,
            username=self.config.hue_username,
        )
        self.network.register_agent(self.lights_agent)

    def _create_software_agent(self, ai_client: BaseAIClient) -> None:
        repo_path = self.config.repo_path
        # self.software_agent = SoftwareEngineeringAgent(
        #     ai_client=ai_client, repo_path=repo_path, logger=self.logger
        # )
        # self.network.register_agent(self.software_agent)

    def _create_night_agents(self) -> None:
        self.night_controller = NightModeControllerAgent(self, self.logger)
        self.network.register_agent(self.night_controller)

        trigger_agent = TriggerPhraseSuggesterAgent(logger=self.logger)
        self.network.register_night_agent(trigger_agent)
        self.night_agents.append(trigger_agent)

        # Night mode controller
        self.night_controller = NightModeControllerAgent(self, self.logger)
        self.network.register_agent(self.night_controller)

        # Night agents
        trigger_agent = TriggerPhraseSuggesterAgent(logger=self.logger)
        self.network.register_night_agent(trigger_agent)
        self.night_agents.append(trigger_agent)

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
        tracker = get_tracker()
        new_tracker = False
        if tracker is None:
            tracker = PerfTracker(enabled=self.perf_enabled)
            tracker.start()
            new_tracker = True
        if metadata:
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
                    return {"response": "Jarvis is in maintenance mode"}

            # 1) First check for protocol matches (fast path)
            match_result = (
                self.protocol_runtime.try_match(user_input)
                if self.protocol_runtime
                else None
            )

            if match_result:
                protocol = match_result["protocol"]
                arguments = match_result["arguments"]

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

                    return {
                        "response": response,
                        "protocol_executed": protocol.name,
                        "execution_time": "fast",
                    }
                except Exception as e:
                    self.logger.log(
                        "ERROR",
                        f"Protocol execution failed for '{protocol.name}'",
                        str(e),
                    )
                    # Fall through to NLU on error

            # 2) No protocol match or protocol failed - use NLU agent
            request_id = str(uuid.uuid4())
            async with tracker.timer("nlu_classification"):
                await self.network.request_capability(
                    from_agent=self.nlu_agent.name,
                    capability="intent_matching",
                    data={"input": user_input},
                    request_id=request_id,
                    allowed_agents=allowed_agents,
                )

                try:
                    classification = await self.network.wait_for_response(
                        request_id, timeout=self.config.intent_timeout
                    )
                except asyncio.TimeoutError:
                    self.logger.log(
                        "ERROR",
                        "NLU classification timed out",
                        f"request_id={request_id}",
                    )
                    return {
                        "response": "The request took too long to complete. Please try again.",
                    }
            if not isinstance(classification, dict) or "intent" not in classification:
                self.logger.log("ERROR", "Error from NLUAgent", str(classification))
                return {
                    "response": "Sorry sir, It appears I had trouble understanding that. Error: "
                    + str(classification)
                }
            intent = classification["intent"]
            target = classification["target_agent"]
            proto = classification.get("protocol_name")
            cap = classification.get("capability")

            self.logger.log(
                "INFO",
                "Routing after NLU",
                f"intent={intent}, target={target}, cap={cap}, proto={proto}",
            )

            # 4) Route to the appropriate agent
            if intent == "perform_capability" and cap:
                request_id = str(uuid.uuid4())
                payload = {"prompt": user_input}
                async with tracker.timer(
                    "agent_response", metadata={"agent": target or cap}
                ):
                    providers = await self.network.request_capability(
                        from_agent=None,
                        capability=cap,
                        data=payload,
                        request_id=request_id,
                        allowed_agents=allowed_agents,
                    )
                    self.logger.log(
                        "DEBUG", f"Requested '{cap}' from {providers}", payload
                    )
                    if not providers:
                        self.logger.log(
                            "WARNING",
                            "No providers found for requested capability",
                            cap,
                        )
                        return {
                            "response": "No agent is available to handle that request."
                        }

                    result = await self.network.wait_for_response(
                        request_id, timeout=self.config.response_timeout
                    )

                return result

            if intent == "orchestrate_tasks":
                async with tracker.timer(
                    "agent_response", metadata={"agent": "orchestrator"}
                ):
                    return await self.orchestrator.process_user_request(
                        user_input, tz_name
                    )

            return {"response": "Sorry, I didn't understand that."}
        finally:
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
        return self.protocol_runtime.get_available_commands(
            allowed_agents
        )

    async def shutdown(self):
        """Shutdown the system"""
        await self.network.stop()
        if self.calendar_service:
            await self.calendar_service.close()
        if self.usage_logger:
            await self.usage_logger.close()
        self.logger.log("INFO", "Jarvis system shutdown complete")
        self.logger.close()


# Example usage and demo
async def demo():
    load_dotenv()
    config = {
        "ai_provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "calendar_api_url": "http://localhost:8080",
    }

    jarvis = JarvisSystem(config)
    await jarvis.initialize()

    from tzlocal import get_localzone_name

    # Demo voice trigger
    print("\n=== Testing Voice Trigger ===")
    user_input = "blue lights"
    print(f"User: {user_input}")
    result = await jarvis.process_request(
        user_input, get_localzone_name(), {}, allowed_agents=None
    )
    print(f"Jarvis: {result['response']}")
    if "protocol_executed" in result:
        print(f"(Executed via protocol: {result['protocol_executed']})")

    print("\n=== Testing NLU Routing ===")
    user_input = "What's on my calendar tomorrow?"
    print(f"User: {user_input}")
    result = await jarvis.process_request(
        user_input, get_localzone_name(), {}, allowed_agents=None
    )
    print(f"Jarvis: {result['response']}")

    print("\n=== Available Voice Commands ===")
    commands = jarvis.get_available_commands()
    for protocol, triggers in commands.items():
        print(f"{protocol}: {', '.join(triggers)}")

    await jarvis.shutdown()


async def create_collaborative_jarvis(
    api_key: Optional[str] = None,
    repo_path: str = ".",
    intent_timeout: float = 5.0,
) -> JarvisSystem:
    """
    Create and initialize a JarvisSystem instance with default configuration.

    Args:
        api_key (Optional[str]): API key for the AI provider. If not provided, it will be loaded from environment variables.
        repo_path (str): Path to the local repository used by the SoftwareEngineeringAgent.
        intent_timeout (float): Seconds to wait for the NLU classification step before timing out.

    Returns:
        JarvisSystem: A fully initialized Jarvis system instance.
    """
    load_dotenv()
    api_key = api_key or os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "Missing API key for AI provider. Set OPENAI_API_KEY in your environment."
        )

    config = JarvisConfig(
        ai_provider="openai",
        api_key=api_key,
        calendar_api_url="http://localhost:8080",
        response_timeout=60.0,
        repo_path=repo_path,
        intent_timeout=intent_timeout,
    )

    jarvis = JarvisSystem(config)
    await jarvis.initialize()
    return jarvis


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo())
