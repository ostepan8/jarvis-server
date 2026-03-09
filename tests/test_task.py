"""Tests for Task data structure."""

import uuid
import pytest

from jarvis.agents.task import Task


class TestTaskCreation:
    """Test Task dataclass creation."""

    def test_create_task_with_capability(self):
        """Test creating a task with just a capability."""
        task = Task(capability="get_weather")
        assert task.capability == "get_weather"
        assert task.assigned_agent is None
        assert task.depends_on == []
        assert task.intent is None
        assert task.result is None
        assert task.prompt is None
        assert task.id is not None

    def test_task_id_is_uuid(self):
        """Test task id is a valid UUID string."""
        task = Task(capability="test")
        parsed = uuid.UUID(task.id)
        assert str(parsed) == task.id

    def test_unique_ids(self):
        """Test each task gets a unique id."""
        task1 = Task(capability="test")
        task2 = Task(capability="test")
        assert task1.id != task2.id

    def test_custom_id(self):
        """Test task with a custom id."""
        task = Task(capability="test", id="custom-id")
        assert task.id == "custom-id"

    def test_full_task_creation(self):
        """Test creating a task with all fields set."""
        task = Task(
            capability="create_event",
            assigned_agent="CalendarAgent",
            depends_on=["task-1", "task-2"],
            intent="create_calendar_event",
            id="task-3",
            result={"success": True},
            prompt="Schedule a meeting tomorrow",
        )
        assert task.capability == "create_event"
        assert task.assigned_agent == "CalendarAgent"
        assert task.depends_on == ["task-1", "task-2"]
        assert task.intent == "create_calendar_event"
        assert task.id == "task-3"
        assert task.result == {"success": True}
        assert task.prompt == "Schedule a meeting tomorrow"


class TestTaskDependencies:
    """Test Task dependency tracking."""

    def test_no_dependencies(self):
        """Test task with no dependencies."""
        task = Task(capability="search")
        assert task.depends_on == []

    def test_single_dependency(self):
        """Test task with a single dependency."""
        task = Task(capability="summarize", depends_on=["task-search"])
        assert task.depends_on == ["task-search"]

    def test_multiple_dependencies(self):
        """Test task with multiple dependencies."""
        task = Task(
            capability="summarize",
            depends_on=["task-weather", "task-calendar", "task-search"],
        )
        assert len(task.depends_on) == 3
        assert "task-weather" in task.depends_on

    def test_depends_on_is_independent_list(self):
        """Test each task gets its own depends_on list."""
        task1 = Task(capability="a")
        task2 = Task(capability="b")
        task1.depends_on.append("dep-1")
        assert task2.depends_on == []


class TestTaskResult:
    """Test Task result storage."""

    def test_result_initially_none(self):
        """Test result starts as None."""
        task = Task(capability="test")
        assert task.result is None

    def test_set_result_dict(self):
        """Test setting a dict result."""
        task = Task(capability="test")
        task.result = {"success": True, "response": "Done"}
        assert task.result["success"] is True

    def test_set_result_string(self):
        """Test setting a string result."""
        task = Task(capability="test")
        task.result = "completed"
        assert task.result == "completed"

    def test_set_result_none(self):
        """Test setting result back to None."""
        task = Task(capability="test")
        task.result = {"data": "value"}
        task.result = None
        assert task.result is None


class TestTaskPrompt:
    """Test Task prompt field."""

    def test_prompt_initially_none(self):
        """Test prompt starts as None."""
        task = Task(capability="test")
        assert task.prompt is None

    def test_prompt_with_user_input(self):
        """Test task with a user prompt."""
        task = Task(
            capability="chat",
            prompt="What is the weather today?",
        )
        assert task.prompt == "What is the weather today?"


class TestTaskAssignedAgent:
    """Test Task agent assignment."""

    def test_assigned_agent_initially_none(self):
        """Test assigned_agent starts as None."""
        task = Task(capability="test")
        assert task.assigned_agent is None

    def test_assign_agent(self):
        """Test assigning an agent to a task."""
        task = Task(capability="get_weather", assigned_agent="WeatherAgent")
        assert task.assigned_agent == "WeatherAgent"

    def test_reassign_agent(self):
        """Test reassigning an agent."""
        task = Task(capability="get_weather", assigned_agent="WeatherAgent")
        task.assigned_agent = "AnotherAgent"
        assert task.assigned_agent == "AnotherAgent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
