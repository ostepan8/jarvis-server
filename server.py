from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from jarvis import AIClientFactory, AgentFactory, JarvisLogger

app = FastAPI(title="Jarvis API")
logger = JarvisLogger()


class AgentRequest(BaseModel):
    command: str
    ai_provider: str = "openai"
    api_key: Optional[str] = None


@app.post("/calendar-agent")
async def calendar_agent(req: AgentRequest):
    """Execute a command using the calendar agent."""
    try:
        ai_client = AIClientFactory.create(req.ai_provider, api_key=req.api_key)
        agent = AgentFactory.create("calendar", ai_client, logger=logger)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    response, actions = await agent.process_request(req.command)
    return {"response": response, "actions": actions}


@app.post("/jarvis")
async def jarvis(req: AgentRequest):
    """Execute a command using the main Jarvis agent."""
    try:
        ai_client = AIClientFactory.create(req.ai_provider, api_key=req.api_key)
        agent = AgentFactory.create("jarvis", ai_client, logger=logger)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    response, actions = await agent.process_request(req.command)
    return {"response": response, "actions": actions}


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
