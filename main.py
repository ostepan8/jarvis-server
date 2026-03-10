import argparse
import asyncio
import os

from dotenv import load_dotenv
from tzlocal import get_localzone_name
from colorama import Fore, Style, init as colorama_init

# NEW: use the builder
from jarvis.core import JarvisBuilder
from jarvis.core.system import JarvisSystem
from jarvis.cli.config_dashboard import run_config_dashboard, show_agents_detail
from jarvis.cli.commands_dashboard import (
    show_commands_overview,
    show_command_detail,
    show_commands_all,
)
from jarvis.cli.models_dashboard import run_models_dashboard
from jarvis.cli.modes import show_modes_dashboard, enter_mode_by_slug

from jarvis.io import (
    InputHandler,
    OutputHandler,
    ConsoleInput,
    ConsoleOutput,
)
from jarvis.io.night_display import NightModePrinter
from jarvis.io.input.wakeword import PicovoiceWakeWordListener
from jarvis.io.input import VoiceInputSystem
from jarvis.io.output.tts import ElevenLabsTTSEngine

# Load environment variables from .env file (once)
load_dotenv()

IDLE_TIMEOUT_SECONDS = int(os.getenv("JARVIS_IDLE_TIMEOUT", "300"))


async def build_jarvis() -> "JarvisSystem":
    """
    Build a Jarvis instance using the new builder style.
    Toggle features here as you like without touching the rest of main.
    """
    # Example toggles:
    # builder = (JarvisBuilder.from_env()
    #               .lights(True)
    #               .search(True)
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

    # Handle errors (both explicit and implicit success=False)
    if error or not success:
        error_msg = None
        if error:
            error_msg = (
                error.get("message", "Unknown error")
                if isinstance(error, dict)
                else str(error)
            )

        if console_mode:
            # If we have response text, show it in red
            if response_text:
                await output.send_output(
                    Fore.RED + "❌ " + str(response_text) + Style.RESET_ALL
                )
            # If we have a separate error message, show that too
            if error_msg and error_msg != response_text:
                await output.send_output(
                    Fore.RED + f"   Error details: {error_msg}" + Style.RESET_ALL
                )
        else:
            if response_text:
                await output.send_output(f"Error: {response_text}")
            elif error_msg:
                await output.send_output(f"Error: {error_msg}")
        return

    # Display main response (success case)
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

    # Narrow Optional types so the rest of the function is safe
    if input_handler is None:
        input_handler = ConsoleInput()
    if output_handler is None:
        output_handler = ConsoleOutput()

    # NEW: build with the builder
    jarvis = await build_jarvis()
    tz_name = get_localzone_name() or "UTC"

    # Get default user_id from environment or default to 1
    default_user_id = int(os.getenv("DEFAULT_USER_ID", "1"))
    
    # Get logger from jarvis system
    logger = jarvis.logger

    input_task = None
    night_printer = None

    try:
        while True:
            if input_task is None:
                input_task = asyncio.create_task(input_handler.get_input("Jarvis> "))

            done, _ = await asyncio.wait({input_task}, timeout=IDLE_TIMEOUT_SECONDS)

            if not done:
                # Idle timeout — slip into night mode if not already there
                if not jarvis.night_mode:
                    night_printer = NightModePrinter()
                    night_printer.print_entering()
                    await jarvis.enter_night_mode(progress_callback=night_printer.on_event)
                continue  # Loop back; same input_task stays alive

            # User typed something
            user_command = input_task.result()
            input_task = None

            # Wake from night mode if active
            if jarvis.night_mode and night_printer:
                night_printer.print_waking()
                await jarvis.exit_night_mode()
                night_printer = None

            if user_command.strip().lower() in {"exit", "quit"}:
                break

            cmd = user_command.strip().lower()

            # Slash commands
            if cmd == "/night":
                if jarvis.night_mode:
                    if night_printer:
                        night_printer.print_waking()
                    await jarvis.exit_night_mode()
                    night_printer = None
                else:
                    night_printer = NightModePrinter()
                    night_printer.print_entering()
                    await jarvis.enter_night_mode(progress_callback=night_printer.on_event)
                continue
            if cmd == "/config":
                await run_config_dashboard(jarvis)
                continue
            if cmd == "/models":
                await run_models_dashboard(jarvis)
                continue
            if cmd == "/agents":
                await show_agents_detail(jarvis)
                continue
            if cmd.startswith("/commands"):
                arg = cmd[len("/commands"):].strip()
                if arg == "all":
                    await show_commands_all(jarvis)
                elif arg:
                    await show_command_detail(jarvis, arg)
                else:
                    await show_commands_overview(jarvis)
                continue
            if cmd == "/modes":
                await show_modes_dashboard(jarvis)
                continue
            if cmd == "/help":
                print("\nAvailable commands:")
                print("  /commands       - Browse all trigger phrases (shortest first)")
                print("  /commands all   - Show every trigger phrase for every command")
                print("  /commands <name> - Show details for a specific command")
                print("  /config         - Interactive config dashboard")
                print("  /models         - AI model & preset management")
                print("  /agents         - View active agents")
                print("  /modes          - SSH into a device (direct control)")
                print("  /night          - Toggle night mode (auto-improvement)")
                print("  /help           - Show this help")
                print("  exit            - Quit Jarvis\n")
                continue

            # Natural language mode triggers
            _ssh_triggers = [
                "ssh into my tv", "ssh roku", "ssh into roku",
                "ssh into my roku", "ssh into the tv", "ssh tv",
                "connect to my tv", "connect to roku",
            ]
            if cmd in _ssh_triggers:
                await enter_mode_by_slug(jarvis, "roku")
                continue

            logger.log("DEBUG", "Processing user request", {"command": user_command})
            result = await jarvis.process_request(
                user_command,
                tz_name,
                {"user_id": default_user_id, "source": "cli"},
                allowed_agents=None,
            )
            result_keys = list(result.keys()) if isinstance(result, dict) else "N/A"
            logger.log("DEBUG", "Request completed", {"result_type": str(type(result)), "result_keys": result_keys})
            await _display_result(result, output_handler)
    finally:
        await jarvis.shutdown()


async def run_console() -> None:
    """Run the interactive demo using console I/O."""
    await demo()


async def run_voice() -> None:
    """Run the demo using wake word detection, speech recognition, and TTS."""
    # NEW: build with the builder
    jarvis = await build_jarvis()
    tz_name = get_localzone_name() or "UTC"

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

    jarvis.logger.log("INFO", "Voice system ready", {"message": "Say 'Jarvis' to activate"})
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
