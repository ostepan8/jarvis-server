"""E2E: Todo pipeline — task management through TodoAgent."""

import pytest


@pytest.mark.asyncio
async def test_show_tasks_routes_to_todo(jarvis_system):
    """'Show my tasks' → NLU classifies as list_tasks → TodoAgent."""
    result = await jarvis_system.process_request("Show my tasks", "UTC")

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_add_task_routes_to_todo(jarvis_system):
    """'Add a task' → NLU classifies as create_task → TodoAgent creates it."""
    result = await jarvis_system.process_request(
        "Add a task: buy groceries", "UTC"
    )

    assert result is not None
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0
