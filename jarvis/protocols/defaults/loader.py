from __future__ import annotations

import json
from pathlib import Path

import argparse
import asyncio

from .. import Protocol
from ..registry import ProtocolRegistry
from ..executor import ProtocolExecutor
from ...main_jarvis import create_collaborative_jarvis


def load_default_protocols(registry: ProtocolRegistry, directory: str | Path | None = None) -> None:
    """Load all JSON protocol definitions in *directory* into the registry."""
    if directory is None:
        directory = Path(__file__).parent
    else:
        directory = Path(directory)

    for file_path in directory.glob("*.json"):
        proto = Protocol.from_file(file_path)
        registry.register(proto)


async def run_protocol(file_path: str) -> None:
    """Run a protocol defined in *file_path* using a collaborative Jarvis."""
    jarvis = await create_collaborative_jarvis()
    executor = ProtocolExecutor(jarvis.network, jarvis.logger)
    proto = Protocol.from_file(file_path)
    results = await executor.execute(proto)
    print(json.dumps(results, indent=2))
    await jarvis.shutdown()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load or run default protocols")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("load", help="Load protocols into the registry")
    run_cmd = sub.add_parser("run", help="Run protocol from JSON file")
    run_cmd.add_argument("file", help="Path to protocol JSON")

    args = parser.parse_args(argv)

    registry = ProtocolRegistry()

    if args.cmd == "run":
        asyncio.run(run_protocol(args.file))
    else:
        load_default_protocols(registry)


if __name__ == "__main__":  # pragma: no cover - utility script
    main()
