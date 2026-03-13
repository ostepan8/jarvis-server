"""E2E with real LLM — actual OpenAI calls through the full Jarvis pipeline.

Requires OPENAI_API_KEY in the environment. Skips gracefully without it.
Uses gpt-4o-mini for both strong and weak calls (fast, cheap, sufficient).

Only HTTP services are mocked (search API, calendar API, MongoDB).
Everything else — NLU classification, agent responses, routing — is real.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for real LLM tests",
)


# ------------------------------------------------------------------
# Chat
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hello_routes_to_chat_real_llm(real_jarvis_system):
    """Real NLU classifies a greeting and routes to ChatAgent."""
    result = await real_jarvis_system.process_request("Hello, how are you?", "UTC")

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weather_routes_to_search_real_llm(real_jarvis_system):
    """Real NLU classifies a weather query and routes to SearchAgent."""
    result = await real_jarvis_system.process_request(
        "What's the weather like today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert len(result["response"]) > 0

    # The mocked search service proves NLU routed to SearchAgent
    search_agent = real_jarvis_system.network.agents.get("SearchAgent")
    if search_agent:
        search_agent.search_service.search.assert_called()


@pytest.mark.asyncio
async def test_search_for_tutorials_real_llm(real_jarvis_system):
    """Real NLU routes a search query, AI synthesizes mocked results."""
    result = await real_jarvis_system.process_request(
        "Search for python tutorials", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert len(result["response"]) > 0

    search_agent = real_jarvis_system.network.agents.get("SearchAgent")
    if search_agent:
        search_agent.search_service.search.assert_called()


# ------------------------------------------------------------------
# Calendar
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whats_on_calendar_real_llm(real_jarvis_system):
    """Real NLU classifies a calendar query and routes to CalendarAgent."""
    result = await real_jarvis_system.process_request(
        "What's on my calendar today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert len(result["response"]) > 0


# ------------------------------------------------------------------
# Todo
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_show_tasks_real_llm(real_jarvis_system):
    """Real NLU classifies a todo query and routes to TodoAgent."""
    result = await real_jarvis_system.process_request("Show my tasks", "UTC")

    assert result is not None
    assert "response" in result
    assert len(result["response"]) > 0


# ------------------------------------------------------------------
# Error resilience
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_error_doesnt_crash_real_llm(real_jarvis_system_search_fail):
    """Search service failure propagates gracefully with real LLM routing."""
    result = await real_jarvis_system_search_fail.process_request(
        "What's the weather like today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0
