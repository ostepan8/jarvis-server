"""E2E: Chat pipeline — greetings and fallback route through ChatAgent."""

import pytest


@pytest.mark.asyncio
async def test_hello_routes_to_chat(jarvis_system):
    """'Hello' → NLU classifies as chat → ChatAgent responds."""
    result = await jarvis_system.process_request("Hello, how are you?", "UTC")

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_gibberish_falls_back_to_chat(jarvis_system):
    """Unrecognizable input defaults to chat DAG."""
    result = await jarvis_system.process_request("xyzzy plugh", "UTC")

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_how_are_you_routes_to_chat(jarvis_system):
    """Conversational queries get routed to ChatAgent."""
    result = await jarvis_system.process_request("How are you doing today?", "UTC")

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
