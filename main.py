import asyncio
import os
from typing import Optional
from dotenv import load_dotenv

from jarvis.main_jarvis import create_collaborative_jarvis
from tzlocal import get_localzone_name
from colorama import Fore, Style, init as colorama_init

# Load environment variables from .env file
load_dotenv()


async def demo() -> None:
    colorama_init(autoreset=True)
    jarvis = await create_collaborative_jarvis(os.getenv("OPENAI_API_KEY"))

    # Get user input for the calendar command
    user_command = input(
        "Enter your command for Jarvis (e.g., 'schedule a meeting', 'check my calendar'): "
    )

    result = await jarvis.process_request(
        user_command,
        get_localzone_name(),
    )
    response_data = result.get("response", "")

    if isinstance(response_data, dict):
        print(Fore.CYAN + "📋 Response Summary:" + Style.RESET_ALL)
        if "response" in response_data:
            print(Fore.GREEN + "🗣️ " + response_data["response"] + Style.RESET_ALL)

        if "actions" in response_data:
            print(Fore.YELLOW + "\n🔍 Actions performed:" + Style.RESET_ALL)
            for action in response_data["actions"]:
                print(Fore.BLUE + f"  • {action['function']}" + Style.RESET_ALL)
                result = action.get("result")
                if result is None:
                    continue

                # Handle dict results
                if isinstance(result, dict):
                    for key, value in result.items():
                        print(f"    - {key}: {Fore.MAGENTA}{value}{Style.RESET_ALL}")

                # Handle list results
                elif isinstance(result, list):
                    for item in result:
                        print(f"    - {Fore.MAGENTA}{item}{Style.RESET_ALL}")

                # Fallback for other types
                else:
                    print(f"    - {Fore.MAGENTA}{result}{Style.RESET_ALL}")

    else:
        # Handle string or error responses
        if result.get("success"):
            print(Fore.CYAN + str(response_data) + Style.RESET_ALL)
        else:
            print(Fore.RED + str(response_data) + Style.RESET_ALL)

    await jarvis.shutdown()


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    jarvis = await create_collaborative_jarvis(api_key or os.getenv("OPENAI_API_KEY"))
    result = await jarvis.process_request(command, get_localzone_name())
    await jarvis.shutdown()
    return result["response"]


if __name__ == "__main__":
    asyncio.run(demo())
