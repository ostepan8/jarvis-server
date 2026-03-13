"""Device monitoring HTTP endpoints."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from jarvis import JarvisSystem
from ..dependencies import get_jarvis

if TYPE_CHECKING:
    from jarvis.agents.device_monitor_agent import DeviceMonitorAgent

router = APIRouter()


def _get_device_agent(jarvis_system: JarvisSystem) -> DeviceMonitorAgent:
    """Get the DeviceMonitorAgent from the system, or raise 503."""
    agent = jarvis_system.network.agents.get("DeviceMonitorAgent")
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="Device monitoring not available",
        )
    # Import at runtime to avoid circular import issues
    from jarvis.agents.device_monitor_agent import DeviceMonitorAgent

    if not isinstance(agent, DeviceMonitorAgent):
        raise HTTPException(
            status_code=503,
            detail="Device monitoring not available",
        )
    return agent


@router.get("/")
async def device_status(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Quick device status summary."""
    agent = _get_device_agent(jarvis_system)
    snap = agent.device_service.snapshot()
    return {
        "hostname": snap.hostname,
        "platform": snap.platform,
        "overall_severity": snap.overall_severity.value,
        "status": (
            "all systems nominal"
            if snap.overall_severity.value == "ok"
            else f"severity: {snap.overall_severity.value}"
        ),
    }


@router.get("/snapshot")
async def device_snapshot(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Full current hardware snapshot."""
    agent = _get_device_agent(jarvis_system)
    snap = agent.device_service.snapshot()
    return snap.to_dict()


@router.get("/history/{component}")
async def device_history(
    component: str,
    metric: Optional[str] = Query(None, description="Specific metric name"),
    hours: int = Query(24, description="Hours of history to retrieve"),
    limit: int = Query(1000, description="Maximum data points"),
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Raw historical metrics for a component."""
    _get_device_agent(jarvis_system)  # Ensure agent is available
    return {
        "component": component,
        "metric": metric,
        "hours": hours,
        "message": "Historical data available when MetricsStore is connected",
        "data": [],
    }


@router.get("/history/{component}/aggregated")
async def device_history_aggregated(
    component: str,
    metric: Optional[str] = Query(None, description="Specific metric name"),
    hours: int = Query(24, description="Hours of history to retrieve"),
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Hourly rollups of historical metrics for a component."""
    _get_device_agent(jarvis_system)  # Ensure agent is available
    return {
        "component": component,
        "metric": metric,
        "hours": hours,
        "message": "Aggregated data available when MetricsStore is connected",
        "data": [],
    }


@router.get("/diagnostics")
async def device_diagnostics(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Deep diagnostics with process analysis."""
    agent = _get_device_agent(jarvis_system)
    result = await agent._handle_device_diagnostics({})
    return result.to_dict()


@router.get("/battery")
async def device_battery(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Battery health details (macOS / laptops)."""
    agent = _get_device_agent(jarvis_system)
    snap = agent.device_service.snapshot()
    if snap.battery is None:
        return {
            "available": False,
            "message": "No battery detected — presumably a desktop or VM",
        }
    batt = snap.battery
    return {
        "available": True,
        "percent": batt.value,
        "severity": batt.severity.value,
        "plugged_in": batt.details.get("plugged_in"),
        "secs_left": batt.details.get("secs_left"),
    }


@router.get("/thermals")
async def device_thermals(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Current thermal status."""
    agent = _get_device_agent(jarvis_system)
    snap = agent.device_service.snapshot()
    if not snap.thermals:
        return {
            "available": False,
            "message": "No thermal sensors detected",
            "sensors": [],
        }
    return {
        "available": True,
        "sensors": [
            {
                "name": m.name,
                "temperature_c": m.value,
                "severity": m.severity.value,
                "details": m.details,
            }
            for m in snap.thermals
        ],
    }
