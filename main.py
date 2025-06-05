import asyncio
from typing import Optional

from jarvis.ai_clients import AIClientFactory
from jarvis.agent import AICalendarAgent
from jarvis.calendar_service import CalendarService


async def demo() -> None:
    ai_client = AIClientFactory.create("openai", api_key="your-api-key-here")
    calendar_service = CalendarService()
    agent = AICalendarAgent(ai_client, calendar_service)

    result = await agent.process_request_with_reasoning(
        "I'm feeling overwhelmed. Clear my entire schedule for today and just add a 2-hour break at 2 PM"
    )
    print(result)


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    ai_client = AIClientFactory.create("openai", api_key=api_key)
    service = CalendarService()
    agent = AICalendarAgent(ai_client, service)
    response, _ = await agent.process_request(command)
    return response


if __name__ == "__main__":
    asyncio.run(demo())
