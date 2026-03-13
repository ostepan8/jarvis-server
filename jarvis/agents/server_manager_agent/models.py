"""Data models for the ServerManagerAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ServerMode(Enum):
    """Whether Jarvis manages the process or just monitors an external one."""
    MANAGED = "managed"
    EXTERNAL = "external"


class ServerStatus(Enum):
    """Lifecycle states for a registered server."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    CRASHED = "crashed"


class RestartPolicy(Enum):
    """When to auto-restart a managed server."""
    NEVER = "never"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"


@dataclass
class ServerConfig:
    """Static configuration for one server entry in the registry."""
    name: str
    mode: ServerMode = ServerMode.MANAGED
    command: List[str] = field(default_factory=list)
    working_directory: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    host: str = "localhost"
    port: int = 0
    health_endpoint: Optional[str] = None
    health_check_interval: float = 30.0
    restart_policy: RestartPolicy = RestartPolicy.ON_FAILURE
    max_restarts: int = 5
    restart_window: float = 300.0  # seconds of stability before counter resets
    start_on_boot: bool = False
    tags: List[str] = field(default_factory=list)

    def health_url(self) -> Optional[str]:
        """Build the full health-check URL, or None if not configured."""
        if not self.health_endpoint or not self.port:
            return None
        scheme = "http"
        return f"{scheme}://{self.host}:{self.port}{self.health_endpoint}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode.value,
            "command": self.command,
            "working_directory": self.working_directory,
            "environment": self.environment,
            "host": self.host,
            "port": self.port,
            "health_endpoint": self.health_endpoint,
            "health_check_interval": self.health_check_interval,
            "restart_policy": self.restart_policy.value,
            "max_restarts": self.max_restarts,
            "restart_window": self.restart_window,
            "start_on_boot": self.start_on_boot,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ServerConfig:
        return cls(
            name=data["name"],
            mode=ServerMode(data.get("mode", "managed")),
            command=data.get("command", []),
            working_directory=data.get("working_directory"),
            environment=data.get("environment", {}),
            host=data.get("host", "localhost"),
            port=data.get("port", 0),
            health_endpoint=data.get("health_endpoint"),
            health_check_interval=data.get("health_check_interval", 30.0),
            restart_policy=RestartPolicy(data.get("restart_policy", "on_failure")),
            max_restarts=data.get("max_restarts", 5),
            restart_window=data.get("restart_window", 300.0),
            start_on_boot=data.get("start_on_boot", False),
            tags=data.get("tags", []),
        )


@dataclass
class ServerState:
    """Runtime state for a registered server."""
    config: ServerConfig
    status: ServerStatus = ServerStatus.STOPPED
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    last_health_latency_ms: Optional[float] = None
    restart_count: int = 0
    consecutive_failures: int = 0
    last_exit_code: Optional[int] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "status": self.status.value,
            "pid": self.pid,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "last_health_latency_ms": round(self.last_health_latency_ms, 2) if self.last_health_latency_ms is not None else None,
            "restart_count": self.restart_count,
            "consecutive_failures": self.consecutive_failures,
            "last_exit_code": self.last_exit_code,
            "error_message": self.error_message,
        }
