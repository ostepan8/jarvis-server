import asyncio
from typing import Optional
import os
from dotenv import load_dotenv  # Add this import

from jarvis.ai_clients import AIClientFactory
from jarvis.agent import AICalendarAgent
from jarvis.calendar_service import CalendarService

# Load environment variables from .env file
load_dotenv()


async def demo() -> None:
    api_key = os.getenv("OPENAI_API_KEY")  # Get the API key from environment
    ai_client = AIClientFactory.create("openai", api_key=api_key)
    calendar_service = CalendarService()
    agent = AICalendarAgent(ai_client, calendar_service)

    result = await agent.process_request_with_reasoning(
        "I'm feeling overwhelmed. Clear my entire schedule for today and just add a 2-hour break at 2 PM"
    )
    print(result)


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")  # Fallback to env if not provided
    ai_client = AIClientFactory.create("openai", api_key=api_key)
    service = CalendarService()
    agent = AICalendarAgent(ai_client, service)
    response, _ = await agent.process_request(command)
    return response


if __name__ == "__main__":
    asyncio.run(demo())
