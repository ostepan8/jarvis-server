"""DeviceMonitorAgent — watches over the hardware running Jarvis.

Capabilities:
    device_status      — quick snapshot of CPU, memory, disk, battery, thermals
    device_diagnostics — deep dive with top processes and zombie detection
    device_cleanup     — clear temp files, kill runaway processes
    device_history     — query historical metrics and return trends summary
"""

from __future__ import annotations

import asyncio
import platform
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..agent_network import AgentNetwork
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...logging import JarvisLogger
from ...services.device_monitor_service import (
    DeviceMonitorService,
    Severity,
)
from ...services.metrics_store import MetricsStore


class DeviceMonitorAgent(NetworkAgent):
    """Monitors the physical hardware running Jarvis and takes corrective action."""

    def __init__(
        self,
        device_service: Optional[DeviceMonitorService] = None,
        metrics_store: Optional[MetricsStore] = None,
        logger: Optional[JarvisLogger] = None,
        probe_interval: float = 30.0,
    ) -> None:
        super().__init__("DeviceMonitorAgent", logger)
        self.device_service = device_service or DeviceMonitorService()
        self.metrics_store = metrics_store
        self._probe_interval = probe_interval
        self._monitor_task: Optional[asyncio.Task] = None
        self._component_statuses: Dict[str, str] = {}  # component -> severity string
        self._consecutive_high_cpu: int = 0
        self._tick_count: int = 0
        self.intent_map: Dict[str, Any] = {
            "device_status": self._handle_device_status,
            "device_diagnostics": self._handle_device_diagnostics,
            "device_cleanup": self._handle_device_cleanup,
            "device_history": self._handle_device_history,
        }

    @property
    def description(self) -> str:
        return (
            "Monitors host hardware health — CPU, memory, disk, battery, "
            "thermals — and can clear temp files or kill runaway processes."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {"device_status", "device_diagnostics", "device_cleanup", "device_history"}

    @property
    def supports_dialogue(self) -> bool:
        return False

    # -- Lifecycle --------------------------------------------------------------

    def set_network(self, network: AgentNetwork) -> None:
        """Override to start the background monitor when network is set."""
        super().set_network(network)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop — caller will start later
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background monitor."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

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

    async def _handle_device_history(self, data: Dict[str, Any]) -> AgentResponse:
        """Query historical metrics and return trends summary."""
        if not self.metrics_store:
            return AgentResponse.error_response(
                response="Historical data not available — MetricsStore not configured.",
                error=ErrorInfo(
                    message="MetricsStore not configured",
                    error_type="ConfigError",
                ),
            )

        component = data.get("component", "cpu")
        metric_name = data.get("metric_name")
        hours = int(data.get("hours", 24))

        from datetime import timedelta
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)

        # Choose resolution: raw for < 6h, hourly for >= 6h
        if hours < 6:
            rows = self.metrics_store.query(
                component=component,
                metric_name=metric_name,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            resolution = "raw"
        else:
            rows = self.metrics_store.query_aggregated(
                component=component,
                metric_name=metric_name,
                start=start.isoformat(),
                end=end.isoformat(),
            )
            resolution = "hourly"

        if not rows:
            return AgentResponse.success_response(
                response=f"No historical data for {component} in the last {hours} hours.",
                data={"component": component, "hours": hours, "data": []},
                metadata={"agent": "device_monitor", "capability": "device_history"},
            )

        # Compute summary statistics
        if resolution == "raw":
            values = [r["value"] for r in rows]
        else:
            values = [r["avg_value"] for r in rows if r.get("avg_value") is not None]

        if not values:
            return AgentResponse.success_response(
                response=f"Aggregated data available for {component} but no numeric values to summarize.",
                data={
                    "component": component, "hours": hours, "resolution": resolution,
                    "min": None, "max": None, "avg": None, "current": None,
                    "trend": "unknown", "sample_count": len(rows), "data": rows,
                },
                metadata={"agent": "device_monitor", "capability": "device_history"},
            )

        min_val = float(min(values))
        max_val = float(max(values))
        avg_val = sum(values) / len(values)
        current = float(values[-1])

        if current > avg_val * 1.1:
            trend = "rising"
        elif current < avg_val * 0.9:
            trend = "falling"
        else:
            trend = "stable"

        summary = (
            f"{component} over the last {hours}h: "
            f"min {min_val:.1f}, max {max_val:.1f}, avg {avg_val:.1f}, "
            f"current {current:.1f} — trend: {trend}."
        )

        return AgentResponse.success_response(
            response=summary,
            data={
                "component": component, "hours": hours, "resolution": resolution,
                "min": min_val, "max": max_val, "avg": avg_val,
                "current": current, "trend": trend,
                "sample_count": len(rows), "data": rows,
            },
            metadata={"agent": "device_monitor", "capability": "device_history"},
        )

    # -- Background monitor loop --------------------------------------------

    async def _monitor_loop(self) -> None:
        """Continuously poll hardware metrics, detect transitions, broadcast alerts."""
        while True:
            try:
                await asyncio.sleep(self._probe_interval)
                self._tick_count += 1

                # Collect snapshot
                snap = self.device_service.snapshot()

                # Record metrics to store
                if self.metrics_store:
                    self._record_snapshot(snap)

                # Detect transitions and broadcast alerts
                await self._process_transitions(snap)

                # Auto-corrective actions on critical thresholds
                await self._auto_correct(snap)

                # Slow metrics every 10th tick (~5 min at 30s interval)
                if self._tick_count % 10 == 0 and self.metrics_store:
                    self._record_slow_metrics()

                # Compaction every 120th tick (~1 hour)
                if self._tick_count % 120 == 0 and self.metrics_store:
                    try:
                        self.metrics_store.compact()
                    except Exception:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.log("ERROR", "Device monitor error", str(exc))

    # -- Metrics recording ---------------------------------------------------

    def _record_snapshot(self, snap) -> None:
        """Batch-insert snapshot metrics into the MetricsStore."""
        now = datetime.now(timezone.utc).isoformat()
        rows: List[Dict[str, Any]] = []

        # CPU
        for m in snap.cpu:
            if m.name == "cpu_overall":
                rows.append({
                    "timestamp": now, "component": "cpu", "metric_name": "cpu_overall",
                    "value": float(m.value) if m.value is not None else 0.0,
                    "unit": "%", "severity": m.severity.value,
                })

        # Memory
        for m in snap.memory:
            if m.name == "ram":
                rows.append({
                    "timestamp": now, "component": "memory", "metric_name": "ram_percent",
                    "value": float(m.value), "unit": "%", "severity": m.severity.value,
                })

        # Disk
        for m in snap.disk:
            rows.append({
                "timestamp": now, "component": "disk", "metric_name": f"disk_{m.name}",
                "value": float(m.value), "unit": "%", "severity": m.severity.value,
            })

        # Battery
        if snap.battery:
            rows.append({
                "timestamp": now, "component": "battery", "metric_name": "battery_percent",
                "value": float(snap.battery.value), "unit": "%",
                "severity": snap.battery.severity.value,
            })

        # Thermals
        for m in snap.thermals:
            rows.append({
                "timestamp": now, "component": "thermal", "metric_name": f"thermal_{m.name}",
                "value": float(m.value), "unit": "°C", "severity": m.severity.value,
            })

        # Disk I/O
        for m in snap.disk_io:
            rows.append({
                "timestamp": now, "component": "disk_io", "metric_name": m.name,
                "value": float(m.value), "unit": m.unit, "severity": m.severity.value,
            })

        # Network I/O
        for m in snap.network_io:
            rows.append({
                "timestamp": now, "component": "network_io", "metric_name": m.name,
                "value": float(m.value), "unit": m.unit, "severity": m.severity.value,
            })

        store = self.metrics_store
        if rows and store:
            try:
                store.record_batch(rows)
            except Exception as exc:
                self.logger.log("WARNING", "Failed to record metrics", str(exc))

    def _record_slow_metrics(self) -> None:
        """Record infrequent metrics (battery health, thermals) every ~5 min."""
        now = datetime.now(timezone.utc).isoformat()
        rows: List[Dict[str, Any]] = []

        batt_health = self.device_service.get_battery_health()
        if batt_health:
            if "cycle_count" in batt_health:
                rows.append({
                    "timestamp": now, "component": "battery",
                    "metric_name": "cycle_count",
                    "value": float(batt_health["cycle_count"]),
                    "unit": "cycles", "severity": "ok",
                })
            if "temperature_c" in batt_health:
                rows.append({
                    "timestamp": now, "component": "battery",
                    "metric_name": "battery_temp",
                    "value": float(batt_health["temperature_c"]),
                    "unit": "°C", "severity": "ok",
                })

        thermal = self.device_service.get_thermal_status()
        if thermal and "thermal_level" in thermal:
            level = thermal["thermal_level"]
            sev = "ok" if level == 0 else ("warning" if level < 70 else "critical")
            rows.append({
                "timestamp": now, "component": "thermal",
                "metric_name": "thermal_level",
                "value": float(level), "unit": "", "severity": sev,
            })

        if rows and self.metrics_store:
            try:
                self.metrics_store.record_batch(rows)
            except Exception:
                pass

    # -- Transition detection ------------------------------------------------

    async def _process_transitions(self, snap) -> None:
        """Detect severity transitions and broadcast alerts on changes."""
        components: Dict[str, str] = {}

        # Aggregate worst severity per component
        for m in snap.cpu:
            if m.name == "cpu_overall":
                components["cpu"] = m.severity.value
        for m in snap.memory:
            if m.name == "ram":
                components["memory"] = m.severity.value
        for m in snap.disk:
            components[f"disk:{m.name}"] = m.severity.value
        if snap.battery:
            components["battery"] = snap.battery.severity.value
        for m in snap.thermals:
            components[f"thermal:{m.name}"] = m.severity.value

        for component, new_sev in components.items():
            old_sev = self._component_statuses.get(component)
            self._component_statuses[component] = new_sev

            if old_sev is None:
                continue  # First probe

            if old_sev == new_sev:
                continue  # No change

            # Transition detected
            is_degradation = (
                (old_sev == "ok" and new_sev in ("warning", "critical"))
                or (old_sev == "warning" and new_sev == "critical")
            )
            is_recovery = (
                (old_sev in ("warning", "critical") and new_sev == "ok")
                or (old_sev == "critical" and new_sev == "warning")
            )

            if is_degradation or is_recovery:
                details = f"{component} transitioned from {old_sev} to {new_sev}"
                await self._broadcast_health_alert(component, old_sev, new_sev, details)

                # macOS notification on degradation
                if is_degradation:
                    self._send_macos_notification(
                        f"Device Alert: {component}",
                        f"{component} is now {new_sev.upper()}",
                    )

    # -- Alert broadcasting --------------------------------------------------

    async def _broadcast_health_alert(
        self,
        component: str,
        old_severity: str,
        new_severity: str,
        details: str,
    ) -> None:
        """Broadcast a health_alert to all agents via the network."""
        if not self.network:
            return
        alert_content = {
            "alert_type": "status_change",
            "source": "device_monitor",
            "component": component,
            "old_status": old_severity,
            "new_status": new_severity,
            "details": details,
        }
        for agent_name, agent in self.network.agents.items():
            if agent_name != self.name:
                try:
                    alert_msg = Message(
                        from_agent=self.name,
                        to_agent=agent_name,
                        message_type="health_alert",
                        content=alert_content,
                        request_id="",
                    )
                    await agent.receive_message(alert_msg)
                except Exception:
                    pass

    # -- macOS native notifications ------------------------------------------

    def _send_macos_notification(self, title: str, message: str) -> None:
        """Push a native macOS notification via osascript. No-op on other platforms."""
        if platform.system() != "Darwin":
            return
        try:
            import subprocess
            # Sanitize inputs to prevent command injection
            safe_title = title.replace('"', '\\"').replace("'", "")
            safe_message = message.replace('"', '\\"').replace("'", "")
            subprocess.Popen(
                [
                    "osascript", "-e",
                    f'display notification "{safe_message}" with title "{safe_title}"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # -- Auto-corrective actions ---------------------------------------------

    async def _auto_correct(self, snap) -> None:
        """Take safe, reversible corrective actions on critical thresholds."""
        # Disk > 95%: auto-clear temp files
        for m in snap.disk:
            if m.severity == Severity.CRITICAL:
                result = self.device_service.clear_temp_files()
                if result["cleared"] > 0:
                    self.logger.log(
                        "INFO",
                        "Auto-cleanup triggered",
                        f"Cleared {result['cleared']} temp files, freed {result['freed_mb']} MB",
                    )
                break  # Only clean once per tick

        # CPU > 90% sustained (3+ consecutive polls): alert with top consumers
        cpu_metric = next((m for m in snap.cpu if m.name == "cpu_overall"), None)
        if cpu_metric and cpu_metric.severity == Severity.CRITICAL:
            self._consecutive_high_cpu += 1
            if self._consecutive_high_cpu >= 3:
                top_procs = self.device_service.top_processes(by="cpu", limit=5)
                proc_summary = ", ".join(
                    f"{p.name}({p.cpu_percent:.0f}%)" for p in top_procs
                )
                self.logger.log(
                    "WARNING",
                    "Sustained high CPU",
                    f"Top consumers: {proc_summary}",
                )
        else:
            self._consecutive_high_cpu = 0

        # Memory > 95% (CRITICAL): alert with top memory consumers
        for m in snap.memory:
            if m.name == "ram" and m.severity == Severity.CRITICAL:
                top_procs = self.device_service.top_processes(by="memory", limit=5)
                proc_summary = ", ".join(
                    f"{p.name}({p.memory_mb:.0f}MB)" for p in top_procs
                )
                self.logger.log(
                    "WARNING",
                    "Critical memory pressure",
                    f"Top consumers: {proc_summary}",
                )
                break

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
