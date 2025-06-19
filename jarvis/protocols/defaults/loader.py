from __future__ import annotations

import json
from pathlib import Path

import argparse
import asyncio

from .. import Protocol
from ..registry import ProtocolRegistry
from ..executor import ProtocolExecutor
from ...main_jarvis import create_collaborative_jarvis


def register_protocols_from_directory(
    registry: ProtocolRegistry, directory: str | Path | None = None
) -> None:
    """
    Discover and register all protocol definitions from JSON files in the specified directory.

    Args:
        registry: The protocol registry to populate
        directory: Directory containing JSON protocol definitions (defaults to this module's directory)
    """
    if directory is None:
        directory = Path(__file__).parent
    else:
        directory = Path(directory)

    for file_path in directory.glob("*.json"):
        proto = Protocol.from_file(file_path)
        registry.register(proto)


async def execute_protocol_file(file_path: str) -> None:
    """
    Execute a protocol defined in the specified JSON file using a collaborative Jarvis instance.

    Args:
        file_path: Path to the JSON protocol definition file

    Returns:
        Prints execution results as formatted JSON
    """
    jarvis = await create_collaborative_jarvis()
    executor = ProtocolExecutor(jarvis.network, jarvis.logger)
    proto = Protocol.from_file(file_path)
    results = await executor.execute(proto)
    print(json.dumps(results, indent=2))
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
    parser = argparse.ArgumentParser(description="Protocol Management CLI")
    args = parser.parse_args()

    while True:
        print("\nProtocol Management CLI")
        print("1. Load protocols into registry")
        print("2. Run protocol from registry")
        print("3. Run protocol from JSON file")
        print("4. View details of a protocol")
        print("5. List all protocols in registry")
        print("6. Exit")

        choice = input("\nEnter your choice (1-6): ")

        if choice == "1":
            register_protocols_from_directory(registry)
            print(f"Loaded {len(registry.protocols)} protocols into registry")

        elif choice == "2":
            if not registry.protocols:
                print("No protocols in registry. Please load protocols first.")
                continue

            print("Available protocols:")
            for i, proto_id in enumerate(registry.protocols.keys(), 1):
                proto = registry.protocols[proto_id]
                print(f"{i}. {proto.name} (ID: {proto.id})")

            proto_index = input("Enter protocol number to run: ")
            try:
                proto_index = int(proto_index) - 1
                proto_id = list(registry.protocols.keys())[proto_index]
                proto = registry.protocols[proto_id]
                jarvis = asyncio.run(create_collaborative_jarvis())
                executor = ProtocolExecutor(jarvis.network, jarvis.logger)
                results = asyncio.run(executor.execute(proto))
                print(json.dumps(results, indent=2))
                asyncio.run(jarvis.shutdown())
            except (ValueError, IndexError) as e:
                print(f"Invalid selection: {e}")
            except Exception as e:
                print(f"Error running protocol: {e}")

        elif choice == "3":
            file_path = input("Enter path to protocol JSON file: ")
            try:
                asyncio.run(execute_protocol_file(file_path))
            except Exception as e:
                print(f"Error running protocol: {e}")

        elif choice == "4":
            file_path = input("Enter path to protocol JSON file: ")
            try:
                protocol = Protocol.from_file(file_path)
                print(f"Protocol ID: {protocol.id}")
                print(f"Name: {protocol.name}")
                print(f"Description: {protocol.description}")
                print(f"Steps ({len(protocol.steps)}):")
                for i, step in enumerate(protocol.steps, 1):
                    print(f"  {i}. {step.intent}")
                    if step.parameters:
                        print(
                            f"     Parameters: {json.dumps(step.parameters, indent=2)}"
                        )
            except Exception as e:
                print(f"Error loading protocol: {e}")

        elif choice == "5":
            if not registry.protocols:
                print("No protocols in registry. Please load protocols first.")
                continue

            print("Protocols in registry:")
            for proto_id, proto in registry.protocols.items():
                print(f"- {proto.name} (ID: {proto.id})")

        elif choice == "6":
            print("Exiting...")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":  # pragma: no cover - utility script
    launch_protocol_management_cli()
