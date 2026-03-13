"""ServerManagerAgent — manages server lifecycle and health monitoring.

Capabilities:
    start_server   — start a managed server by name
    stop_server    — stop a managed server by name
    restart_server — restart a managed server
    server_status  — get status of a specific server
    list_servers   — list all registered servers and their statuses
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from ..base import NetworkAgent
from ..agent_network import AgentNetwork
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...logging import JarvisLogger

if TYPE_CHECKING:
    from ...services.server_manager_service import ServerManagerService
    from jarvis.agents.health_agent.models import ProbeResult


class ServerManagerAgent(NetworkAgent):
    """Manages the lifecycle of registered servers and monitors their health."""

    def __init__(
        self,
        server_service: "ServerManagerService",
        logger: Optional[JarvisLogger] = None,
        monitor_interval: float = 15.0,
    ) -> None:
        super().__init__("ServerManagerAgent", logger)
        self.server_service = server_service
        self._monitor_interval = monitor_interval
        self._monitor_task: Optional[asyncio.Task] = None
        self._booted = False
        self._latest_probes: List["ProbeResult"] = []
        self.intent_map: Dict[str, Any] = {
            "start_server": self._handle_start_server,
            "stop_server": self._handle_stop_server,
            "restart_server": self._handle_restart_server,
            "server_status": self._handle_server_status,
            "list_servers": self._handle_list_servers,
        }

    @property
    def description(self) -> str:
        return (
            "Manages server lifecycle — start, stop, restart, monitor health "
            "of both managed subprocesses and external services."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {"start_server", "stop_server", "restart_server", "server_status", "list_servers"}

    @property
    def supports_dialogue(self) -> bool:
        return False

    # -- Lifecycle --------------------------------------------------------------

    def set_network(self, network: AgentNetwork) -> None:
        """Start background monitor when network is attached."""
        super().set_network(network)
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background monitor and all managed servers."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await self.server_service.stop_all()

    # -- Message handlers ---------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        handler = self.intent_map.get(capability)
        if not handler:
            await self.send_error(
                message.from_agent,
                f"Unknown capability: {capability}",
                message.request_id,
            )
            return

        result = await handler(data)
        await self.send_capability_response(
            message.from_agent,
            result.to_dict(),
            message.request_id,
            message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        pass  # ServerManagerAgent never sends sub-requests

    # -- Capability implementations -----------------------------------------

    async def _handle_start_server(self, data: Dict[str, Any]) -> AgentResponse:
        """Start a managed server."""
        name = data.get("prompt", "").strip()
        if not name:
            # Try to extract server name from the prompt text
            name = self._extract_server_name(data)
        if not name:
            return AgentResponse.error_response(
                response="Which server would you like me to start? I need a name.",
                error=ErrorInfo(message="No server name provided", error_type="ValueError"),
            )

        try:
            state = await self.server_service.start_server(name)
            return AgentResponse.success_response(
                response=f"Server '{name}' started — PID {state.pid}.",
                data=state.to_dict(),
                metadata={"agent": "server_manager", "capability": "start_server"},
            )
        except KeyError:
            return AgentResponse.error_response(
                response=f"No server named '{name}' in the registry.",
                error=ErrorInfo(message=f"Unknown server: {name}", error_type="KeyError"),
            )
        except ValueError as exc:
            return AgentResponse.error_response(
                response=str(exc),
                error=ErrorInfo(message=str(exc), error_type="ValueError"),
            )
        except Exception as exc:
            return AgentResponse.error_response(
                response=f"Failed to start '{name}': {exc}",
                error=ErrorInfo.from_exception(exc),
            )

    async def _handle_stop_server(self, data: Dict[str, Any]) -> AgentResponse:
        """Stop a managed server."""
        name = data.get("prompt", "").strip()
        if not name:
            name = self._extract_server_name(data)
        if not name:
            return AgentResponse.error_response(
                response="Which server should I stop?",
                error=ErrorInfo(message="No server name provided", error_type="ValueError"),
            )

        try:
            state = await self.server_service.stop_server(name)
            return AgentResponse.success_response(
                response=f"Server '{name}' stopped. Exit code: {state.last_exit_code}.",
                data=state.to_dict(),
                metadata={"agent": "server_manager", "capability": "stop_server"},
            )
        except KeyError:
            return AgentResponse.error_response(
                response=f"No server named '{name}' in the registry.",
                error=ErrorInfo(message=f"Unknown server: {name}", error_type="KeyError"),
            )
        except ValueError as exc:
            return AgentResponse.error_response(
                response=str(exc),
                error=ErrorInfo(message=str(exc), error_type="ValueError"),
            )

    async def _handle_restart_server(self, data: Dict[str, Any]) -> AgentResponse:
        """Restart a managed server."""
        name = data.get("prompt", "").strip()
        if not name:
            name = self._extract_server_name(data)
        if not name:
            return AgentResponse.error_response(
                response="Which server should I restart?",
                error=ErrorInfo(message="No server name provided", error_type="ValueError"),
            )

        try:
            state = await self.server_service.restart_server(name)
            return AgentResponse.success_response(
                response=f"Server '{name}' restarted — PID {state.pid}.",
                data=state.to_dict(),
                metadata={"agent": "server_manager", "capability": "restart_server"},
            )
        except KeyError:
            return AgentResponse.error_response(
                response=f"No server named '{name}' in the registry.",
                error=ErrorInfo(message=f"Unknown server: {name}", error_type="KeyError"),
            )
        except ValueError as exc:
            return AgentResponse.error_response(
                response=str(exc),
                error=ErrorInfo(message=str(exc), error_type="ValueError"),
            )

    async def _handle_server_status(self, data: Dict[str, Any]) -> AgentResponse:
        """Get status of a specific server."""
        name = data.get("prompt", "").strip()
        if not name:
            name = self._extract_server_name(data)
        if not name:
            return AgentResponse.error_response(
                response="Which server would you like the status of?",
                error=ErrorInfo(message="No server name provided", error_type="ValueError"),
            )

        state = self.server_service.get_server(name)
        if not state:
            return AgentResponse.error_response(
                response=f"No server named '{name}' in the registry.",
                error=ErrorInfo(message=f"Unknown server: {name}", error_type="KeyError"),
            )

        response = self._format_server_status(state)
        return AgentResponse.success_response(
            response=response,
            data=state.to_dict(),
            metadata={"agent": "server_manager", "capability": "server_status"},
        )

    async def _handle_list_servers(self, data: Dict[str, Any]) -> AgentResponse:
        """List all registered servers."""
        servers = self.server_service.servers
        if not servers:
            return AgentResponse.success_response(
                response="No servers registered. The registry is empty.",
                data={"servers": []},
                metadata={"agent": "server_manager", "capability": "list_servers"},
            )

        lines = []
        for name, state in servers.items():
            mode = state.config.mode.value
            status = state.status.value.upper()
            port_info = f":{state.config.port}" if state.config.port else ""
            pid_info = f" (PID {state.pid})" if state.pid else ""
            lines.append(f"  {name} [{mode}] — {status}{port_info}{pid_info}")

        running = sum(1 for s in servers.values() if s.status.value == "running")
        summary = f"{len(servers)} server(s) registered, {running} running."

        return AgentResponse.success_response(
            response=f"{summary}\n" + "\n".join(lines),
            data={"servers": [s.to_dict() for s in servers.values()]},
            metadata={"agent": "server_manager", "capability": "list_servers"},
        )

    # -- Health probes for HealthAgent integration ---------------------------

    async def get_health_probes(self) -> List["ProbeResult"]:
        """Return latest health probe results for all servers.

        Called by HealthAgent during _build_snapshot().
        """
        return list(self._latest_probes)

    # -- Background monitor loop --------------------------------------------

    async def _monitor_loop(self) -> None:
        """Continuously monitor server health and handle crashes."""
        while True:
            try:
                # First iteration: boot startup servers
                if not self._booted:
                    try:
                        started = await self.server_service.start_boot_servers()
                        if started:
                            self.logger.log(
                                "INFO",
                                "Boot servers started",
                                ", ".join(started),
                            )
                    except Exception as exc:
                        self.logger.log("WARNING", "Boot server error", str(exc))
                    self._booted = True

                await asyncio.sleep(self._monitor_interval)

                # Detect crashed managed processes
                crashed = await self.server_service.detect_crashes()
                for name in crashed:
                    await self._notify_crash(name)
                    await self.server_service.maybe_auto_restart(name)

                # Health check all servers
                probes = await self.server_service.check_all_health()
                self._latest_probes = probes

                # Detect unhealthy transitions
                for probe in probes:
                    if probe.status.value == "unhealthy":
                        server_name = probe.component.replace("server:", "")
                        state = self.server_service.get_server(server_name)
                        if state and state.config.mode.value == "managed":
                            await self.server_service.maybe_auto_restart(server_name)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.log("ERROR", "Server monitor error", str(exc))

    async def _notify_crash(self, name: str) -> None:
        """Send error message to HealthAgent about a crashed server."""
        if not self.network:
            return
        if "HealthAgent" not in self.network.agents:
            return
        try:
            error_msg = Message(
                from_agent=self.name,
                to_agent="HealthAgent",
                message_type="error",
                content={"error": f"Server '{name}' has crashed"},
                request_id="",
            )
            await self.network.agents["HealthAgent"].receive_message(error_msg)
        except Exception:
            pass

    # -- Helpers ------------------------------------------------------------

    def _extract_server_name(self, data: Dict[str, Any]) -> str:
        """Try to extract a server name from various data fields."""
        prompt = data.get("prompt", "")
        # Common patterns: "start the calendar-api", "stop calendar server"
        # Just use the last word as a heuristic
        words = prompt.strip().split()
        if words:
            candidate = words[-1].strip("\"'")
            # Check if it matches a known server
            if self.server_service.get_server(candidate):
                return candidate
            # Try the whole prompt minus common verbs
            for word in words:
                clean = word.strip("\"'.,")
                if self.server_service.get_server(clean):
                    return clean
        return ""

    def _format_server_status(self, state) -> str:
        """Format a single server's status for human consumption."""
        from .models import ServerStatus
        c = state.config
        lines = [
            f"Server: {c.name}",
            f"Mode: {c.mode.value}",
            f"Status: {state.status.value.upper()}",
        ]
        if c.port:
            lines.append(f"Endpoint: {c.host}:{c.port}")
        if state.pid:
            lines.append(f"PID: {state.pid}")
        if state.started_at:
            lines.append(f"Started: {state.started_at.isoformat()}")
        if state.last_health_check:
            latency = f" ({state.last_health_latency_ms:.0f}ms)" if state.last_health_latency_ms else ""
            lines.append(f"Last health check: {state.last_health_check.isoformat()}{latency}")
        if state.restart_count > 0:
            lines.append(f"Restart count: {state.restart_count}/{c.max_restarts}")
        if state.error_message:
            lines.append(f"Error: {state.error_message}")
        return "\n".join(lines)
