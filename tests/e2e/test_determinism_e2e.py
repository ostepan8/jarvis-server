"""E2E: Determinism — same input, same output, every single time."""

import pytest


@pytest.mark.asyncio
async def test_same_chat_input_ten_times_identical_output(jarvis_system):
    """Run the same chat request 10 times; every response must be identical."""
    responses = []
    for _ in range(10):
        result = await jarvis_system.process_request("Hello, how are you?", "UTC")
        responses.append(result["response"])

    first = responses[0]
    for i, resp in enumerate(responses[1:], start=2):
        assert resp == first, f"Response #{i} diverged: {resp!r} != {first!r}"


@pytest.mark.asyncio
async def test_same_search_input_ten_times_identical_output(jarvis_system):
    """Run the same search request 10 times; every response must be identical."""
    responses = []
    for _ in range(10):
        result = await jarvis_system.process_request(
            "What's the weather like today?", "UTC"
        )
        responses.append(result["response"])

    first = responses[0]
    for i, resp in enumerate(responses[1:], start=2):
        assert resp == first, f"Response #{i} diverged: {resp!r} != {first!r}"


@pytest.mark.asyncio
async def test_same_todo_input_ten_times_consistent(jarvis_system):
    """Run the same todo list request 10 times; responses should be consistent."""
    responses = []
    for _ in range(10):
        result = await jarvis_system.process_request("Show my tasks", "UTC")
        responses.append(result["response"])

    first = responses[0]
    for i, resp in enumerate(responses[1:], start=2):
        assert resp == first, f"Response #{i} diverged: {resp!r} != {first!r}"
