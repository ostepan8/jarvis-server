from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

from jarvis import JarvisLogger, JarvisSystem
from jarvis.utils import detect_timezone

app = FastAPI(title="Jarvis API")
logger = JarvisLogger()
jarvis_system: Optional[JarvisSystem] = None


class JarvisRequest(BaseModel):
    command: str


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the collaborative Jarvis system."""
    load_dotenv()
    config = {
        "ai_provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "calendar_api_url": os.getenv("CALENDAR_API_URL", "http://localhost:8080"),
    }
    global jarvis_system
    jarvis_system = JarvisSystem(config)
    await jarvis_system.initialize()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if jarvis_system:
        await jarvis_system.shutdown()
    logger.close()


@app.post("/jarvis")
async def jarvis(req: JarvisRequest, request: Request):
    """Execute a command using the agent network."""
    if jarvis_system is None:
        raise HTTPException(status_code=500, detail="Jarvis system not initialized")
    tz_name = detect_timezone(request)
    return await jarvis_system.process_request(req.command, tz_name)


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
