import asyncio
import os
from typing import Optional
from dotenv import load_dotenv

from jarvis.main_network import create_collaborative_jarvis

# Load environment variables from .env file
load_dotenv()


async def demo() -> None:
    jarvis = await create_collaborative_jarvis(os.getenv("OPENAI_API_KEY"))
    result = await jarvis.process_request(
        "Remove everything from my schedule for June 5th."
    )
    print(result)
    await jarvis.shutdown()


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    jarvis = await create_collaborative_jarvis(api_key or os.getenv("OPENAI_API_KEY"))
    result = await jarvis.process_request(command)
    await jarvis.shutdown()
    return result["response"]


if __name__ == "__main__":
    asyncio.run(demo())
