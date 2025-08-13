from __future__ import annotations

import json
from pathlib import Path

import argparse
import asyncio

from .. import Protocol
from ..registry import ProtocolRegistry
from ..executor import ProtocolExecutor
from ...logging import JarvisLogger
from jarvis.core import JarvisBuilder


def register_protocols_from_directory(
    registry: ProtocolRegistry,
    directory: str | Path | None = None,
    logger: JarvisLogger | None = None,
) -> None:
    """
    Discover and register all protocol definitions from JSON files in the specified directory.

    Args:
        registry: The protocol registry to populate
        directory: Directory containing JSON protocol definitions (defaults to protocols/definitions/)
    """
    if directory is None:
        # Default to protocols/definitions/ directory
        directory = Path(__file__).parent / "definitions"
    else:
        directory = Path(directory)

    logger = logger or JarvisLogger()

    if not directory.exists():
        logger.log("ERROR", "Directory does not exist", str(directory))
        return

    json_files = list(directory.glob("*.json"))
    logger.log("INFO", f"Found {len(json_files)} JSON files", str(directory))

    for file_path in json_files:
        try:
            logger.log("INFO", f"Loading {file_path.name}...")
            proto = Protocol.from_file(file_path)
            result = registry.register(proto)
            if result.get("success") is True:
                logger.log("INFO", f"Registered protocol: {proto.name} ({proto.id})")
                # Log argument definitions if present
                if proto.argument_definitions:
                    args_info = [
                        f"{ad.name}({ad.type.value})"
                        for ad in proto.argument_definitions
                    ]
                    logger.log("INFO", f"  Arguments: {', '.join(args_info)}")
            elif result.get("success") is False:
                logger.log(
                    "ERROR",
                    f"Failed to register protocol {proto.name}: {result.get('reason')}",
                )

        except Exception as e:
            logger.log("ERROR", f"Failed to load {file_path.name}", str(e))


async def execute_protocol_file(
    file_path: str, logger: JarvisLogger | None = None
) -> None:
    """
    Execute a protocol defined in the specified JSON file using a collaborative Jarvis instance.

    Args:
        file_path: Path to the JSON protocol definition file

    Returns:
        Prints execution results as formatted JSON
    """
    logger = logger or JarvisLogger()
    logger.log("INFO", f"Loading protocol from {file_path}...")
    builder = JarvisBuilder.from_env()
    jarvis = await builder.build()
    executor = ProtocolExecutor(jarvis.network, jarvis.logger)
    proto = Protocol.from_file(file_path)
    logger.log("INFO", f"Executing protocol: {proto.name}")
    results = await executor.execute(proto, allowed_agents=None)
    logger.log("INFO", "Results", results)
    await jarvis.shutdown()


async def execute_protocol_by_name(
    name: str, logger: JarvisLogger | None = None
) -> None:
    """
    Execute a protocol by name using voice trigger matching.

    Args:
        name: Protocol name or voice trigger phrase
    """
    logger = logger or JarvisLogger()
    builder = JarvisBuilder.from_env()
    jarvis = await builder.build()

    # Try to find a matching protocol using the enhanced matcher
    match_result = jarvis.voice_matcher.match_command(name)
    if match_result:
        protocol = match_result["protocol"]
        arguments = match_result["arguments"]
        logger.log("INFO", f"Matched protocol: {protocol.name}")
        if arguments:
            logger.log("INFO", f"Extracted arguments: {arguments}")

        # Use the new run_protocol_with_match method
        results = await jarvis.protocol_executor.run_protocol_with_match(match_result)
        logger.log("INFO", "Results", results)
    else:
        logger.log("WARNING", f"No protocol found matching '{name}'")
        logger.log(
            "INFO", "Available triggers", jarvis.voice_matcher.get_all_triggers()
        )

    await jarvis.shutdown()


def launch_protocol_management_cli() -> None:
    """
    Launch the interactive command-line interface for protocol management.

    Provides options for:
    - Loading and registering protocols
    - Executing protocols from registry or file
    - Viewing protocol details and listings
    """
    registry = ProtocolRegistry()

    # Try to load protocols on startup
    print("Loading protocols from registry database...")
    registry.load()
    print(f"Loaded {len(registry.protocols)} protocols from database")

    while True:
        print("\n" + "=" * 50)
        print("Protocol Management CLI")
        print("=" * 50)
        print("1. Load protocols from definitions directory")
        print("2. Run protocol from registry")
        print("3. Run protocol from JSON file")
        print("4. Execute protocol by voice trigger")
        print("5. View protocol details")
        print("6. List all protocols in registry")
        print("7. List all voice triggers")
        print("8. Test voice command matching")  # NEW
        print("9. Exit")

        choice = input("\nEnter your choice (1-9): ")

        if choice == "1":
            directory = input(
                "Enter directory path (press Enter for default): "
            ).strip()
            if not directory:
                directory = None
            register_protocols_from_directory(
                registry,
                directory,
            )
            print(f"\nTotal protocols in registry: {len(registry.protocols)}")

        elif choice == "2":
            if not registry.protocols:
                print("No protocols in registry. Please load protocols first.")
                continue

            print("\nAvailable protocols:")
            protocols_list = list(registry.protocols.items())
            for i, (proto_id, proto) in enumerate(protocols_list, 1):
                print(f"{i}. {proto.name} - {proto.description}")
                print(f"   Triggers: {', '.join(proto.trigger_phrases)}")
                # Show argument definitions if present
                if proto.argument_definitions:
                    args_info = [
                        f"{ad.name}({ad.type.value})"
                        for ad in proto.argument_definitions
                    ]
                    print(f"   Arguments: {', '.join(args_info)}")

            proto_index = input("\nEnter protocol number to run: ")
            try:
                proto_index = int(proto_index) - 1
                proto_id, proto = protocols_list[proto_index]

                print(f"\nExecuting protocol: {proto.name}")

                # Handle protocols with arguments
                arguments = {}
                if proto.argument_definitions:
                    print("\nThis protocol requires arguments:")
                    for arg_def in proto.argument_definitions:
                        if arg_def.type.value == "choice":
                            print(
                                f"  {arg_def.name} (choices: {', '.join(arg_def.choices)})"
                            )
                            value = input(f"Enter {arg_def.name}: ").strip()
                            if value.lower() in [c.lower() for c in arg_def.choices]:
                                arguments[arg_def.name] = value.lower()
                            else:
                                print(
                                    f"Invalid choice. Using first option: {arg_def.choices[0]}"
                                )
                                arguments[arg_def.name] = arg_def.choices[0].lower()
                        elif arg_def.type.value == "range":
                            print(
                                f"  {arg_def.name} (range: {arg_def.min_val}-{arg_def.max_val})"
                            )
                            value = input(f"Enter {arg_def.name}: ").strip()
                            try:
                                num_val = int(value)
                                if (
                                    arg_def.min_val is None
                                    or num_val >= arg_def.min_val
                                ) and (
                                    arg_def.max_val is None
                                    or num_val <= arg_def.max_val
                                ):
                                    arguments[arg_def.name] = num_val
                                else:
                                    print(
                                        f"Value out of range. Using default: {arg_def.min_val or 0}"
                                    )
                                    arguments[arg_def.name] = arg_def.min_val or 0
                            except ValueError:
                                print(
                                    f"Invalid number. Using default: {arg_def.min_val or 0}"
                                )
                                arguments[arg_def.name] = arg_def.min_val or 0
                        else:
                            value = input(f"Enter {arg_def.name}: ").strip()
                            arguments[arg_def.name] = value

                async def run_protocol():
                    builder = JarvisBuilder.from_env()
                    jarvis = await builder.build()
                    executor = ProtocolExecutor(jarvis.network, jarvis.logger)
                    results = await executor.execute(
                        proto, context=arguments, allowed_agents=None
                    )
                    await jarvis.shutdown()
                    return results

                results = asyncio.run(run_protocol())
                print("\nResults:")
                print(json.dumps(results, indent=2))
            except (ValueError, IndexError) as e:
                print(f"Invalid selection: {e}")
            except Exception as e:
                print(f"Error running protocol: {e}")
                import traceback

                traceback.print_exc()

        elif choice == "3":
            file_path = input("Enter path to protocol JSON file: ")
            try:
                asyncio.run(execute_protocol_file(file_path))
            except Exception as e:
                print(f"Error running protocol: {e}")
                import traceback

                traceback.print_exc()

        elif choice == "4":
            trigger = input(
                "Enter voice trigger phrase (e.g., 'lights off' or 'change lights to red'): "
            )
            try:
                asyncio.run(execute_protocol_by_name(trigger))
            except Exception as e:
                print(f"Error executing protocol: {e}")
                import traceback

                traceback.print_exc()

        elif choice == "5":
            if not registry.protocols:
                print("No protocols in registry.")
                continue

            print("\nEnter protocol name or ID:")
            identifier = input().strip()

            proto = registry.get(identifier)
            if proto:
                print(f"\nProtocol Details:")
                print(f"ID: {proto.id}")
                print(f"Name: {proto.name}")
                print(f"Description: {proto.description}")
                print(f"Trigger phrases: {', '.join(proto.trigger_phrases)}")

                # Show argument definitions
                if proto.argument_definitions:
                    print(f"Arguments:")
                    for arg_def in proto.argument_definitions:
                        print(f"  - {arg_def.name} ({arg_def.type.value})")
                        if arg_def.type.value == "choice":
                            print(f"    Choices: {', '.join(arg_def.choices)}")
                        elif arg_def.type.value == "range":
                            print(f"    Range: {arg_def.min_val}-{arg_def.max_val}")
                        print(f"    Description: {arg_def.description}")
                        print(f"    Required: {arg_def.required}")

                print(f"Steps ({len(proto.steps)}):")
                for i, step in enumerate(proto.steps, 1):
                    print(f"  {i}. Agent: {step.agent}, Function: {step.function}")
                    if step.parameters:
                        print(
                            f"     Parameters: {json.dumps(step.parameters, indent=8)}"
                        )
                    if step.parameter_mappings:
                        print(
                            f"     Mappings: {json.dumps(step.parameter_mappings, indent=8)}"
                        )
            else:
                print(f"Protocol '{identifier}' not found")

        elif choice == "6":
            if not registry.protocols:
                print("No protocols in registry. Please load protocols first.")
                continue

            print("\nProtocols in registry:")
            for proto_id, proto in registry.protocols.items():
                print(f"\n{proto.name} (ID: {proto.id})")
                print(f"  Description: {proto.description}")
                print(f"  Triggers: {', '.join(proto.trigger_phrases)}")
                print(f"  Steps: {len(proto.steps)}")
                if proto.argument_definitions:
                    args_info = [
                        f"{ad.name}({ad.type.value})"
                        for ad in proto.argument_definitions
                    ]
                    print(f"  Arguments: {', '.join(args_info)}")

        elif choice == "7":
            if not registry.protocols:
                print("No protocols loaded.")
                continue

            print("\nAll voice triggers:")
            all_triggers = {}
            for proto in registry.protocols.values():
                for trigger in proto.trigger_phrases:
                    all_triggers[trigger] = proto.name

            for trigger, proto_name in sorted(all_triggers.items()):
                if "{" in trigger and "}" in trigger:
                    print(f"  '{trigger}' → {proto_name} (parameterized)")
                else:
                    print(f"  '{trigger}' → {proto_name}")

        elif choice == "8":  # NEW: Test voice command matching
            if not registry.protocols:
                print("No protocols loaded.")
                continue

            from ..voice_trigger import VoiceTriggerMatcher

            matcher = VoiceTriggerMatcher(registry.protocols)

            print("\nTesting voice command matching...")
            print("Enter voice commands to test (or 'quit' to return):")

            while True:
                command = input("\nVoice command: ").strip()
                if command.lower() == "quit":
                    break

                match_result = matcher.match_command(command)
                if match_result:
                    protocol = match_result["protocol"]
                    arguments = match_result["arguments"]
                    matched_phrase = match_result["matched_phrase"]

                    print(f"✅ MATCH!")
                    print(f"  Protocol: {protocol.name}")
                    print(f"  Matched phrase: '{matched_phrase}'")
                    if arguments:
                        print(f"  Extracted arguments: {arguments}")
                    else:
                        print(f"  No arguments extracted")
                else:
                    print(f"❌ No match found for '{command}'")

        elif choice == "9":
            print("Exiting...")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":  # pragma: no cover - utility script
    launch_protocol_management_cli()
