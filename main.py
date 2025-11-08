import argparse
import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from tzlocal import get_localzone_name
from colorama import Fore, Style, init as colorama_init

# NEW: use the builder
from jarvis.core import JarvisBuilder

from jarvis.io import (
    InputHandler,
    OutputHandler,
    ConsoleInput,
    ConsoleOutput,
)
from jarvis.io.input.wakeword import PicovoiceWakeWordListener
from jarvis.io.input import VoiceInputSystem
from jarvis.io.output.tts import ElevenLabsTTSEngine

# Load environment variables from .env file (once)
load_dotenv()


async def build_jarvis():
    """
    Build a Jarvis instance using the new builder style.
    Toggle features here as you like without touching the rest of main.
    """
    # Example toggles:
    # builder = (JarvisBuilder.from_env()
    #               .lights(True)
    #               .weather(True)
    #               .protocol_directory(True)
    #               .night_agents(True))
    builder = JarvisBuilder.from_env()
    jarvis = await builder.build()
    return jarvis


async def _display_result(result: dict, output: OutputHandler) -> None:
    print(f"[DISPLAY_START] _display_result called")
    print(f"[DISPLAY] result type: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
    response_data = result.get("response", "")
    print(f"[DISPLAY] response_data type: {type(response_data)}, value: {str(response_data)[:200]}")
    console_mode = isinstance(output, ConsoleOutput)
    print(f"[DISPLAY] console_mode: {console_mode}")
    
    # Handle the case where response_data is a dict (legacy format with actions)
    if isinstance(response_data, dict):
        print(f"[DISPLAY] response_data is dict, keys: {list(response_data.keys())}")
        if console_mode:
            await output.send_output(
                Fore.CYAN + "📋 Response Summary:" + Style.RESET_ALL
            )
        if "response" in response_data:
            print(f"[DISPLAY] Found 'response' key in response_data, value: {response_data['response']}")
            if console_mode:
                print(f"[DISPLAY] Console mode - sending output with formatting")
                await output.send_output(
                    Fore.GREEN + "🗣️ " + response_data["response"] + Style.RESET_ALL
                )
                print(f"[DISPLAY] Output sent to console")
            else:
                print(f"[DISPLAY] Non-console mode - sending output")
                await output.send_output(response_data["response"])
                print(f"[DISPLAY] Output sent")

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
                        str_value = str(value)
                        if len(str_value) > 100:
                            str_value = str_value[:97] + "..."
                        await output.send_output(
                            f"    - {key}: {Fore.MAGENTA}{str_value}{Style.RESET_ALL}"
                        )
                elif isinstance(result_value, list):
                    shown_items = result_value[:5]
                    for item in shown_items:
                        str_item = str(item)
                        if len(str_item) > 100:
                            str_item = str_item[:97] + "..."
                        await output.send_output(
                            f"    - {Fore.MAGENTA}{str_item}{Style.RESET_ALL}"
                        )
                    if len(result_value) > 5:
                        await output.send_output(
                            f"    - {Fore.YELLOW}...and {len(result_value) - 5} more items{Style.RESET_ALL}"
                        )
                else:
                    str_result = str(result_value)
                    if len(str_result) > 100:
                        str_result = str_result[:97] + "..."
                    await output.send_output(
                        f"    - {Fore.MAGENTA}{str_result}{Style.RESET_ALL}"
                    )
    # Handle the case where response_data is a simple string (current format)
    elif response_data:
        print(f"[DISPLAY] response_data is string, value: {str(response_data)[:200]}")
        if console_mode:
            print(f"[DISPLAY] Sending string response to console")
            await output.send_output(Fore.GREEN + str(response_data) + Style.RESET_ALL)
            print(f"[DISPLAY] String response sent to console")
        else:
            print(f"[DISPLAY] Sending string response (non-console)")
            await output.send_output(str(response_data))
            print(f"[DISPLAY] String response sent")
    # Fallback for empty response
    else:
        print(f"[DISPLAY] response_data is empty, using fallback")
        if console_mode:
            await output.send_output(Fore.YELLOW + "Request completed." + Style.RESET_ALL)
        else:
            await output.send_output("Request completed.")
        print(f"[DISPLAY] Fallback message sent")


async def demo(
    input_handler: InputHandler | None = ConsoleInput(),
    output_handler: OutputHandler | None = ConsoleOutput(),
) -> None:
    colorama_init(autoreset=True)

    # NEW: build with the builder
    jarvis = await build_jarvis()
    tz_name = get_localzone_name()

    # Get default user_id from environment or default to 1
    default_user_id = int(os.getenv("DEFAULT_USER_ID", "1"))

    try:
        while True:
            user_command = await input_handler.get_input("Jarvis> ")
            if user_command.strip().lower() in {"exit", "quit"}:
                break

            print(f"[MAIN] About to call jarvis.process_request with: {user_command}")
            result = await jarvis.process_request(
                user_command,
                tz_name,
                {"user_id": default_user_id, "source": "cli"},
                allowed_agents=None,
            )
            print(f"[MAIN] Got result from process_request, type: {type(result)}, keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            print(f"[MAIN] About to call _display_result")
            await _display_result(result, output_handler)
            print(f"[MAIN] _display_result completed")
    finally:
        await jarvis.shutdown()


async def run_console() -> None:
    """Run the interactive demo using console I/O."""
    await demo()


async def run_voice() -> None:
    """Run the demo using wake word detection, speech recognition, and TTS."""
    # NEW: build with the builder
    jarvis = await build_jarvis()
    tz_name = get_localzone_name()

    # Get default user_id from environment or default to 1
    default_user_id = int(os.getenv("DEFAULT_USER_ID", "1"))

    # Initialize components
    wake_listener = PicovoiceWakeWordListener(
        access_key=os.getenv("PORCUPINE_API_KEY"),
        keyword_paths=(
            os.getenv("PICOVOICE_KEYWORD_PATHS", "").split(os.pathsep)
            if os.getenv("PICOVOICE_KEYWORD_PATHS")
            else None
        ),
    )

    # Add speech recognition
    from jarvis.io.input.transcription.vosk import VoskSmallEnglishSTTEngine

    stt_engine = VoskSmallEnglishSTTEngine(
        model_path=os.getenv("VOSK_MODEL_PATH", "models/vosk-model-en-us-0.22-lgraph"),
        debug=os.getenv("VOSK_DEBUG", "false").lower() == "true",
    )

    tts_engine = ElevenLabsTTSEngine(
        default_voice=os.getenv("ELEVEN_VOICE_ID", "ErXwobaYiN019PkySvjV")
    )

    # Create the voice system with STT
    system = VoiceInputSystem(wake_listener, stt_engine, tts_engine)

    async def handler(text: str) -> str:
        if text.strip().lower() in {"exit", "quit", "goodbye"}:
            system.stop()
            return "Goodbye, sir."

        result = await jarvis.process_request(
            text,
            tz_name,
            {"user_id": default_user_id, "source": "voice"},
            allowed_agents=None,
        )
        await _display_result(result, ConsoleOutput())

        resp = result.get("response", "")
        if isinstance(resp, dict):
            return resp.get("response", "Command completed, sir.")
        return str(resp) if resp else "Command completed, sir."

    print("Voice system ready. Say 'Jarvis' to activate...")
    await system.run_forever(handler)
    await jarvis.shutdown()


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
