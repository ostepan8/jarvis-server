# jarvis/main_network.py

import asyncio
import os
import uuid
from typing import Dict, Any
from dotenv import load_dotenv

from .agents.agent_network import AgentNetwork
from .agents.nlu_agent import NLUAgent
from .agents.protocal_agent import ProtocolAgent
from .agents.lights_agent import PhillipsHueAgent
from .agents.calendar_agent import CollaborativeCalendarAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .services.calendar_service import CalendarService
from .ai_clients import AIClientFactory
from .logger import JarvisLogger
from .agents.message import Message


class JarvisSystem:
    """Main Jarvis system that manages the agent network"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = JarvisLogger()
        self.network = AgentNetwork(self.logger)

        # Placeholders for your agents
        self.nlu_agent: NLUAgent = None
        self.orchestrator: OrchestratorAgent = None
        self.calendar_service: CalendarService = None
        self.lights_agent: PhillipsHueAgent = None
        self.protocal_agent: ProtocalAgent = None  # type: ignore

    async def initialize(self):
        """Initialize all agents and start the network"""

        # Create AI client
        ai_client = AIClientFactory.create(
            self.config.get("ai_provider", "openai"), api_key=self.config.get("api_key")
        )

        # 1) NLUAgent (must be registered so network.request_capability works)
        self.nlu_agent = NLUAgent(ai_client, self.logger)
        self.network.register_agent(self.nlu_agent)

        # 2) OrchestratorAgent (dynamic multi-step planning)
        timeout = self.config.get("response_timeout", 15.0)
        self.orchestrator = OrchestratorAgent(
            ai_client, self.logger, response_timeout=timeout
        )
        self.network.register_agent(self.orchestrator)

        # 3) CalendarAgent
        self.calendar_service = CalendarService(self.config.get("calendar_api_url"))
        calendar_agent = CollaborativeCalendarAgent(
            ai_client, self.calendar_service, self.logger
        )
        self.network.register_agent(calendar_agent)

        # 4) ProtocolAgent (for managing protocols)
        self.protocal_agent = ProtocolAgent(self.logger)
        
        # 5) LightsAgent (for smart home control)
        load_dotenv()
        BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")
        self.lights_agent = PhillipsHueAgent(ai_client=ai_client, bridge_ip=BRIDGE_IP)
        self.network.register_agent(self.lights_agent)

        # Register protocol agent after other providers so capability map exists
        self.network.register_agent(self.protocal_agent)

        # Start the message processing loop
        await self.network.start()

        self.logger.log(
            "INFO",
            "Jarvis system initialized",
            f"Active agents: {list(self.network.agents.keys())}",
        )

    async def process_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Process a user request through the network via NLU routing."""
        if not self.nlu_agent:
            raise RuntimeError("System not initialized")

        # 1) Ask NLUAgent to classify the intent
        request_id = str(uuid.uuid4())
        await self.network.request_capability(
            from_agent=self.nlu_agent.name,
            capability="intent_matching",
            data={"input": user_input},
            request_id=request_id,
        )

        # 2) Wait for the classification result
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

        # 3) Route to the appropriate agent
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
            # placeholder for PersonaAgent.chat()
            return {"response": "[Chit‐chat response]"}

        # fallback
        return {"response": "Sorry, I didn't understand that."}

    async def shutdown(self):
        """Shutdown the system"""
        await self.network.stop()
        if self.calendar_service:
            await self.calendar_service.close()
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

    user_input = "What's on my calendar tomorrow?"
    print(f"User: {user_input}\n" + "-" * 60)
    result = await jarvis.process_request(user_input, get_localzone_name())
    print(f"Jarvis: {result['response']}")

    await jarvis.shutdown()


# Simple interface for your existing code
async def create_collaborative_jarvis(api_key: str = None):
    """Create a collaborative Jarvis instance"""
    if api_key is None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
    config = {
        "ai_provider": "openai",
        "api_key": api_key,
        "calendar_api_url": "http://localhost:8080",
        "response_timeout": 60.0,
    }

    jarvis = JarvisSystem(config)
    await jarvis.initialize()
    return jarvis


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo())
