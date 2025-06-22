from __future__ import annotations

import os
import logging

from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from dotenv import load_dotenv

from jarvis import JarvisLogger, JarvisSystem
from jarvis.utils import detect_timezone

app = FastAPI(title="Jarvis API")


class JarvisRequest(BaseModel):
    command: str


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the collaborative Jarvis system."""
    load_dotenv()
    level_name = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    app.state.logger = JarvisLogger(log_level=level)
    config = {
        "ai_provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "calendar_api_url": os.getenv("CALENDAR_API_URL", "http://localhost:8080"),
        "repo_path": os.getenv("REPO_PATH", "."),
    }
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
    jarvis_system: JarvisSystem | None = getattr(request.app.state, "jarvis_system", None)
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


def run():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
