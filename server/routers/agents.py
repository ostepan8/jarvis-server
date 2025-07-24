from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from jarvis import JarvisSystem

from ..dependencies import get_jarvis

router = APIRouter()


@router.get("/")
async def list_agents(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Return all registered agents."""
    return jarvis_system.list_agents()


@router.get("/{agent_name}")
async def get_agent(agent_name: str, jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """Return information about a single agent."""
    agents = jarvis_system.list_agents()
    if agent_name not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents[agent_name]


@router.get("/{agent_name}/capabilities")
async def get_agent_capabilities(agent_name: str, jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """List detailed capabilities for the given agent."""
    return jarvis_system.get_agent_capabilities(agent_name)
