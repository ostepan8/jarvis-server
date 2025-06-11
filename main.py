import asyncio
import os
from typing import Optional
from dotenv import load_dotenv

from jarvis.main_network import create_collaborative_jarvis
from tzlocal import get_localzone_name
from colorama import Fore, Style, init as colorama_init

# Load environment variables from .env file
load_dotenv()


async def demo() -> None:
    colorama_init(autoreset=True)
    jarvis = await create_collaborative_jarvis(os.getenv("OPENAI_API_KEY"))

    # Get user input for the calendar command
    user_command = input("Enter your calendar command: ")

    result = await jarvis.process_request(
        user_command,
        get_localzone_name(),
    )
    response_text = result.get("response", "")
    if result.get("success"):
        print(Fore.CYAN + response_text + Style.RESET_ALL)
    else:
        print(Fore.RED + response_text + Style.RESET_ALL)
    await jarvis.shutdown()


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    jarvis = await create_collaborative_jarvis(api_key or os.getenv("OPENAI_API_KEY"))
    result = await jarvis.process_request(command, get_localzone_name())
    await jarvis.shutdown()
    return result["response"]


if __name__ == "__main__":
    asyncio.run(demo())
