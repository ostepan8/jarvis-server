from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Set

from ..base import NetworkAgent
from ..agent_network import AgentNetwork
from ..message import Message
from ..response import AgentResponse
from ...logging import JarvisLogger
from ...services.health_service import HealthService
from .models import (
    ComponentStatus,
    IncidentRecord,
    IncidentSeverity,
    SystemHealthSnapshot,
    ProbeResult,
)
from .probes import probe_agents, probe_network
from .dependency_map import build_dependency_graph
from .report_writer import ReportWriter


class HealthAgent(NetworkAgent):
    """Monitors system health continuously without requiring an AI client."""

    def __init__(
        self,
        health_service: HealthService,
        logger: Optional[JarvisLogger] = None,
        probe_interval: float = 60.0,
        report_interval: float = 3600.0,
        report_dir: Optional[str] = None,
    ):
        super().__init__("HealthAgent", logger)
        self.health_service = health_service
        self._probe_interval = probe_interval
        self._report_interval = report_interval
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_snapshot: Optional[SystemHealthSnapshot] = None
        self._component_statuses: Dict[str, ComponentStatus] = {}
        self._incidents: List[IncidentRecord] = []
        self._error_counts: Dict[str, int] = {}
        self.report_writer = ReportWriter(report_dir)

        self.intent_map = {
            "system_health_check": self._system_health_check,
            "agent_health_status": self._agent_health_status,
            "service_health_status": self._service_health_status,
            "system_resource_status": self._system_resource_status,
            "health_report": self._health_report,
            "dependency_map": self._dependency_map,
            "incident_list": self._incident_list,
        }

    @property
    def description(self) -> str:
        return (
            "Monitors system health, probes agents/services/resources, "
            "tracks incidents, and generates health reports."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {
            "system_health_check",
            "agent_health_status",
            "service_health_status",
            "system_resource_status",
            "health_report",
            "dependency_map",
            "incident_list",
        }

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

    # ------------------------------------------------------------------
    # Background monitor
    # ------------------------------------------------------------------
    async def _monitor_loop(self) -> None:
        """Continuously probe the system and track health."""
        last_report_time = datetime.now()
        while True:
            try:
                await asyncio.sleep(self._probe_interval)
                snapshot = await self._build_snapshot()
                self._last_snapshot = snapshot

                # Track status transitions and manage incidents
                await self._process_transitions(snapshot)

                # Write status file
                try:
                    self.report_writer.write_status_file(snapshot)
                except Exception as exc:
                    self.logger.log("WARNING", "Failed to write status file", str(exc))

                # Periodic daily report
                now = datetime.now()
                if (now - last_report_time).total_seconds() >= self._report_interval:
                    last_report_time = now
                    try:
                        self.report_writer.cleanup_old_reports()
                    except Exception:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.log("ERROR", "Health monitor error", str(exc))

    async def _build_snapshot(self) -> SystemHealthSnapshot:
        """Build a full system health snapshot."""
        agent_statuses = probe_agents(self.network)
        network_statuses = probe_network(self.network)

        # Resource probes
        resource_statuses = []
        loop_lag = await self.health_service.get_event_loop_lag()
        resource_statuses.append(loop_lag)

        cpu = self.health_service.get_cpu_usage()
        resource_statuses.append(cpu)
        mem = self.health_service.get_memory_usage()
        resource_statuses.append(mem)
        disk = self.health_service.get_disk_usage()
        resource_statuses.append(disk)

        # Service probes
        service_statuses = []
        service_statuses.append(await self.health_service.probe_calendar_api())
        sqlite_result = await self.health_service.probe_sqlite()
        service_statuses.append(sqlite_result)

        # Managed server probes (from ServerManagerAgent)
        if self.network and "ServerManagerAgent" in self.network.agents:
            try:
                server_agent = self.network.agents["ServerManagerAgent"]
                server_probes = await server_agent.get_health_probes()
                service_statuses.extend(server_probes)
            except Exception:
                pass

        # Network metrics
        network_metrics = None
        if self.network:
            network_metrics = self.network.get_metrics()

        # Compute overall status
        all_results = agent_statuses + service_statuses + resource_statuses + network_statuses
        overall = self._compute_overall_status(all_results)

        # Active incidents
        active = [i for i in self._incidents if i.is_active]

        # Summary
        healthy_count = sum(1 for r in all_results if r.status == ComponentStatus.HEALTHY)
        total = len(all_results)
        summary = f"{healthy_count}/{total} components healthy"
        if active:
            summary += f", {len(active)} active incident(s)"

        return SystemHealthSnapshot(
            overall_status=overall,
            agent_statuses=agent_statuses,
            service_statuses=service_statuses,
            resource_statuses=resource_statuses,
            network_metrics=network_metrics,
            active_incidents=active,
            summary=summary,
        )

    def _compute_overall_status(self, results: List[ProbeResult]) -> ComponentStatus:
        """Compute overall system status from all probe results."""
        if not results:
            return ComponentStatus.UNKNOWN

        statuses = [r.status for r in results]
        if any(s == ComponentStatus.UNHEALTHY for s in statuses):
            return ComponentStatus.UNHEALTHY
        if any(s == ComponentStatus.DEGRADED for s in statuses):
            return ComponentStatus.DEGRADED
        if all(s == ComponentStatus.UNKNOWN for s in statuses):
            return ComponentStatus.UNKNOWN
        return ComponentStatus.HEALTHY

    async def _process_transitions(self, snapshot: SystemHealthSnapshot) -> None:
        """Detect status transitions and manage incidents."""
        all_results = (
            snapshot.agent_statuses
            + snapshot.service_statuses
            + snapshot.resource_statuses
        )

        for result in all_results:
            old_status = self._component_statuses.get(result.component)
            new_status = result.status
            self._component_statuses[result.component] = new_status

            if old_status is None:
                continue  # First probe, no transition

            if old_status == new_status:
                continue  # No change

            # Status transition detected
            if (
                new_status in (ComponentStatus.DEGRADED, ComponentStatus.UNHEALTHY)
                and old_status == ComponentStatus.HEALTHY
            ):
                # Open incident
                severity = (
                    IncidentSeverity.ERROR
                    if new_status == ComponentStatus.UNHEALTHY
                    else IncidentSeverity.WARNING
                )
                incident = IncidentRecord(
                    component=result.component,
                    severity=severity,
                    title=f"{result.component} is {new_status.value}",
                    description=result.message,
                    probe_results=[result],
                )
                self._incidents.append(incident)
                try:
                    self.report_writer.write_incident_report(incident)
                except Exception:
                    pass
                await self._broadcast_health_alert(
                    result.component, old_status, new_status, result.message
                )

            elif (
                new_status == ComponentStatus.HEALTHY
                and old_status in (ComponentStatus.DEGRADED, ComponentStatus.UNHEALTHY)
            ):
                # Resolve incidents for this component
                for inc in self._incidents:
                    if inc.component == result.component and inc.is_active:
                        inc.resolved_at = datetime.now()
                        inc.actions_taken.append("Auto-resolved: component returned to healthy")
                        try:
                            self.report_writer.update_incident_report(inc)
                        except Exception:
                            pass
                await self._broadcast_health_alert(
                    result.component, old_status, new_status, "Recovered"
                )

    async def _broadcast_health_alert(
        self,
        component: str,
        old_status: ComponentStatus,
        new_status: ComponentStatus,
        details: str,
    ) -> None:
        """Broadcast a health_alert to all agents."""
        if not self.network:
            return
        active = [i.to_dict() for i in self._incidents if i.is_active]
        alert_content = {
            "alert_type": "status_change",
            "component": component,
            "old_status": old_status.value,
            "new_status": new_status.value,
            "details": details,
            "active_incidents": active,
        }
        # Deliver to all agents directly (broadcast)
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

    # ------------------------------------------------------------------
    # Error tracking (intercepts error messages passively)
    # ------------------------------------------------------------------
    async def _handle_error(self, message: Message) -> None:
        """Track error messages for failure rate monitoring."""
        component = message.from_agent
        self._error_counts[component] = self._error_counts.get(component, 0) + 1
        self.logger.log(
            "DEBUG",
            f"HealthAgent tracked error from {component}",
            f"Total errors: {self._error_counts[component]}",
        )

    # ------------------------------------------------------------------
    # Capability handlers
    # ------------------------------------------------------------------
    async def _handle_capability_request(self, message: Message) -> None:
        """Route capability requests to handlers."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        prompt = data.get("prompt", "")

        handler = self.intent_map.get(capability)
        if not handler:
            await self.send_error(
                message.from_agent,
                f"Unknown health capability: {capability}",
                message.request_id,
            )
            return

        try:
            result = await handler(prompt=prompt, data=data)
            await self.send_capability_response(
                to_agent=message.from_agent,
                result=result.to_dict(),
                request_id=message.request_id,
                original_message_id=message.id,
            )
        except Exception as exc:
            await self.send_error(
                message.from_agent,
                f"Health check error: {exc}",
                message.request_id,
            )

    async def _system_health_check(self, **kwargs) -> AgentResponse:
        """Full system health snapshot."""
        snapshot = await self._build_snapshot()
        self._last_snapshot = snapshot

        all_results = (
            snapshot.agent_statuses
            + snapshot.service_statuses
            + snapshot.resource_statuses
        )
        healthy = sum(
            1 for r in all_results if r.status == ComponentStatus.HEALTHY
        )
        total = len(all_results)
        issues = [
            r for r in all_results if r.status != ComponentStatus.HEALTHY
        ]

        if snapshot.overall_status == ComponentStatus.HEALTHY:
            response = f"All systems operational — {total} components, all healthy."
        else:
            issue_summaries = [
                f"{r.component} ({r.message})" for r in issues
            ]
            if snapshot.overall_status == ComponentStatus.DEGRADED:
                response = (
                    f"Mostly operational, {healthy} of {total} components healthy. "
                    f"Showing some strain: {', '.join(issue_summaries)}."
                )
            else:
                response = (
                    f"Not at full strength — {healthy} of {total} components healthy. "
                    f"Issues with: {', '.join(issue_summaries[:5])}."
                )

        if snapshot.active_incidents:
            count = len(snapshot.active_incidents)
            response += (
                f" {count} active incident{'s' if count != 1 else ''} on record."
            )

        return AgentResponse(
            success=True,
            response=response,
            data=snapshot.to_dict(),
            metadata={"agent": "health"},
        )

    async def _agent_health_status(self, **kwargs) -> AgentResponse:
        """Health status of agents."""
        prompt = kwargs.get("prompt", "")
        agent_results = probe_agents(self.network)

        # Filter to specific agent if mentioned
        if prompt:
            specific = [r for r in agent_results if r.component.lower() in prompt.lower()]
            if specific:
                agent_results = specific

        statuses = [r.to_dict() for r in agent_results]
        healthy = sum(1 for r in agent_results if r.status == ComponentStatus.HEALTHY)

        if healthy == len(agent_results):
            response = f"All {healthy} agents responding normally."
        else:
            unhealthy = [
                r for r in agent_results
                if r.status != ComponentStatus.HEALTHY
            ]
            names = [r.component for r in unhealthy]
            verb = "is" if len(names) == 1 else "are"
            response = (
                f"{healthy} of {len(agent_results)} agents healthy. "
                f"{', '.join(names)} {verb} not responding as expected."
            )

        return AgentResponse(
            success=True,
            response=response,
            data={"agents": statuses},
            metadata={"agent": "health"},
        )

    async def _service_health_status(self, **kwargs) -> AgentResponse:
        """Health status of external services."""
        results = []
        results.append(await self.health_service.probe_calendar_api())
        results.append(await self.health_service.probe_sqlite())

        statuses = [r.to_dict() for r in results]
        healthy = sum(1 for r in results if r.status == ComponentStatus.HEALTHY)

        if healthy == len(results):
            names = [r.component for r in results]
            response = (
                f"All services online — {', '.join(names)} responding normally."
            )
        else:
            unhealthy = [
                r for r in results if r.status != ComponentStatus.HEALTHY
            ]
            summaries = [f"{r.component} ({r.message})" for r in unhealthy]
            response = (
                f"{healthy} of {len(results)} services healthy. "
                f"Issues: {', '.join(summaries)}."
            )

        return AgentResponse(
            success=True,
            response=response,
            data={"services": statuses},
            metadata={"agent": "health"},
        )

    async def _system_resource_status(self, **kwargs) -> AgentResponse:
        """CPU, memory, disk, event loop status."""
        results = [
            self.health_service.get_cpu_usage(),
            self.health_service.get_memory_usage(),
            self.health_service.get_disk_usage(),
            await self.health_service.get_event_loop_lag(),
        ]

        statuses = [r.to_dict() for r in results]
        overall = self._compute_overall_status(results)

        # Build conversational summary from probe details
        parts = []
        for r in results:
            details = r.details or {}
            if r.component == "CPU":
                pct = details.get("percent")
                if pct is not None:
                    parts.append(f"CPU at {pct:.0f}%")
            elif r.component == "Memory":
                pct = details.get("percent")
                if pct is not None:
                    parts.append(f"memory at {pct:.0f}%")
            elif r.component == "Disk":
                pct = details.get("percent")
                if pct is not None:
                    used = details.get("used_gb")
                    total = details.get("total_gb")
                    part = f"disk at {pct:.0f}%"
                    if used is not None and total is not None:
                        part += f" ({used}/{total} GB)"
                    parts.append(part)
            elif r.component == "EventLoop":
                if r.latency_ms is not None:
                    parts.append(f"event loop lag {r.latency_ms:.1f}ms")

        if overall == ComponentStatus.HEALTHY:
            opener = "Resources looking good"
        elif overall == ComponentStatus.DEGRADED:
            opener = "Resources under some pressure"
        else:
            opener = "Resource concerns detected"

        if parts:
            response = f"{opener} — {', '.join(parts)}."
        else:
            response = f"{opener}."

        return AgentResponse(
            success=True,
            response=response,
            data={"resources": statuses},
            metadata={"agent": "health"},
        )

    async def _health_report(self, **kwargs) -> AgentResponse:
        """Generate or retrieve a health report."""
        if self._last_snapshot:
            path = self.report_writer.write_status_file(self._last_snapshot)
            content = self.report_writer.read_report(path)
        else:
            snapshot = await self._build_snapshot()
            self._last_snapshot = snapshot
            path = self.report_writer.write_status_file(snapshot)
            content = self.report_writer.read_report(path)

        return AgentResponse(
            success=True,
            response=content or "No health report available.",
            data={"report_path": path},
            metadata={"agent": "health"},
        )

    async def _dependency_map(self, **kwargs) -> AgentResponse:
        """Generate dependency graph."""
        nodes = build_dependency_graph(self.network, self._component_statuses)
        path = self.report_writer.write_dependency_map(nodes)

        return AgentResponse(
            success=True,
            response=f"Dependency map generated — {len(nodes)} components mapped.",
            data={"nodes": [n.to_dict() for n in nodes], "report_path": path},
            metadata={"agent": "health"},
        )

    async def _incident_list(self, **kwargs) -> AgentResponse:
        """List active and recent incidents."""
        data = kwargs.get("data", {})
        active_only = "active" in data.get("prompt", "").lower()

        if active_only:
            incidents = [i for i in self._incidents if i.is_active]
        else:
            incidents = self._incidents[-20:]  # Last 20

        if not incidents:
            response = "No incidents on record. Quiet day."
        elif len(incidents) == 1:
            inc = incidents[0]
            status = "active" if inc.is_active else "resolved"
            response = (
                f"One incident: {inc.title} "
                f"({inc.severity.value}, {status})."
            )
        else:
            active = sum(1 for i in incidents if i.is_active)
            response = (
                f"{len(incidents)} incidents on record, "
                f"{active} currently active."
            )

        return AgentResponse(
            success=True,
            response=response,
            data={"incidents": [i.to_dict() for i in incidents]},
            metadata={"agent": "health"},
        )
