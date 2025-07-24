from __future__ import annotations

from fastapi import APIRouter, Request, Depends
from jarvis import JarvisSystem
from jarvis.utils import detect_timezone
from .agents import (
    list_agents as list_agents_route,
    get_agent_capabilities as agent_caps_route,
)

from ..models import JarvisRequest
from ..dependencies import (
    get_jarvis,
    get_user_allowed_agents,
    get_current_user,
    get_auth_db,
)
from ..database import get_user_profile


router = APIRouter()


@router.post("/")
async def jarvis(
    req: JarvisRequest,
    request: Request,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
    allowed: set[str] = Depends(get_user_allowed_agents),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
):
    """Execute a command using the agent network."""
    tz_name = detect_timezone(request)
    profile = get_user_profile(db, current_user["id"])
    metadata = {
        "device": request.headers.get("X-Device"),
        "location": request.headers.get("X-Location"),
        "user": request.headers.get("X-User"),
        "source": request.headers.get("X-Source", "text"),
        "user_id": current_user["id"],
        "profile": profile,
    }
    return await jarvis_system.process_request(
        req.command, tz_name, metadata, allowed_agents=allowed
    )


@router.get("/agents")
async def list_agents(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """List all available agents."""
    return await list_agents_route(jarvis_system)


@router.get("/agents/{agent_name}/capabilities")
async def get_agent_capabilities(
    agent_name: str, jarvis_system: JarvisSystem = Depends(get_jarvis)
):
    """Get all capabilities for a specific agent."""
    return await agent_caps_route(agent_name, jarvis_system)
