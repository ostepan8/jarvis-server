from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from .models import SystemHealthSnapshot, IncidentRecord, DependencyNode


class ReportWriter:
    """Writes health reports as markdown files."""

    def __init__(self, report_dir: Optional[str] = None):
        if report_dir:
            self.report_dir = Path(report_dir)
        else:
            self.report_dir = Path(__file__).parent / "reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "incidents").mkdir(exist_ok=True)
        (self.report_dir / "daily").mkdir(exist_ok=True)

    def write_status_file(self, snapshot: SystemHealthSnapshot) -> str:
        """Write current_status.md. Returns the file path."""
        path = self.report_dir / "current_status.md"
        lines = [
            "# System Health Status",
            f"**Updated:** {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Overall:** {snapshot.overall_status.value.upper()}",
            "",
        ]

        # Agents table
        if snapshot.agent_statuses:
            lines.append("## Agents")
            lines.append("| Agent | Status | Details |")
            lines.append("|-------|--------|---------|")
            for s in snapshot.agent_statuses:
                lines.append(f"| {s.component} | {s.status.value} | {s.message} |")
            lines.append("")

        # Services table
        if snapshot.service_statuses:
            lines.append("## Services")
            lines.append("| Service | Status | Latency | Details |")
            lines.append("|---------|--------|---------|---------|")
            for s in snapshot.service_statuses:
                lat = f"{s.latency_ms:.0f}ms" if s.latency_ms is not None else "N/A"
                lines.append(f"| {s.component} | {s.status.value} | {lat} | {s.message} |")
            lines.append("")

        # Resources table
        if snapshot.resource_statuses:
            lines.append("## Resources")
            lines.append("| Resource | Status | Details |")
            lines.append("|----------|--------|---------|")
            for s in snapshot.resource_statuses:
                lines.append(f"| {s.component} | {s.status.value} | {s.message} |")
            lines.append("")

        # Network metrics
        if snapshot.network_metrics:
            lines.append("## Network")
            for key, val in snapshot.network_metrics.items():
                if not isinstance(val, dict):
                    lines.append(f"- **{key}:** {val}")
            lines.append("")

        # Active incidents
        if snapshot.active_incidents:
            lines.append("## Active Incidents")
            for inc in snapshot.active_incidents:
                lines.append(f"- **[{inc.severity.value.upper()}]** {inc.title} (since {inc.started_at.strftime('%H:%M:%S')})")
            lines.append("")

        lines.append(f"**Summary:** {snapshot.summary}")
        path.write_text("\n".join(lines))
        return str(path)

    def write_incident_report(self, incident: IncidentRecord) -> str:
        """Write an incident report markdown file. Returns file path."""
        filename = f"{incident.started_at.strftime('%Y-%m-%d_%H-%M')}_{incident.component}_{incident.severity.value}.md"
        path = self.report_dir / "incidents" / filename
        lines = [
            f"# Incident: {incident.title}",
            "",
            f"- **ID:** {incident.id}",
            f"- **Component:** {incident.component}",
            f"- **Severity:** {incident.severity.value}",
            f"- **Started:** {incident.started_at.isoformat()}",
            f"- **Status:** {'Active' if incident.is_active else 'Resolved'}",
            "",
            "## Description",
            incident.description,
            "",
        ]

        if incident.probe_results:
            lines.append("## Probe Results")
            for pr in incident.probe_results:
                lines.append(f"- [{pr.timestamp.strftime('%H:%M:%S')}] {pr.component}: {pr.status.value} — {pr.message}")
            lines.append("")

        if incident.actions_taken:
            lines.append("## Actions Taken")
            for action in incident.actions_taken:
                lines.append(f"- {action}")
            lines.append("")

        if incident.resolved_at:
            lines.append(f"**Resolved at:** {incident.resolved_at.isoformat()}")
            lines.append(f"**Duration:** {incident.duration_seconds:.0f}s")

        path.write_text("\n".join(lines))
        return str(path)

    def update_incident_report(self, incident: IncidentRecord) -> str:
        """Update an existing incident report. Returns file path."""
        # Just rewrite it
        return self.write_incident_report(incident)

    def write_dependency_map(self, nodes: List[DependencyNode]) -> str:
        """Write dependency_map.md with Mermaid diagram. Returns file path."""
        path = self.report_dir / "dependency_map.md"
        lines = [
            "# System Dependency Map",
            f"**Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "```mermaid",
            "graph TD",
        ]

        for node in nodes:
            # Style based on status
            shape_start, shape_end = "[", "]"
            if node.node_type == "external_api":
                shape_start, shape_end = "((", "))"
            elif node.node_type == "service":
                shape_start, shape_end = "(", ")"

            safe_name = node.name.replace(" ", "_")
            lines.append(f"    {safe_name}{shape_start}{node.name}{shape_end}")

            for dep in node.depends_on:
                safe_dep = dep.replace(" ", "_")
                lines.append(f"    {safe_name} --> {safe_dep}")

        lines.append("```")
        path.write_text("\n".join(lines))
        return str(path)

    def read_report(self, path: str) -> Optional[str]:
        """Read a report file. Returns content or None."""
        p = Path(path) if os.path.isabs(path) else self.report_dir / path
        if p.exists():
            return p.read_text()
        return None

    def list_reports(self, category: str = "") -> List[str]:
        """List report files. Category can be 'incidents', 'daily', or '' for root."""
        search_dir = self.report_dir / category if category else self.report_dir
        if not search_dir.exists():
            return []
        return sorted(
            [str(p.relative_to(self.report_dir)) for p in search_dir.glob("*.md")],
            reverse=True,
        )

    def cleanup_old_reports(self, retention_days: int = 30) -> int:
        """Remove reports older than retention_days. Returns count removed."""
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        for subdir in ["incidents", "daily"]:
            dir_path = self.report_dir / subdir
            if not dir_path.exists():
                continue
            for f in dir_path.glob("*.md"):
                try:
                    # Parse date from filename (YYYY-MM-DD_...)
                    date_str = f.name[:10]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date < cutoff:
                        f.unlink()
                        removed += 1
                except (ValueError, IndexError):
                    continue
        return removed
