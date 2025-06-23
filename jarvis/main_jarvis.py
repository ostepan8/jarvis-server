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
from .agents.software_engineering_agent import SoftwareEngineeringAgent
from .agents.calendar_agent import CollaborativeCalendarAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .services.calendar_service import CalendarService
from .agents.chat_agent import ChatAgent
from .ai_clients import AIClientFactory, BaseAIClient
from .logger import JarvisLogger
from .config import JarvisConfig
from .agents.message import Message
from .protocols.registry import ProtocolRegistry
from .protocols.executor import ProtocolExecutor
from .protocols.loggers import ProtocolUsageLogger
from .protocols.voice_trigger import VoiceTriggerMatcher
from .protocols import Protocol

# Pre-defined phrases used when summarizing protocol execution results.
PROTOCOL_RESPONSES: Dict[str, str] = {
    "blue_lights_on": "Blue lights activated, sir.",
    "blue_lights_off": "Blue lights deactivated, sir.",
    "red_alert": "Red alert mode engaged. All systems on high alert, sir.",
    "all_lights_off": "All lights have been turned off, sir.",
    "dim_lights": "Lights dimmed to comfortable levels, sir.",
    "bright_lights": "Lights set to maximum brightness, sir.",
    "morning_routine": "Good morning, sir. Your morning routine has been initiated.",
    "goodnight": "Goodnight, sir. Sleep mode activated.",
}


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

        # Placeholders for your agents
        self.nlu_agent: NLUAgent = None
        self.orchestrator: OrchestratorAgent = None
        self.calendar_service: CalendarService = None
        self.lights_agent: PhillipsHueAgent = None
        self.chat_agent: ChatAgent | None = None
        self.protocol_agent: ProtocolAgent | None = None
        self.software_agent: SoftwareEngineeringAgent | None = None

        # Protocol system components
        self.protocol_registry = ProtocolRegistry()
        self.protocol_executor = None  # Will be initialized after network is ready
        self.voice_matcher = None  # Will be initialized after protocols are loaded
        self.usage_logger = ProtocolUsageLogger(
            mongo_uri=getenv("MONGO_URI", "mongodb://localhost:27017/"),
            db_name="protocals",
        )

    async def initialize(self) -> None:
        """Initialize all agents and start the network."""

        ai_client = self._create_ai_client()
        await self._connect_usage_logger()
        self._register_agents(ai_client)
        self._setup_protocol_system()
        await self._start_network()

        self.logger.log(
            "INFO",
            "Jarvis system initialized",
            f"Active agents: {list(self.network.agents.keys())}, Loaded protocols: {len(self.protocol_registry.protocols)}",
        )

    def _create_ai_client(self) -> BaseAIClient:
        """Instantiate the configured AI client."""
        return AIClientFactory.create(self.config.ai_provider, api_key=self.config.api_key)

    async def _connect_usage_logger(self) -> None:
        await self.usage_logger.connect()

    def _register_agents(self, ai_client: BaseAIClient) -> None:
        """Create and register all agents with the network."""

        # 1) NLUAgent (must be registered so network.request_capability works)
        self.nlu_agent = NLUAgent(ai_client, self.logger)
        self.network.register_agent(self.nlu_agent)

        # 2) OrchestratorAgent (dynamic multi-step planning)
        timeout = self.config.response_timeout
        self.orchestrator = OrchestratorAgent(ai_client, self.logger, response_timeout=timeout)
        self.network.register_agent(self.orchestrator)

        # 3) CalendarAgent
        self.calendar_service = CalendarService(self.config.calendar_api_url)
        calendar_agent = CollaborativeCalendarAgent(ai_client, self.calendar_service, self.logger)
        self.network.register_agent(calendar_agent)

        # 4) ChatAgent (for handling chat interactions)
        self.chat_agent = ChatAgent(ai_client, self.logger)
        self.network.register_agent(self.chat_agent)

        # 5) ProtocolAgent (for protocol management)
        self.protocol_agent = ProtocolAgent(self.logger)

        # 6) LightsAgent (for smart home control)
        load_dotenv()
        bridge_ip = os.getenv("HUE_BRIDGE_IP")
        self.lights_agent = PhillipsHueAgent(ai_client=ai_client, bridge_ip=bridge_ip)
        self.network.register_agent(self.lights_agent)

        # 7) SoftwareEngineeringAgent (developer tools)
        repo_path = self.config.repo_path
        self.software_agent = SoftwareEngineeringAgent(ai_client=ai_client, repo_path=repo_path, logger=self.logger)
        self.network.register_agent(self.software_agent)

        # Register protocol agent after other providers so capability map exists
        self.network.register_agent(self.protocol_agent)

    def _setup_protocol_system(self) -> None:
        """Initialize protocol executor and load protocol definitions."""
        self.protocol_executor = ProtocolExecutor(self.network, self.logger, usage_logger=self.usage_logger)

        protocols_dir = Path(__file__).parent / "protocols" / "definitions"
        if protocols_dir.exists():
            self._load_protocols_from_directory(protocols_dir)

        self.voice_matcher = VoiceTriggerMatcher(self.protocol_registry.protocols)

    async def _start_network(self) -> None:
        await self.network.start()

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
                        f"Failed to register protocol: {protocol.name}. Reason: {result.reason}",
                        result.message,
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
        if not self.nlu_agent:
            raise RuntimeError("System not initialized")

        # 1) First check for protocol matches (fast path)
        matched_protocol = None
        if self.voice_matcher:
            matched_protocol = self.voice_matcher.match_command(user_input)

        if not matched_protocol:
            matched_protocol = self.protocol_registry.find_matching_protocol(user_input)

        if matched_protocol:
            self.logger.log(
                "INFO",
                "Trigger matched",
                f"Command: '{user_input}' -> Protocol: '{matched_protocol.name}'",
            )

            try:
                # Execute the protocol directly
                results = await self.protocol_executor.run_protocol(
                    matched_protocol,
                    trigger_phrase=user_input,
                    metadata=metadata,
                )

                # Format the response in Jarvis style
                response = self._format_protocol_response(matched_protocol, results)

                return {
                    "response": response,
                    "protocol_executed": matched_protocol.name,
                    "execution_time": "fast",
                }
            except Exception as e:
                self.logger.log(
                    "ERROR",
                    f"Protocol execution failed for '{matched_protocol.name}'",
                    str(e),
                )
                # Fall through to NLU on error

        # 2) No protocol match or protocol failed - use NLU agent
        request_id = str(uuid.uuid4())
        await self.network.request_capability(
            from_agent=self.nlu_agent.name,
            capability="intent_matching",
            data={"input": user_input},
            request_id=request_id,
        )

        # 3) Wait for the classification result
        classification = await self.network.wait_for_response(request_id)
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
            payload = {"command": user_input}
            providers = await self.network.request_capability(
                from_agent=self.nlu_agent.name,
                capability=cap,
                data=payload,
                request_id=request_id,
            )
            self.logger.log("DEBUG", f"Requested '{cap}' from {providers}", payload)

            result = await self.network.wait_for_response(request_id)
            return {"response": result}

        if intent == "orchestrate_tasks":
            return await self.orchestrator.process_user_request(user_input, tz_name)

        if intent == "run_protocol":
            run_id = str(uuid.uuid4())
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
            payload = {"command": user_input}
            await self.network.request_capability(
                from_agent=self.nlu_agent.name,
                capability=cap,
                data=payload,
                request_id=define_id,
            )
            result = await self.network.wait_for_response(define_id)

            return {"response": result}

        # fallback
        return {"response": "Sorry, I didn't understand that."}

    def _format_protocol_response(
        self, protocol: Protocol, results: Dict[str, Any]
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

        # Create response based on protocol name and results
        protocol_responses = dict(PROTOCOL_RESPONSES)
        protocol_responses["check_today_schedule"] = self._format_calendar_response(results)

        # Return specific response or generic success
        return protocol_responses.get(
            protocol.name,
            f"{protocol.description or 'Command'} completed successfully, sir.",
        )

    def _format_calendar_response(self, results: Dict[str, Any]) -> str:
        """Format calendar-specific responses"""
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


# Simple interface for your existing code
async def create_collaborative_jarvis(api_key: str | None = None, repo_path: str = ".") -> "JarvisSystem":
    """Helper for demos and tests to create a ready-to-use system."""
    if api_key is None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")

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
