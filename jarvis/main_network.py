# jarvis/main_network.py
import asyncio
import os
from typing import Dict, Any
from dotenv import load_dotenv

from .agents.agent_network import AgentNetwork
from .agents.calendar_agent import CollaborativeCalendarAgent
from .agents.orchestrator_agent import OrchestratorAgent
from .services.calendar_service import CalendarService
from .ai_clients import AIClientFactory
from .logger import JarvisLogger


class JarvisSystem:
    """Main Jarvis system that manages the agent network"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = JarvisLogger()
        self.network = AgentNetwork(self.logger)
        self.orchestrator: OrchestratorAgent | None = None
        self.calendar_service: CalendarService | None = None

    async def initialize(self):
        """Initialize all agents and start the network"""

        # Create AI client
        ai_client = AIClientFactory.create(
            self.config.get("ai_provider", "openai"), api_key=self.config.get("api_key")
        )

        # Create Orchestrator Agent (handles user requests and task sequencing)
        timeout = self.config.get("response_timeout", 15.0)
        self.orchestrator = OrchestratorAgent(
            ai_client, self.logger, response_timeout=timeout
        )
        self.network.register_agent(self.orchestrator)

        # Create Calendar Agent with integrated natural language logic
        self.calendar_service = CalendarService(
            self.config.get("calendar_api_url", "http://localhost:8080")
        )
        calendar_agent = CollaborativeCalendarAgent(
            ai_client, self.calendar_service, self.logger
        )
        self.network.register_agent(calendar_agent)

        # Add more agents as you build them:
        # email_agent = CollaborativeEmailAgent(email_service, self.logger)
        # self.network.register_agent(email_agent)

        # research_agent = CollaborativeResearchAgent(self.logger)
        # self.network.register_agent(research_agent)

        # Start the network
        await self.network.start()

        self.logger.log(
            "INFO",
            "Jarvis system initialized",
            f"Active agents: {list(self.network.agents.keys())}",
        )

    async def process_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Process a user request through the network"""
        if not self.orchestrator:
            raise RuntimeError("System not initialized")

        return await self.orchestrator.process_user_request(user_input, tz_name)

    async def shutdown(self):
        """Shutdown the system"""
        await self.network.stop()
        if self.calendar_service:
            await self.calendar_service.close()
        self.logger.log("INFO", "Jarvis system shutdown complete")


# Example usage and demo
async def demo():
    """Demo of the collaborative Jarvis system"""

    # Configuration
    load_dotenv()
    config = {
        "ai_provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "calendar_api_url": "http://localhost:8080",
    }

    # Create and initialize system
    jarvis = JarvisSystem(config)
    await jarvis.initialize()

    # Example requests that demonstrate agent collaboration
    examples = [
        # Simple single-agent request
        "What's on my calendar today?",
        # Multi-agent request (calendar + email)
        "Schedule a meeting with John tomorrow at 2 PM and send him an email to confirm",
        # Complex coordination
        "Find a free 2-hour slot this week when both Sarah and I are available, "
        "book a meeting room, and send calendar invites",
        # Intelligent scheduling
        "I need to schedule 5 one-hour meetings this week. Find the optimal times "
        "that minimize travel between locations and avoid early mornings",
        # Context-aware request
        "Cancel all my meetings tomorrow and email the attendees with an apology",
    ]

    # Process a request
    user_input = "Check my schedule for tomorrow and if I have any meetings with Sarah, find a good lunch spot nearby and add it to the calendar"

    print(f"\nUser: {user_input}")
    print("-" * 80)

    from tzlocal import get_localzone_name

    result = await jarvis.process_request(user_input, get_localzone_name())

    print(f"Jarvis: {result['response']}")
    print(f"\nAgents involved: {', '.join(result.get('agents_involved', []))}")

    # Shutdown
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
