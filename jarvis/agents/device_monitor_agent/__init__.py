"""DeviceMonitorAgent — watches over the hardware running Jarvis.

Capabilities:
    device_status      — quick snapshot of CPU, memory, disk, battery, thermals
    device_diagnostics — deep dive with top processes and zombie detection
    device_cleanup     — clear temp files, kill runaway processes
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...logging import JarvisLogger
from ...services.device_monitor_service import (
    DeviceMonitorService,
    Severity,
)


class DeviceMonitorAgent(NetworkAgent):
    """Monitors the physical hardware running Jarvis and takes corrective action."""

    def __init__(
        self,
        device_service: Optional[DeviceMonitorService] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__("DeviceMonitorAgent", logger)
        self.device_service = device_service or DeviceMonitorService()
        self.intent_map: Dict[str, Any] = {
            "device_status": self._handle_device_status,
            "device_diagnostics": self._handle_device_diagnostics,
            "device_cleanup": self._handle_device_cleanup,
        }

    @property
    def description(self) -> str:
        return (
            "Monitors host hardware health — CPU, memory, disk, battery, "
            "thermals — and can clear temp files or kill runaway processes."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {"device_status", "device_diagnostics", "device_cleanup"}

    @property
    def supports_dialogue(self) -> bool:
        return False

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

    async def _handle_capability_response(self, message: Message) -> None:  # noqa: ARG002
        pass  # DeviceMonitorAgent never sends sub-requests

    # -- Capability implementations -----------------------------------------

    async def _handle_device_status(self, data: Dict[str, Any]) -> AgentResponse:
        """Quick hardware snapshot."""
        snap = self.device_service.snapshot()
        response_text = self._format_snapshot(snap)
        return AgentResponse.success_response(
            response=response_text,
            data=snap.to_dict(),
            metadata={"agent": "device_monitor", "capability": "device_status"},
        )

    async def _handle_device_diagnostics(self, data: Dict[str, Any]) -> AgentResponse:
        """Deep dive — snapshot plus process analysis."""
        snap = self.device_service.snapshot()
        top_by_mem = self.device_service.top_processes(by="memory", limit=5)
        top_by_cpu = self.device_service.top_processes(by="cpu", limit=5)
        zombies = self.device_service.get_zombie_processes()

        lines = [self._format_snapshot(snap)]

        if top_by_cpu:
            lines.append("\nTop processes by CPU:")
            for p in top_by_cpu:
                lines.append(f"  {p.name} (PID {p.pid}) — {p.cpu_percent:.1f}% CPU, {p.memory_mb:.0f} MB RAM")

        if top_by_mem:
            lines.append("\nTop processes by memory:")
            for p in top_by_mem:
                lines.append(f"  {p.name} (PID {p.pid}) — {p.memory_mb:.0f} MB RAM, {p.cpu_percent:.1f}% CPU")

        if zombies:
            lines.append(f"\nZombie processes detected: {len(zombies)}")
            for z in zombies:
                lines.append(f"  {z.name} (PID {z.pid}) — {z.status}")

        diag_data = snap.to_dict()
        diag_data["top_by_cpu"] = [p.to_dict() for p in top_by_cpu]
        diag_data["top_by_memory"] = [p.to_dict() for p in top_by_mem]
        diag_data["zombies"] = [z.to_dict() for z in zombies]

        return AgentResponse.success_response(
            response="\n".join(lines),
            data=diag_data,
            metadata={"agent": "device_monitor", "capability": "device_diagnostics"},
        )

    async def _handle_device_cleanup(self, data: Dict[str, Any]) -> AgentResponse:
        """Clear temp files and report zombie processes.

        Process killing requires an explicit PID in data["kill_pid"].
        We don't kill processes unprompted — that would be rude.
        """
        actions = []
        lines = []

        # Clear temp files
        result = self.device_service.clear_temp_files()
        actions.append({"type": "temp_cleanup", "details": result})
        if result["cleared"] > 0:
            lines.append(
                f"Cleared {result['cleared']} temp files, freed {result['freed_mb']} MB."
            )
        else:
            lines.append("Temp directory is already tidy. Nothing to clear.")

        # Kill specific process if requested
        kill_pid = data.get("kill_pid")
        if kill_pid is not None:
            try:
                pid = int(kill_pid)
            except (ValueError, TypeError):
                return AgentResponse.error_response(
                    response=f"Invalid PID: {kill_pid}",
                    error=ErrorInfo(message=f"Invalid PID: {kill_pid}", error_type="ValueError"),
                )
            kill_result = self.device_service.kill_process(pid)
            actions.append({"type": "process_kill", "details": kill_result})
            if kill_result["success"]:
                lines.append(f"Terminated process {kill_result['name']} (PID {pid}).")
            else:
                lines.append(f"Could not terminate PID {pid}: {kill_result['error']}")

        # Report zombies as a courtesy
        zombies = self.device_service.get_zombie_processes()
        if zombies:
            lines.append(f"\n{len(zombies)} zombie process(es) lingering:")
            for z in zombies:
                lines.append(f"  {z.name} (PID {z.pid})")
            lines.append("Provide a PID to terminate any of these.")

        return AgentResponse.success_response(
            response="\n".join(lines),
            actions=actions,
            data={"zombies": [z.to_dict() for z in zombies]},
            metadata={"agent": "device_monitor", "capability": "device_cleanup"},
        )

    # -- Formatting ----------------------------------------------------------

    def _format_snapshot(self, snap) -> str:
        """Build a concise human-readable summary from a DeviceSnapshot."""
        svc = self.device_service
        lines = [f"Host: {snap.hostname} ({snap.platform})"]

        if snap.uptime_seconds:
            lines.append(f"Uptime: {svc.format_uptime(snap.uptime_seconds)}")

        # CPU
        for m in snap.cpu:
            if m.name == "cpu_overall":
                cores = m.details.get("core_count", "?")
                lines.append(f"CPU: {m.value:.1f}% across {cores} cores")
            elif m.name == "load_average" and isinstance(m.value, dict):
                lines.append(
                    f"Load: {m.value['1m']:.2f} / {m.value['5m']:.2f} / {m.value['15m']:.2f}"
                )

        # Memory
        for m in snap.memory:
            if m.name == "ram":
                total = m.details.get("total_gb", "?")
                avail = m.details.get("available_gb", "?")
                lines.append(f"Memory: {m.value:.1f}% used ({avail} GB free of {total} GB)")
            elif m.name == "swap" and m.value > 0:
                lines.append(f"Swap: {m.value:.1f}% used")

        # Disk
        for m in snap.disk:
            free = m.details.get("free_gb", "?")
            total = m.details.get("total_gb", "?")
            lines.append(f"Disk [{m.name}]: {m.value:.1f}% used ({free} GB free of {total} GB)")

        # Battery
        if snap.battery:
            b = snap.battery
            plug = "plugged in" if b.details.get("plugged_in") else "on battery"
            lines.append(f"Battery: {b.value}% ({plug})")

        # Thermals
        for m in snap.thermals:
            lines.append(f"Temp [{m.name}]: {m.value:.0f}°C")

        # Overall verdict
        if snap.overall_severity == Severity.CRITICAL:
            lines.append("\nVerdict: something is on fire. Immediate attention required.")
        elif snap.overall_severity == Severity.WARNING:
            lines.append("\nVerdict: a few concerns worth noting.")
        else:
            lines.append("\nVerdict: all systems nominal.")

        return "\n".join(lines)
