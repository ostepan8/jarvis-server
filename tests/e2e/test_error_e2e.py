"""E2E: Error propagation — service failures don't crash the pipeline."""

import pytest


@pytest.mark.asyncio
async def test_search_service_error_propagates_gracefully(jarvis_system_search_fail):
    """Search service failure → error flows through pipeline without crash."""
    result = await jarvis_system_search_fail.process_request(
        "What's the weather like today?", "UTC"
    )

    assert result is not None
    assert "response" in result
    # The system should still return a response, even if it reports an error
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0
