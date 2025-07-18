import pytest
import asyncio

from jarvis.agents.calendar_agent import CollaborativeCalendarAgent
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient
from jarvis.services.calendar_service import CalendarService

class DummyAIClient(BaseAIClient):
    async def strong_chat(self, messages, tools=None):
        return None, None
    async def weak_chat(self, messages, tools=None):
        return None, None

@pytest.mark.asyncio
async def test_calendar_agent_prompt(monkeypatch):
    service = CalendarService()
    agent = CollaborativeCalendarAgent(ai_client=DummyAIClient(), calendar_service=service)
    async def fake_process(cmd):
        return {"echo": cmd}
    monkeypatch.setattr(agent.command_processor, "process_command", fake_process)
    captured = {}
    async def fake_send(to, result, request_id, msg_id):
        captured["result"] = result
    monkeypatch.setattr(agent, "send_capability_response", fake_send)
    message = Message(
        from_agent="tester",
        to_agent="CalendarAgent",
        message_type="capability_request",
        content={"capability": next(iter(agent.capabilities)), "data": {"prompt": "hi"}},
        request_id="1",
    )
    await agent._handle_capability_request(message)
    assert captured["result"]["echo"] == "hi"
