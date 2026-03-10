from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class ComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class IncidentSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ProbeResult:
    component: str
    component_type: str  # "agent", "service", "resource", "network"
    status: ComponentStatus
    latency_ms: Optional[float] = None
    message: str = ""
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "component": self.component,
            "component_type": self.component_type,
            "status": self.status.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class IncidentRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    component: str = ""
    severity: IncidentSeverity = IncidentSeverity.WARNING
    title: str = ""
    description: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    probe_results: List[ProbeResult] = field(default_factory=list)
    actions_taken: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None

    @property
    def duration_seconds(self) -> float:
        end = self.resolved_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "component": self.component,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "started_at": self.started_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "is_active": self.is_active,
            "duration_seconds": round(self.duration_seconds, 1),
            "probe_results": [p.to_dict() for p in self.probe_results],
            "actions_taken": self.actions_taken,
        }


@dataclass
class SystemHealthSnapshot:
    timestamp: datetime = field(default_factory=datetime.now)
    overall_status: ComponentStatus = ComponentStatus.UNKNOWN
    agent_statuses: List[ProbeResult] = field(default_factory=list)
    service_statuses: List[ProbeResult] = field(default_factory=list)
    resource_statuses: List[ProbeResult] = field(default_factory=list)
    network_metrics: Optional[Dict[str, Any]] = None
    active_incidents: List[IncidentRecord] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "agent_statuses": [s.to_dict() for s in self.agent_statuses],
            "service_statuses": [s.to_dict() for s in self.service_statuses],
            "resource_statuses": [s.to_dict() for s in self.resource_statuses],
            "network_metrics": self.network_metrics,
            "active_incidents": [i.to_dict() for i in self.active_incidents],
            "summary": self.summary,
        }


@dataclass
class DependencyNode:
    name: str
    node_type: str  # "agent", "service", "external_api"
    status: ComponentStatus = ComponentStatus.UNKNOWN
    depends_on: List[str] = field(default_factory=list)
    depended_by: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "depended_by": self.depended_by,
        }
