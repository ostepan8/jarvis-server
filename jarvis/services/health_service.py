from __future__ import annotations

import asyncio
import os
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.agents.health_agent.models import ProbeResult, ComponentStatus


def _models():
    """Lazy import to break circular dependency."""
    from jarvis.agents.health_agent.models import ProbeResult, ComponentStatus
    return ProbeResult, ComponentStatus


class HealthService:
    """Probes external services and system resources."""

    def __init__(self, timeout: float = 5.0):
        self._timeout = timeout

    async def probe_http_service(
        self, name: str, url: str, timeout: Optional[float] = None
    ) -> ProbeResult:
        """Probe an HTTP service. Returns ProbeResult, never raises."""
        ProbeResult, ComponentStatus = _models()
        t = timeout or self._timeout
        try:
            import httpx
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=t) as client:
                resp = await client.get(url)
            latency = (time.monotonic() - start) * 1000

            if resp.status_code < 400:
                return ProbeResult(
                    component=name,
                    component_type="service",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}",
                )
            elif resp.status_code < 500:
                return ProbeResult(
                    component=name,
                    component_type="service",
                    status=ComponentStatus.DEGRADED,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}",
                )
            else:
                return ProbeResult(
                    component=name,
                    component_type="service",
                    status=ComponentStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}",
                )
        except ImportError:
            return ProbeResult(
                component=name,
                component_type="service",
                status=ComponentStatus.UNKNOWN,
                message="httpx not installed",
            )
        except Exception as exc:
            return ProbeResult(
                component=name,
                component_type="service",
                status=ComponentStatus.UNHEALTHY,
                message=str(exc),
            )

    async def probe_calendar_api(self, url: str = "") -> ProbeResult:
        """Probe the Calendar API."""
        api_url = url or os.getenv("CALENDAR_API_URL", "http://localhost:8080")
        return await self.probe_http_service("CalendarAPI", f"{api_url}/health")

    async def probe_sqlite(self, db_path: str = "") -> ProbeResult:
        """Check if SQLite database file exists and is accessible."""
        ProbeResult, ComponentStatus = _models()
        path = db_path or os.path.join(os.path.expanduser("~"), ".jarvis", "jarvis.db")
        try:
            if os.path.exists(path):
                size_mb = os.path.getsize(path) / (1024 * 1024)
                return ProbeResult(
                    component="SQLite",
                    component_type="service",
                    status=ComponentStatus.HEALTHY,
                    message=f"Database exists ({size_mb:.1f} MB)",
                    details={"path": path, "size_mb": round(size_mb, 1)},
                )
            else:
                return ProbeResult(
                    component="SQLite",
                    component_type="service",
                    status=ComponentStatus.DEGRADED,
                    message=f"Database file not found: {path}",
                )
        except Exception as exc:
            return ProbeResult(
                component="SQLite",
                component_type="service",
                status=ComponentStatus.UNHEALTHY,
                message=f"Error checking SQLite: {exc}",
            )

    def get_cpu_usage(self) -> ProbeResult:
        """Get CPU usage. Soft dependency on psutil."""
        ProbeResult, ComponentStatus = _models()
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            if cpu > 90:
                status = ComponentStatus.UNHEALTHY
            elif cpu > 70:
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.HEALTHY
            return ProbeResult(
                component="CPU",
                component_type="resource",
                status=status,
                message=f"{cpu:.1f}% usage",
                details={"percent": cpu},
            )
        except ImportError:
            return ProbeResult(
                component="CPU",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message="psutil not installed",
            )
        except Exception as exc:
            return ProbeResult(
                component="CPU",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message=f"Error: {exc}",
            )

    def get_memory_usage(self) -> ProbeResult:
        """Get memory usage."""
        ProbeResult, ComponentStatus = _models()
        try:
            import psutil
            mem = psutil.virtual_memory()
            pct = mem.percent
            if pct > 90:
                status = ComponentStatus.UNHEALTHY
            elif pct > 80:
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.HEALTHY
            return ProbeResult(
                component="Memory",
                component_type="resource",
                status=status,
                message=f"{pct:.1f}% used ({mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB)",
                details={"percent": pct, "used_mb": mem.used // (1024**2), "total_mb": mem.total // (1024**2)},
            )
        except ImportError:
            return ProbeResult(
                component="Memory",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message="psutil not installed",
            )
        except Exception as exc:
            return ProbeResult(
                component="Memory",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message=f"Error: {exc}",
            )

    def get_disk_usage(self) -> ProbeResult:
        """Get disk usage."""
        ProbeResult, ComponentStatus = _models()
        try:
            import psutil
            disk = psutil.disk_usage("/")
            pct = disk.percent
            if pct > 95:
                status = ComponentStatus.UNHEALTHY
            elif pct > 85:
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.HEALTHY
            return ProbeResult(
                component="Disk",
                component_type="resource",
                status=status,
                message=f"{pct:.1f}% used ({disk.used // (1024**3)} GB / {disk.total // (1024**3)} GB)",
                details={"percent": pct, "used_gb": disk.used // (1024**3), "total_gb": disk.total // (1024**3)},
            )
        except ImportError:
            return ProbeResult(
                component="Disk",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message="psutil not installed",
            )
        except Exception as exc:
            return ProbeResult(
                component="Disk",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message=f"Error: {exc}",
            )

    async def get_event_loop_lag(self) -> ProbeResult:
        """Measure event loop lag."""
        ProbeResult, ComponentStatus = _models()
        try:
            start = time.monotonic()
            await asyncio.sleep(0)
            lag_ms = (time.monotonic() - start) * 1000

            if lag_ms > 100:
                status = ComponentStatus.UNHEALTHY
            elif lag_ms > 50:
                status = ComponentStatus.DEGRADED
            else:
                status = ComponentStatus.HEALTHY

            return ProbeResult(
                component="EventLoop",
                component_type="resource",
                status=status,
                latency_ms=lag_ms,
                message=f"Lag: {lag_ms:.1f}ms",
            )
        except Exception as exc:
            return ProbeResult(
                component="EventLoop",
                component_type="resource",
                status=ComponentStatus.UNKNOWN,
                message=f"Error measuring lag: {exc}",
            )
