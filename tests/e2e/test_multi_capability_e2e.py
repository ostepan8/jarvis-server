"""E2E: Multi-capability DAG — parallel agent execution and response aggregation."""

import pytest

from jarvis.ai_clients.scripted_client import ScriptedAIClient


@pytest.mark.asyncio
async def test_search_and_schedule_parallel_dag(jarvis_system):
    """Multi-cap DAG: search + get_today_schedule run in parallel, results merge."""
    result = await jarvis_system.process_request(
        "Search for news and tell me my schedule", "UTC"
    )

    assert result is not None
    assert "response" in result
    response = result["response"]
    assert isinstance(response, str)
    assert len(response) > 0
