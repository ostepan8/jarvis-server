# agents/protocol_agent.py

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional, Set

from .base import NetworkAgent
from .message import Message
from ..logger import JarvisLogger


class ProtocolAgent(NetworkAgent):
    """Agent that stores, describes, and runs named multi-step protocols."""

    STORAGE_PATH = "protocols.json"

    def __init__(self, logger: Optional[JarvisLogger] = None) -> None:
        super().__init__("ProtocolAgent", logger)
        # Load existing protocols or start empty
        self.protocols: Dict[str, Dict[str, Any]] = self._load_protocols()
        # Expose them to the network for NLU discovery
        self.network and self._sync_registry()

    @property
    def description(self) -> str:
        return (
            "Manages named multi-step protocols: define, list, describe, and run them."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {
            "define_protocol",
            "list_protocols",
            "describe_protocol",
            "run_protocol",
        }

    def _load_protocols(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.STORAGE_PATH):
            try:
                with open(self.STORAGE_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                self.logger.log("ERROR", "Failed to load protocols", "")
        return {}

    def _save_protocols(self) -> None:
        try:
            with open(self.STORAGE_PATH, "w") as f:
                json.dump(self.protocols, f, indent=2)
        except Exception as e:
            self.logger.log("ERROR", "Failed to save protocols", str(e))

    def _sync_registry(self) -> None:
        """Sync network.protocol_registry with current protocols."""
        if self.network:
            self.network.protocol_registry = list(self.protocols.keys())

    async def _handle_capability_request(self, message: Message) -> None:
        cap = message.content.get("capability")
        data = message.content.get("data", {}) or {}
        req_id = message.request_id

        if cap == "define_protocol":
            await self._handle_define(message, data)
        elif cap == "list_protocols":
            await self._handle_list(message)
        elif cap == "describe_protocol":
            await self._handle_describe(message, data)
        elif cap == "run_protocol":
            await self._handle_run(message, data)
        else:
            # Not our concern
            return

    async def _handle_define(self, message: Message, data: Dict[str, Any]) -> None:
        name = data.get("name")
        description = data.get("description", "")
        steps = data.get("steps", [])
        if not name or not isinstance(steps, list):
            await self.send_error(
                message.from_agent, "Invalid protocol definition", message.request_id
            )
            return

        self.protocols[name] = {
            "description": description,
            "steps": steps,
        }
        self._save_protocols()
        self._sync_registry()

        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"status": "ok", "name": name},
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_list(self, message: Message) -> None:
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"protocols": list(self.protocols.keys())},
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_describe(self, message: Message, data: Dict[str, Any]) -> None:
        name = data.get("protocol_name")
        proto = self.protocols.get(name)
        if not proto:
            await self.send_error(
                message.from_agent, f"Unknown protocol '{name}'", message.request_id
            )
            return

        await self.send_capability_response(
            to_agent=message.from_agent,
            result={
                "name": name,
                "description": proto.get("description", ""),
                "steps": proto.get("steps", []),
            },
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_run(self, message: Message, data: Dict[str, Any]) -> None:
        name = data.get("protocol_name")
        args = data.get("args", {}) or {}
        proto = self.protocols.get(name)
        if not proto:
            await self.send_error(
                message.from_agent, f"Unknown protocol '{name}'", message.request_id
            )
            return

        results: Dict[str, Any] = {}
        # Execute each step in sequence
        for step in proto["steps"]:
            agent_name = step.get("agent")
            capability = step.get("capability")
            step_args = {**step.get("args", {}), **args}

            if not agent_name or not capability:
                results.setdefault("errors", []).append(
                    f"Invalid step in protocol '{name}': {step}"
                )
                continue

            # Send request to the specific agent
            step_req = str(uuid.uuid4())
            await self.send_message(
                to_agent=agent_name,
                message_type="capability_request",
                content={"capability": capability, "data": step_args},
                request_id=step_req,
            )
            # Wait for its response or error
            res = await self.network.wait_for_response(step_req)
            results[capability] = res

        # Send back the aggregated results
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"protocol": name, "results": results},
            request_id=message.request_id,
            original_message_id=message.id,
        )
