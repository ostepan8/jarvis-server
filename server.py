from __future__ import annotations

import os
import logging

from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Dict, Optional
from jarvis import JarvisLogger, JarvisSystem, JarvisConfig
from jarvis.constants import DEFAULT_PORT
from jarvis.utils import detect_timezone
from fastapi.middleware.cors import CORSMiddleware


class ProtocolRunRequest(BaseModel):
    protocol: Optional[Dict[str, Any]] = None
    protocol_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


app = FastAPI(title="Jarvis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React or Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JarvisRequest(BaseModel):
    command: str


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the collaborative Jarvis system."""
    load_dotenv()
    level_name = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    app.state.logger = JarvisLogger(log_level=level)
    config = JarvisConfig(
        ai_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY"),
        calendar_api_url=os.getenv("CALENDAR_API_URL", "http://localhost:8080"),
        repo_path=os.getenv("REPO_PATH", "."),
        response_timeout=float(os.getenv("JARVIS_RESPONSE_TIMEOUT", 15.0)),
    )
    jarvis_system = JarvisSystem(config)
    await jarvis_system.initialize()
    app.state.jarvis_system = jarvis_system


@app.on_event("shutdown")
async def shutdown_event() -> None:
    jarvis_system: JarvisSystem | None = getattr(app.state, "jarvis_system", None)
    if jarvis_system:
        await jarvis_system.shutdown()
    logger: JarvisLogger | None = getattr(app.state, "logger", None)
    if logger:
        logger.close()


async def get_jarvis(request: Request) -> JarvisSystem:
    jarvis_system: JarvisSystem | None = getattr(
        request.app.state, "jarvis_system", None
    )
    if jarvis_system is None:
        raise HTTPException(status_code=500, detail="Jarvis system not initialized")
    return jarvis_system


@app.post("/jarvis")
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


@app.get("/protocols")
async def list_protocols(
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Return all registered protocols with their details."""
    protocols = [
        p.to_dict() for p in jarvis_system.protocol_registry.protocols.values()
    ]
    return {"protocols": protocols}


@app.post("/protocols/run")
async def run_protocol(
    req: ProtocolRunRequest,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
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

    results = await jarvis_system.protocol_executor.run_protocol(proto, req.arguments)
    return {"protocol": proto.name, "results": results}


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)


if __name__ == "__main__":
    run()
