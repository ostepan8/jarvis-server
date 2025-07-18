# jarvis/main_network.py

import asyncio
import json
import os
from os import getenv
import uuid
import random
from typing import Any, Dict, List, Optional
from pathlib import Path

from dotenv import load_dotenv

from .agents.agent_network import AgentNetwork
from .agents.nlu_agent import NLUAgent
from .agents.protocol_agent import ProtocolAgent
from .agents.lights_agent import PhillipsHueAgent
from .agents.software_engineering_agent import SoftwareEngineeringAgent
from .agents.calendar_agent.agent import CollaborativeCalendarAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .agents.weather_agent import WeatherAgent
from .agents.memory_agent import MemoryAgent
from .agents.chat_agent import ChatAgent
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
from .agents.message import Message
from .protocols.registry import ProtocolRegistry
from .protocols.executor import ProtocolExecutor
from .protocols.loggers import ProtocolUsageLogger
from .protocols.voice_trigger import VoiceTriggerMatcher
from .protocols.models import Protocol, ResponseMode
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
        self.software_agent: SoftwareEngineeringAgent | None = None
        self.vector_memory: VectorMemoryService | None = None

        # Night mode management
        self.night_mode: bool = False
        self.night_agents: list[NightAgent] = []
        self.night_controller: NightModeControllerAgent | None = None

        # Protocol system components
        self.protocol_registry = ProtocolRegistry()
        self.protocol_executor = None  # Will be initialized after network is ready
        self.voice_matcher = None  # Will be initialized after protocols are loaded
        self.usage_logger = ProtocolUsageLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name="protocals",
        )

    async def initialize(self, load_protocol_directory: bool = False) -> None:
        """Initialize all agents and start the network."""
        ai_client = self._create_ai_client()
        await self._connect_usage_logger()
        self._register_agents(ai_client)
        self._setup_protocol_system(load_protocol_directory)
        await self._start_network()

        self.logger.log(
            "INFO",
            "Jarvis system initialized",
            f"Active agents: {list(self.network.agents.keys())}, "
            f"Loaded protocols: {len(self.protocol_registry.protocols)}",
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

        # Shared memory service provided via MemoryAgent
        self.vector_memory = VectorMemoryService(
            persist_directory=self.config.memory_dir,
            api_key=self.config.api_key,
        )
        self.memory_agent = MemoryAgent(self.vector_memory, self.logger, ai_client)
        self.network.register_agent(self.memory_agent)

        # 1) NLUAgent (must be registered so network.request_capability works)
        self.nlu_agent = NLUAgent(ai_client, self.logger)
        self.network.register_agent(self.nlu_agent)

        # 2) OrchestratorAgent (dynamic multi-step planning)
        timeout = self.config.response_timeout
        self.orchestrator = OrchestratorAgent(
            ai_client, self.logger, response_timeout=timeout
        )
        self.network.register_agent(self.orchestrator)

        # 3) CollaborativeCalendarAgent (your existing Calendar API)
        self.calendar_service = CalendarService(self.config.calendar_api_url)
        calendar_agent = CollaborativeCalendarAgent(
            ai_client, self.calendar_service, self.logger
        )
        self.network.register_agent(calendar_agent)

        # 4) CanvasAgent (Canvas LMS integration)               ← ADDED
        #    Reads CANVAS_API_URL and CANVAS_API_TOKEN env-vars by default
        # self.canvas_service = CanvasService()
        # canvas_agent = CanvasAgent(ai_client, self.canvas_service, self.logger)
        # self.network.register_agent(canvas_agent)
        # canvas_agent.memory = self.vector_memory

        # 5) ChatAgent (chat interactions)
        self.chat_agent = ChatAgent(ai_client, self.logger)
        self.network.register_agent(self.chat_agent)

        # 6) WeatherAgent (for weather info)
        weather_key = os.getenv("WEATHER_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
        try:
            self.weather_agent = WeatherAgent(
                api_key=weather_key, logger=self.logger, ai_client=ai_client
            )
            self.network.register_agent(self.weather_agent)
        except Exception as exc:
            self.logger.log("WARNING", "WeatherAgent init failed", str(exc))

        # 7) ProtocolAgent (for protocol management)
        self.protocol_agent = ProtocolAgent(self.logger)
        self.network.register_agent(self.protocol_agent)

        # 8) LightsAgent (for smart home control)
        load_dotenv()
        bridge_ip = os.getenv("HUE_BRIDGE_IP")
        self.lights_agent = PhillipsHueAgent(ai_client=ai_client, bridge_ip=bridge_ip)
        self.network.register_agent(self.lights_agent)

        # 9) SoftwareEngineeringAgent (developer tools)
        repo_path = self.config.repo_path
        self.software_agent = SoftwareEngineeringAgent(
            ai_client=ai_client, repo_path=repo_path, logger=self.logger
        )
        self.network.register_agent(self.software_agent)

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

    def _setup_protocol_system(self, load_protocol_directory) -> None:
        """Initialize protocol executor and load protocol definitions."""
        self.protocol_executor = ProtocolExecutor(
            self.network, self.logger, usage_logger=self.usage_logger
        )

        protocols_dir = Path(__file__).parent / "protocols" / "defaults" / "definitions"
        if protocols_dir.exists():
            self._load_protocols_from_directory(protocols_dir)

        self.voice_matcher = VoiceTriggerMatcher(self.protocol_registry.protocols)

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

    def _load_protocols_from_directory(self, directory: Path):
        """Load all protocol definitions from JSON files in the directory"""
        for json_file in directory.glob("*.json"):
            try:
                protocol = Protocol.from_file(json_file)
                result = self.protocol_registry.register(protocol)
                if result.get("success") is True:
                    self.logger.log(
                        "INFO",
                        f"Loaded protocol: {protocol.name}",
                        f"Triggers: {protocol.trigger_phrases}",
                    )
                elif result.get("success") is False:
                    self.logger.log(
                        "WARNING",
                        f"Failed to register protocol: {protocol.name}.",
                        result,
                    )
            except Exception as e:
                self.logger.log(
                    "ERROR", f"Failed to load protocol from {json_file}", str(e)
                )

    async def process_request(
        self,
        user_input: str,
        tz_name: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Process a user request through the network via voice trigger or NLU routing."""
        tracker = get_tracker()
        new_tracker = False
        if tracker is None:
            tracker = PerfTracker(enabled=self.perf_enabled)
            tracker.start()
            new_tracker = True
        try:
            if not self.nlu_agent:
                raise RuntimeError("System not initialized")

            if self.night_mode:
                if self.voice_matcher:
                    match_result = self.voice_matcher.match_command(user_input)
                if not match_result or match_result["protocol"].name != "wake_up":
                    return {"response": "Jarvis is in maintenance mode"}

            # 1) First check for protocol matches (fast path)
            match_result = None
            if self.voice_matcher:
                match_result = self.voice_matcher.match_command(user_input)

            if not match_result:
                # Fallback to registry for simple matching
                matched_protocol = self.protocol_registry.find_matching_protocol(
                    user_input
                )
                if matched_protocol:
                    match_result = {
                        "protocol": matched_protocol,
                        "arguments": {},
                        "matched_phrase": user_input,
                    }

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
                        "protocol_execution",
                        metadata={"protocol": protocol.name},
                    ):
                        results = await self.protocol_executor.run_protocol_with_match(
                            match_result,
                            trigger_phrase=user_input,
                            metadata=metadata,
                        )

                    response = await self._format_protocol_response(
                        protocol, results, arguments
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
                )

                classification = await self.network.wait_for_response(request_id)
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
            args = classification.get("args", {})

            self.logger.log(
                "INFO",
                "Routing after NLU",
                f"intent={intent}, target={target}, cap={cap}, proto={proto}, args={args}",
            )

            # 4) Route to the appropriate agent
            if intent == "perform_capability" and cap:
                request_id = str(uuid.uuid4())
                payload = {"prompt": user_input}
                if args:
                    payload.update(args)
                if cap == "store_memory":
                    cmd = args.get("memory_data", user_input)
                    meta = (
                        {"type": args.get("memory_type")}
                        if args.get("memory_type")
                        else {}
                    )
                    payload = {"prompt": cmd, "metadata": meta}
                async with tracker.timer(
                    "agent_response", metadata={"agent": target or cap}
                ):
                    providers = await self.network.request_capability(
                        from_agent=None,
                        capability=cap,
                        data=payload,
                        request_id=request_id,
                    )
                    self.logger.log(
                        "DEBUG", f"Requested '{cap}' from {providers}", payload
                    )
                    result = await self.network.wait_for_response(request_id)
                return {"response": result}

            if intent == "orchestrate_tasks":
                async with tracker.timer(
                    "agent_response", metadata={"agent": "orchestrator"}
                ):
                    return await self.orchestrator.process_user_request(
                        user_input, tz_name
                    )

            if intent == "run_protocol":
                run_id = str(uuid.uuid4())
                async with tracker.timer(
                    "protocol_execution", metadata={"protocol": proto}
                ):
                    await self.network.request_capability(
                        from_agent=self.nlu_agent.name,
                        capability="run_protocol",
                        data={"protocol_name": proto, "args": args},
                        request_id=run_id,
                    )
                    result = await self.network.wait_for_response(run_id)
                return {"response": result}

            if intent == "define_protocol":
                define_id = str(uuid.uuid4())
                async with tracker.timer(
                    "agent_response", metadata={"agent": "nlu_define"}
                ):
                    await self.network.request_capability(
                        from_agent=self.nlu_agent.name,
                        capability="define_protocol",
                        data=args,
                        request_id=define_id,
                    )
                    result = await self.network.wait_for_response(define_id)
                return {"response": result}

            if intent == "ask_about_protocol":
                desc_id = str(uuid.uuid4())
                async with tracker.timer(
                    "agent_response", metadata={"agent": "nlu_describe"}
                ):
                    await self.network.request_capability(
                        from_agent=self.nlu_agent.name,
                        capability="describe_protocol",
                        data={"protocol_name": proto},
                        request_id=desc_id,
                    )
                    result = await self.network.wait_for_response(desc_id)
                return {"response": result}

            if intent == "chat":
                define_id = str(uuid.uuid4())
                payload = {"prompt": user_input}
                async with tracker.timer(
                    "agent_response", metadata={"agent": target or "chat"}
                ):
                    await self.network.request_capability(
                        from_agent=None,
                        capability=cap,
                        data=payload,
                        request_id=define_id,
                    )
                    result = await self.network.wait_for_response(define_id)

                return {"response": result}

            # fallback
            return {"response": "Sorry, I didn't understand that."}
        finally:
            if new_tracker:
                tracker.stop()
                tracker.save()
                self.logger.log("INFO", "Performance summary", tracker.summary())

    async def _format_protocol_response(
        self,
        protocol: Protocol,
        results: Dict[str, Any],
        arguments: Dict[str, Any] | None = None,
    ) -> str:
        """Format protocol execution results in Jarvis style"""
        # Check if any step had an error
        errors = []
        successes = []

        for step_id, result in results.items():
            if isinstance(result, dict) and "error" in result:
                errors.append(result["error"])
            else:
                successes.append(step_id)

        if errors:
            return f"I encountered some issues executing that command, sir. {'. '.join(errors)}"

        response_cfg = protocol.response
        print(protocol, "RESPONSE CFG")
        print(results, "RESULTS")

        # Default fallback
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
            # Build comprehensive prompt with protocol and result context
            base_prompt = response_cfg.prompt or ""

            # Get current time for context
            from datetime import datetime

            current_time = datetime.now().strftime("%I:%M %p")  # 12-hour format
            current_date = datetime.now().strftime("%Y-%m-%d")

            # Create structured context for the AI
            context_prompt = f"""You are Jarvis, Tony Stark's AI assistant. Your job is to communicate ONLY the actual results and information from the protocol execution to the user. Do not mention that data was "retrieved" or "fetched" - just communicate the actual content/results directly.

    Protocol Data:
    - Current Time: {current_time}
    - Current Date: {current_date}
    - Results: {json.dumps(results, indent=2)}
    - User Arguments: {json.dumps(arguments or {}, indent=2)}

    Instructions: {base_prompt}

    IMPORTANT RULES:
    1. Do NOT say things like "retrieved", "fetched", "successfully obtained", "data shows", etc.
    2. Communicate the ACTUAL information/results directly to the user
    3. Use Jarvis's polite, butler-like tone with "sir"
    4. Focus on what the user actually needs to know from the results
    5. Use 12-hour time format only
    6. If there's no meaningful data to report, say so directly (e.g., "You have nothing scheduled today, sir")"""

            # Replace argument placeholders in the base prompt
            if arguments:
                for k, v in arguments.items():
                    context_prompt = context_prompt.replace(f"{{{k}}}", str(v))
                    base_prompt = base_prompt.replace(f"{{{k}}}", str(v))

            print("Full AI Prompt:", context_prompt)

            if self.chat_agent is None:
                return base_prompt

            message, _ = await self.chat_agent.ai_client.weak_chat(
                [{"role": "user", "content": context_prompt}],
                [],
            )
            return message.content

        return ""

    def _format_calendar_response(self, results: Dict[str, Any]) -> str:
        """Format calendar-specific responses"""
        print(results, "RESULTS")
        # Extract calendar data from results
        for step_id, result in results.items():
            if isinstance(result, dict) and "response" in result:
                return result["response"]
        return "Calendar information retrieved, sir."

    def get_available_commands(self) -> Dict[str, List[str]]:
        """Get all available voice trigger commands organized by protocol"""
        if not self.voice_matcher:
            return {}

        commands = {}
        for protocol in self.protocol_registry.protocols.values():
            commands[protocol.name] = protocol.trigger_phrases

        return commands

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
    result = await jarvis.process_request(user_input, get_localzone_name(), {})
    print(f"Jarvis: {result['response']}")
    if "protocol_executed" in result:
        print(f"(Executed via protocol: {result['protocol_executed']})")

    print("\n=== Testing NLU Routing ===")
    user_input = "What's on my calendar tomorrow?"
    print(f"User: {user_input}")
    result = await jarvis.process_request(user_input, get_localzone_name(), {})
    print(f"Jarvis: {result['response']}")

    print("\n=== Available Voice Commands ===")
    commands = jarvis.get_available_commands()
    for protocol, triggers in commands.items():
        print(f"{protocol}: {', '.join(triggers)}")

    await jarvis.shutdown()


async def create_collaborative_jarvis(
    api_key: Optional[str] = None, repo_path: str = "."
) -> JarvisSystem:
    """
    Create and initialize a JarvisSystem instance with default configuration.

    Args:
        api_key (Optional[str]): API key for the AI provider. If not provided, it will be loaded from environment variables.
        repo_path (str): Path to the local repository used by the SoftwareEngineeringAgent.

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
    )

    jarvis = JarvisSystem(config)
    await jarvis.initialize()
    return jarvis


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo())
