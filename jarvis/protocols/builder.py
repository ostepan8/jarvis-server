from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from . import Protocol, ProtocolStep
from .registry import ProtocolRegistry


def create_from_file(file_path: str, registry: ProtocolRegistry) -> Protocol:
    data = json.loads(Path(file_path).read_text())
    steps = [ProtocolStep(**s) for s in data.get("steps", [])]
    proto = Protocol(
        id=str(uuid.uuid4()),
        name=data["name"],
        description=data.get("description", ""),
        steps=steps,
    )
    registry.register(proto)
    return proto


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Protocol builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_cmd = sub.add_parser("create", help="Create protocol from JSON file")
    create_cmd.add_argument("file", help="Path to JSON definition")

    sub.add_parser("list", help="List protocols")

    describe_cmd = sub.add_parser("describe", help="Describe a protocol")
    describe_cmd.add_argument("identifier", help="Protocol id or name")

    args = parser.parse_args(argv)

    registry = ProtocolRegistry()

    if args.cmd == "create":
        proto = create_from_file(args.file, registry)
        print(f"Created protocol {proto.name} ({proto.id})")
    elif args.cmd == "list":
        for pid in registry.list_ids():
            p = registry.get(pid)
            print(f"{pid}: {p.name}")
    elif args.cmd == "describe":
        proto = registry.get(args.identifier)
        if not proto:
            print("Protocol not found")
        else:
            print(json.dumps({
                "id": proto.id,
                "name": proto.name,
                "description": proto.description,
                "steps": [s.__dict__ for s in proto.steps],
            }, indent=2))


if __name__ == "__main__":  # pragma: no cover - manual tool
    main()
