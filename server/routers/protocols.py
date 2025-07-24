from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from jarvis import JarvisSystem
from jarvis.protocols import Protocol

from ..models import ProtocolRunRequest
from ..dependencies import get_jarvis, get_user_allowed_agents


router = APIRouter()


@router.get("/")
async def list_protocols(
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Return all registered protocols with their details."""
    protocols = [
        p.to_dict() for p in jarvis_system.protocol_registry.protocols.values()
    ]
    return {"protocols": protocols}


@router.post("/run")
async def run_protocol(
    req: ProtocolRunRequest,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
    allowed: set[str] = Depends(get_user_allowed_agents),
):
    """Run a protocol provided directly or by name."""
    if req.protocol is None and req.protocol_name is None:
        raise HTTPException(400, detail="protocol or protocol_name required")

    if req.protocol is not None:
        try:
            proto = Protocol.from_dict(req.protocol)
        except Exception as exc:
            raise HTTPException(400, detail=f"Invalid protocol: {exc}")
    else:
        proto = jarvis_system.protocol_registry.get(req.protocol_name)  # type: ignore[arg-type]
        if proto is None:
            raise HTTPException(404, detail="Protocol not found")

    results = await jarvis_system.protocol_executor.run_protocol(
        proto, req.arguments, allowed_agents=allowed
    )
    return {"protocol": proto.name, "results": results}
