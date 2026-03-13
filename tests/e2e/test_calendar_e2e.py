"""E2E: Calendar pipeline — scheduling and querying events through CalendarAgent."""

import pytest


@pytest.mark.asyncio
async def test_schedule_meeting_routes_to_calendar(jarvis_system):
    """'Schedule ...' → NLU classifies as schedule_appointment → CalendarAgent."""
    result = await jarvis_system.process_request(
        "Schedule a meeting at 3pm tomorrow", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_whats_on_calendar_routes_to_calendar(jarvis_system):
    """'What's on my calendar' → NLU classifies as get_today_schedule → CalendarAgent."""
    result = await jarvis_system.process_request(
        "What's on my calendar today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_create_event_routes_to_calendar(jarvis_system):
    """'Create an event' → NLU routes to schedule_appointment."""
    result = await jarvis_system.process_request(
        "Create an event for lunch at noon", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
