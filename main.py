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
    """Display a standardized agent response to the user.

    Handles the unified AgentResponse format with success, response, actions, data, and error fields.
    """
    # Extract standardized response fields
    response_text = result.get("response", "")
    actions = result.get("actions", [])
    success = result.get("success", True)
    error = result.get("error")

    console_mode = isinstance(output, ConsoleOutput)

    # Handle errors
    if error and not success:
        error_msg = (
            error.get("message", "Unknown error")
            if isinstance(error, dict)
            else str(error)
        )
        if console_mode:
            await output.send_output(
                Fore.RED + f"❌ Error: {error_msg}" + Style.RESET_ALL
            )
        else:
            await output.send_output(f"Error: {error_msg}")
        return

    # Display main response
    if response_text:
        if console_mode:
            await output.send_output(Fore.GREEN + str(response_text) + Style.RESET_ALL)
        else:
            await output.send_output(str(response_text))

    # Display actions if present (console mode only for brevity)
    if actions and console_mode:
        await output.send_output(Fore.YELLOW + "\n🔍 Actions:" + Style.RESET_ALL)
        for action in actions:
            function_name = action.get("function", "unknown")
            await output.send_output(
                Fore.BLUE + f"  • {function_name}" + Style.RESET_ALL
            )


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
            result_keys = list(result.keys()) if isinstance(result, dict) else "N/A"
            print(f"[MAIN] Got result, type: {type(result)}, keys: {result_keys}")
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
