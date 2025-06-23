import argparse
import asyncio
import os
from typing import Optional
from dotenv import load_dotenv

from jarvis.main_jarvis import create_collaborative_jarvis
from tzlocal import get_localzone_name
from colorama import Fore, Style, init as colorama_init
from jarvis.io import (
    InputHandler,
    OutputHandler,
    ConsoleInput,
    ConsoleOutput,
)
from jarvis.io.elevenlabs_output import ElevenLabsOutput
from jarvis.voice import (
    VoiceInputSystem,
    PicovoiceWakeWordListener,
    ElevenLabsTTSEngine,
)

# Load environment variables from .env file
load_dotenv()


async def _display_result(result: dict, output: OutputHandler) -> None:
    response_data = result.get("response", "")
    console_mode = isinstance(output, ConsoleOutput)
    if isinstance(response_data, dict):
        if console_mode:
            await output.send_output(
                Fore.CYAN + "📋 Response Summary:" + Style.RESET_ALL
            )
        if "response" in response_data:
            if console_mode:
                await output.send_output(
                    Fore.GREEN + "🗣️ " + response_data["response"] + Style.RESET_ALL
                )
            else:
                await output.send_output(response_data["response"])

        if "actions" in response_data and console_mode:
            await output.send_output(
                Fore.YELLOW + "\n🔍 Actions performed:" + Style.RESET_ALL
            )
            for action in response_data["actions"]:
                await output.send_output(
                    Fore.BLUE + f"  • {action['function']}" + Style.RESET_ALL
                )
                result_value = action.get("result")
                if result_value is None:
                    continue

                if isinstance(result_value, dict):
                    for key, value in result_value.items():
                        await output.send_output(
                            f"    - {key}: {Fore.MAGENTA}{value}{Style.RESET_ALL}"
                        )
                elif isinstance(result_value, list):
                    for item in result_value:
                        await output.send_output(
                            f"    - {Fore.MAGENTA}{item}{Style.RESET_ALL}"
                        )
                else:
                    await output.send_output(
                        f"    - {Fore.MAGENTA}{result_value}{Style.RESET_ALL}"
                    )
    else:
        if result.get("success"):
            await output.send_output(Fore.CYAN + str(response_data) + Style.RESET_ALL)
        else:
            await output.send_output(Fore.RED + str(response_data) + Style.RESET_ALL)


async def demo(
    input_handler: InputHandler | None = ConsoleInput(),
    output_handler: OutputHandler | None = ConsoleOutput(),
) -> None:
    colorama_init(autoreset=True)

    jarvis = await create_collaborative_jarvis(os.getenv("OPENAI_API_KEY"))
    tz_name = get_localzone_name()

    while True:
        user_command = await input_handler.get_input("Jarvis> ")
        if user_command.strip().lower() in {"exit", "quit"}:
            break

        result = await jarvis.process_request(user_command, tz_name, {})
        await _display_result(result, output_handler)

    await jarvis.shutdown()


async def run_console() -> None:
    """Run the interactive demo using console I/O."""
    await demo()


async def run_voice() -> None:
    """Run the demo using wake word detection and ElevenLabs TTS."""

    jarvis = await create_collaborative_jarvis(os.getenv("OPENAI_API_KEY"))
    tz_name = get_localzone_name()

    wake_listener = PicovoiceWakeWordListener(
        access_key=os.getenv("PICOVOICE_ACCESS_KEY"),
        keyword_paths=os.getenv("PICOVOICE_KEYWORD_PATHS", "").split(os.pathsep)
        if os.getenv("PICOVOICE_KEYWORD_PATHS")
        else None,
    )
    tts_engine = ElevenLabsTTSEngine(
        default_voice=os.getenv("ELEVEN_VOICE_ID", "ErXwobaYiN019PkySvjV")
    )
    system = VoiceInputSystem(wake_listener, tts_engine)

    async def handler(text: str) -> str:
        if text.strip().lower() in {"exit", "quit"}:
            system.stop()
            return "Goodbye"
        result = await jarvis.process_request(text, tz_name, {})
        await _display_result(result, ConsoleOutput())
        resp = result.get("response", "")
        if isinstance(resp, dict):
            return resp.get("response", "")
        return str(resp)

    await system.run_forever(handler)
    await jarvis.shutdown()


async def calendar_ai(command: str, api_key: Optional[str] = None) -> str:
    jarvis = await create_collaborative_jarvis(api_key or os.getenv("OPENAI_API_KEY"))
    result = await jarvis.process_request(command, get_localzone_name(), {})
    await jarvis.shutdown()
    return result["response"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jarvis demo")
    parser.add_argument(
        "--mode",
        choices=["console", "voice"],
        default="console",
        help="Run in text console mode or voice mode",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.mode == "voice":
        asyncio.run(run_voice())
    else:
        asyncio.run(run_console())
