"""Tests for TodoAgent and TodoService."""

from __future__ import annotations

import os
import tempfile
import pytest

from jarvis.services.todo_service import (
    TodoService,
    TodoItem,
    TaskStatus,
    TaskPriority,
)
from jarvis.agents.todo_agent import TodoAgent
from jarvis.agents.response import AgentResponse


# ── Helpers ──────────────────────────────────────────────────────────

class FakeAIMessage:
    def __init__(self, content: str):
        self.content = content


class FakeAIClient:
    """Minimal AI client stub that returns canned JSON."""

    def __init__(self, response: str = '{"op":"list"}'):
        self._response = response

    async def strong_chat(self, messages, tools=None):
        return FakeAIMessage(self._response), None

    async def weak_chat(self, messages, tools=None):
        return [FakeAIMessage(self._response)]


def _make_service(tmp_path: str) -> TodoService:
    db_path = os.path.join(tmp_path, "test_todos.db")
    return TodoService(db_path=db_path)


# =====================================================================
# TodoService tests
# =====================================================================

class TestTodoServiceCRUD:
    """Test basic CRUD operations on the service."""

    def test_create_returns_item(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Buy milk", priority="high", tags=["errands"])
        assert isinstance(item, TodoItem)
        assert item.title == "Buy milk"
        assert item.priority == TaskPriority.HIGH
        assert item.status == TaskStatus.TODO
        assert "errands" in item.tags
        assert len(item.id) == 8

    def test_get_by_id(self, tmp_path):
        svc = _make_service(str(tmp_path))
        created = svc.create(title="Test task")
        fetched = svc.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "Test task"

    def test_get_by_prefix(self, tmp_path):
        svc = _make_service(str(tmp_path))
        created = svc.create(title="Prefix task")
        prefix = created.id[:4]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_nonexistent_returns_none(self, tmp_path):
        svc = _make_service(str(tmp_path))
        assert svc.get("nonexistent") is None

    def test_list_all(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="Task A")
        svc.create(title="Task B")
        items = svc.list()
        assert len(items) == 2

    def test_list_by_status(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="Todo task")
        item_b = svc.create(title="Done task")
        svc.complete(item_b.id)

        todo_items = svc.list(status="todo")
        done_items = svc.list(status="done")
        assert len(todo_items) == 1
        assert len(done_items) == 1
        assert todo_items[0].title == "Todo task"

    def test_list_by_priority(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="Urgent task", priority="urgent")
        svc.create(title="Low task", priority="low")

        urgent = svc.list(priority="urgent")
        assert len(urgent) == 1
        assert urgent[0].title == "Urgent task"

    def test_list_by_tag(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="Dev task", tags=["dev", "backend"])
        svc.create(title="Personal task", tags=["personal"])

        dev_tasks = svc.list(tag="dev")
        assert len(dev_tasks) == 1
        assert dev_tasks[0].title == "Dev task"

    def test_update_fields(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Original")
        updated = svc.update(item.id, title="Changed", priority="urgent")
        assert updated is not None
        assert updated.title == "Changed"
        assert updated.priority == TaskPriority.URGENT

    def test_update_nonexistent_returns_none(self, tmp_path):
        svc = _make_service(str(tmp_path))
        assert svc.update("nope", title="x") is None

    def test_update_ignores_unknown_fields(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Task")
        updated = svc.update(item.id, unknown_field="value")
        assert updated is not None
        assert updated.title == "Task"

    def test_delete_existing(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="To delete")
        assert svc.delete(item.id) is True
        assert svc.get(item.id) is None

    def test_delete_nonexistent_returns_false(self, tmp_path):
        svc = _make_service(str(tmp_path))
        assert svc.delete("nonexistent") is False

    def test_complete_sets_done(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Complete me")
        completed = svc.complete(item.id)
        assert completed is not None
        assert completed.status == TaskStatus.DONE

    def test_start_sets_in_progress(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Start me")
        started = svc.start(item.id)
        assert started is not None
        assert started.status == TaskStatus.IN_PROGRESS

    def test_counts_by_status(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="T1")
        svc.create(title="T2")
        item3 = svc.create(title="T3")
        svc.complete(item3.id)

        counts = svc.counts_by_status()
        assert counts["todo"] == 2
        assert counts["done"] == 1
        assert counts["in_progress"] == 0

    def test_create_with_description_and_due_date(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(
            title="Big feature",
            description="Implement the whole thing",
            due_date="2026-04-01",
        )
        assert item.description == "Implement the whole thing"
        assert item.due_date == "2026-04-01"

    def test_update_tags(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Tagged", tags=["a"])
        updated = svc.update(item.id, tags=["b", "c"])
        assert updated is not None
        assert "b" in updated.tags
        assert "c" in updated.tags
        assert "a" not in updated.tags


class TestTodoItemSerialization:
    def test_to_dict(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(title="Serialize me", priority="high", tags=["test"])
        d = item.to_dict()
        assert d["title"] == "Serialize me"
        assert d["priority"] == "high"
        assert d["status"] == "todo"
        assert "test" in d["tags"]
        assert "id" in d
        assert "created_at" in d

    def test_list_empty_db(self, tmp_path):
        svc = _make_service(str(tmp_path))
        items = svc.list()
        assert items == []


# =====================================================================
# TodoAgent tests
# =====================================================================

class TestTodoAgentOperations:
    """Test the agent's operation dispatch (no network needed)."""

    def _make_agent(self, tmp_path, ai_response='{"op":"list"}'):
        svc = _make_service(str(tmp_path))
        client = FakeAIClient(ai_response)
        return TodoAgent(ai_client=client, todo_service=svc, logger=None), svc

    def test_create_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({
            "op": "create",
            "title": "Agent task",
            "priority": "high",
            "tags": ["dev"],
        })
        assert result.success is True
        assert "Agent task" in result.response
        assert result.data["priority"] == "high"

    def test_list_op_empty(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "list"})
        assert result.success is True
        assert "empty" in result.response.lower()

    def test_list_op_with_items(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        svc.create(title="Task 1")
        svc.create(title="Task 2")
        result = agent._execute_op({"op": "list"})
        assert result.success is True
        assert "Task 1" in result.response
        assert "Task 2" in result.response

    def test_complete_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        item = svc.create(title="Finish me")
        result = agent._execute_op({"op": "complete", "id": item.id})
        assert result.success is True
        assert "Completed" in result.response
        assert svc.get(item.id).status == TaskStatus.DONE

    def test_complete_nonexistent(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "complete", "id": "nope"})
        assert result.success is False
        assert "not found" in result.response.lower()

    def test_start_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        item = svc.create(title="Begin me")
        result = agent._execute_op({"op": "start", "id": item.id})
        assert result.success is True
        assert "Started" in result.response
        assert svc.get(item.id).status == TaskStatus.IN_PROGRESS

    def test_delete_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        item = svc.create(title="Delete me")
        result = agent._execute_op({"op": "delete", "id": item.id})
        assert result.success is True
        assert "Deleted" in result.response
        assert svc.get(item.id) is None

    def test_delete_nonexistent(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "delete", "id": "nope"})
        assert result.success is False

    def test_update_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        item = svc.create(title="Old title")
        result = agent._execute_op({
            "op": "update",
            "id": item.id,
            "fields": {"title": "New title", "priority": "urgent"},
        })
        assert result.success is True
        assert "Updated" in result.response
        updated = svc.get(item.id)
        assert updated.title == "New title"
        assert updated.priority == TaskPriority.URGENT

    def test_show_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        item = svc.create(title="Detail task", description="Some details", tags=["info"])
        result = agent._execute_op({"op": "show", "id": item.id})
        assert result.success is True
        assert "Detail task" in result.response
        assert "Some details" in result.response
        assert "info" in result.response

    def test_show_nonexistent(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "show", "id": "nope"})
        assert result.success is False

    def test_unknown_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "explode"})
        assert result.success is False
        assert "Unknown" in result.response


class TestTodoAgentProcess:
    """Test the full _process pipeline (AI parsing → execution)."""

    @pytest.mark.asyncio
    async def test_process_create(self, tmp_path):
        ai_resp = '{"op":"create","title":"AI-parsed task","priority":"high"}'
        svc = _make_service(str(tmp_path))
        agent = TodoAgent(ai_client=FakeAIClient(ai_resp), todo_service=svc)
        result = await agent._process("add a high priority task called AI-parsed task")
        assert result.success is True
        assert "AI-parsed task" in result.response
        assert len(svc.list()) == 1

    @pytest.mark.asyncio
    async def test_process_list(self, tmp_path):
        svc = _make_service(str(tmp_path))
        svc.create(title="Existing task")
        ai_resp = '{"op":"list"}'
        agent = TodoAgent(ai_client=FakeAIClient(ai_resp), todo_service=svc)
        result = await agent._process("show my tasks")
        assert result.success is True
        assert "Existing task" in result.response

    @pytest.mark.asyncio
    async def test_process_batch_operations(self, tmp_path):
        svc = _make_service(str(tmp_path))
        ai_resp = '[{"op":"create","title":"Task A"},{"op":"create","title":"Task B"}]'
        agent = TodoAgent(ai_client=FakeAIClient(ai_resp), todo_service=svc)
        result = await agent._process("add Task A and Task B")
        assert result.success is True
        assert len(svc.list()) == 2

    @pytest.mark.asyncio
    async def test_process_invalid_json(self, tmp_path):
        svc = _make_service(str(tmp_path))
        agent = TodoAgent(ai_client=FakeAIClient("not json at all"), todo_service=svc)
        result = await agent._process("do something weird")
        assert result.success is False
        assert "couldn't understand" in result.response.lower()

    @pytest.mark.asyncio
    async def test_process_markdown_fenced_json(self, tmp_path):
        svc = _make_service(str(tmp_path))
        ai_resp = '```json\n{"op":"create","title":"Fenced"}\n```'
        agent = TodoAgent(ai_client=FakeAIClient(ai_resp), todo_service=svc)
        result = await agent._process("add fenced task")
        assert result.success is True
        assert "Fenced" in result.response


class TestTodoAgentProperties:
    """Test agent metadata."""

    def test_capabilities(self, tmp_path):
        agent, _ = TestTodoAgentOperations()._make_agent(tmp_path)
        caps = agent.capabilities
        assert "create_task" in caps
        assert "list_tasks" in caps
        assert "update_task" in caps
        assert "complete_task" in caps
        assert "delete_task" in caps

    def test_name(self, tmp_path):
        agent, _ = TestTodoAgentOperations()._make_agent(tmp_path)
        assert agent.name == "TodoAgent"

    def test_description(self, tmp_path):
        agent, _ = TestTodoAgentOperations()._make_agent(tmp_path)
        assert "task board" in agent.description.lower()
