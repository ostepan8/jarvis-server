from __future__ import annotations

import sys
import os

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from fastapi import APIRouter, Request, Depends
from jarvis import JarvisSystem
from jarvis.utils import detect_timezone

from models import JarvisRequest
from dependencies import get_jarvis


router = APIRouter()


@router.post("/")
async def jarvis(
    req: JarvisRequest,
    request: Request,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Execute a command using the agent network."""
    tz_name = detect_timezone(request)
    metadata = {
        "device": request.headers.get("X-Device"),
        "location": request.headers.get("X-Location"),
        "user": request.headers.get("X-User"),
        "source": request.headers.get("X-Source", "text"),
    }
    return await jarvis_system.process_request(req.command, tz_name, metadata)


@router.get("/agents")
async def list_agents(jarvis_system: JarvisSystem = Depends(get_jarvis)):
    """List all available agents."""
    return jarvis_system.list_agents()


@router.get("/agents/{agent_name}/capabilities")
async def get_agent_capabilities(
    agent_name: str, jarvis_system: JarvisSystem = Depends(get_jarvis)
):
    """Get all capabilities for a specific agent."""
    return await jarvis_system.get_agent_capabilities(agent_name)
