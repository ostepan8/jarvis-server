"""Health monitoring HTTP endpoints."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from jarvis import JarvisSystem
from ..dependencies import get_jarvis

if TYPE_CHECKING:
    from jarvis.agents.health_agent import HealthAgent

router = APIRouter()


def _get_health_agent(jarvis_system: JarvisSystem) -> HealthAgent:
    """Get the HealthAgent from the system, or raise 503."""
    agent = jarvis_system.network.agents.get("HealthAgent")
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="Health monitoring not available",
        )
    # Import at runtime to avoid circular import issues
    from jarvis.agents.health_agent import HealthAgent

    if not isinstance(agent, HealthAgent):
        raise HTTPException(
            status_code=503,
            detail="Health monitoring not available",
        )
    return agent


@router.get("/")
async def health_check(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Basic health check for load balancers."""
    agent = jarvis_system.network.agents.get("HealthAgent")
    if not agent:
        return {
            "status": "unknown",
            "summary": "Health agent not initialized",
        }

    from jarvis.agents.health_agent import HealthAgent

    if isinstance(agent, HealthAgent) and agent._last_snapshot:
        snapshot = agent._last_snapshot
        return {
            "status": snapshot.overall_status.value,
            "summary": snapshot.summary,
            "timestamp": snapshot.timestamp.isoformat(),
        }

    return {
        "status": "unknown",
        "summary": "No health data yet",
    }


@router.get("/detailed")
async def health_detailed(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Full system health snapshot."""
    agent = _get_health_agent(jarvis_system)
    result = await agent._system_health_check()
    return result.to_dict()


@router.get("/agents")
async def health_agents(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Health status of all agents."""
    agent = _get_health_agent(jarvis_system)
    result = await agent._agent_health_status(prompt="")
    return result.to_dict()


@router.get("/agents/{agent_name}")
async def health_agent_by_name(
    agent_name: str,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Health status of a specific agent."""
    agent = _get_health_agent(jarvis_system)
    result = await agent._agent_health_status(prompt=agent_name)
    return result.to_dict()


@router.get("/incidents")
async def health_incidents(
    active_only: bool = Query(False, description="Only show active incidents"),
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """List incidents."""
    agent = _get_health_agent(jarvis_system)
    prompt = "active" if active_only else ""
    result = await agent._incident_list(data={"prompt": prompt})
    return result.to_dict()


@router.get("/reports")
async def list_reports(
    category: str = Query("", description="Report category: incidents, daily, or empty for root"),
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """List available health reports."""
    agent = _get_health_agent(jarvis_system)
    reports = agent.report_writer.list_reports(category)
    return {"reports": reports}


@router.get("/reports/{path:path}")
async def read_report(
    path: str,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Read a specific health report."""
    agent = _get_health_agent(jarvis_system)
    content = agent.report_writer.read_report(path)
    if content is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"path": path, "content": content}


@router.get("/dependency-map")
async def dependency_map(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Live dependency graph."""
    agent = _get_health_agent(jarvis_system)
    result = await agent._dependency_map()
    return result.to_dict()
