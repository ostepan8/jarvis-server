"""E2E: Search pipeline — weather and search queries route through SearchAgent."""

import pytest


@pytest.mark.asyncio
async def test_weather_query_routes_to_search(jarvis_system):
    """'weather' → NLU classifies as search → SearchAgent → mocked service → synthesis."""
    result = await jarvis_system.process_request(
        "What's the weather like today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    response = result["response"]
    assert isinstance(response, str)
    assert len(response) > 0

    # The mocked search service was called
    search_agent = jarvis_system.network.agents["SearchAgent"]
    search_agent.search_service.search.assert_called()


@pytest.mark.asyncio
async def test_search_query_routes_to_search(jarvis_system):
    """'Search for ...' → NLU classifies as search → SearchAgent processes."""
    result = await jarvis_system.process_request(
        "Search for python tutorials", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0

    search_agent = jarvis_system.network.agents["SearchAgent"]
    search_agent.search_service.search.assert_called()
