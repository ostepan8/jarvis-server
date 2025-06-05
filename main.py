import asyncio
from typing import Optional
import os
from dotenv import load_dotenv  # Add this import

from jarvis.ai_clients import AIClientFactory
from jarvis.agent import AICalendarAgent
from jarvis.calendar_service import CalendarService
from jarvis.logger import JarvisLogger

# Load environment variables from .env file
load_dotenv()


async def demo() -> None:
    api_key = os.getenv("OPENAI_API_KEY")  # Get the API key from environment
    ai_client = AIClientFactory.create("openai", api_key=api_key)
    logger = JarvisLogger()
    calendar_service = CalendarService(logger=logger)
    agent = AICalendarAgent(ai_client, calendar_service, logger=logger)

    # First create events
    # result = await agent.process_request_with_reasoning(
    #     "Create a full schedule for June 5th with the following activities: "
    #     "7-8:30 AM: Morning workout and basketball drills, "
    #     "9-10:30 AM: LeetCode practice focusing on algorithms, "
    #     "11 AM-12 PM: Quant finance study (stochastic calculus), "
    #     "1-2:30 PM: Software engineering work on system design, "
    #     "3-4 PM: Technical interview prep, "
    #     "4:30-6 PM: Basketball pickup game, "
    #     "7-8 PM: Coding project work, "
    #     "8:30-9:30 PM: Review quantitative trading strategies"
    # )
    # print(result)

    # Then remove all events on June 5th
    result = await agent.process_request_with_reasoning("Remove all events on June 5th")
    print(result)


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")  # Fallback to env if not provided
    ai_client = AIClientFactory.create("openai", api_key=api_key)
    logger = JarvisLogger()
    service = CalendarService(logger=logger)
    agent = AICalendarAgent(ai_client, service, logger=logger)
    response, _ = await agent.process_request(command)
    return response


if __name__ == "__main__":
    asyncio.run(demo())
