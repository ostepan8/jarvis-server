"""Tests for SchedulerAgent and SchedulerService."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from jarvis.services.scheduler_service import SchedulerService, ScheduleItem, ScheduleType
from jarvis.agents.scheduler_agent import SchedulerAgent
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


def _make_service(tmp_path: str) -> SchedulerService:
    db_path = os.path.join(tmp_path, "test_schedules.db")
    return SchedulerService(db_path=db_path)


# =====================================================================
# SchedulerService tests — CRUD
# =====================================================================


class TestSchedulerServiceCRUD:
    """Test basic CRUD operations on the scheduler service."""

    def test_create_once_schedule(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(
            name="Morning alarm",
            schedule_type="once",
            request_text="Turn on the lights",
            run_at=run_at,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        assert isinstance(item, ScheduleItem)
        assert item.name == "Morning alarm"
        assert item.schedule_type == ScheduleType.ONCE
        assert item.request_text == "Turn on the lights"
        assert item.next_run == run_at
        assert item.enabled is True
        assert len(item.id) == 8

    def test_create_cron_schedule(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(
            name="Daily briefing",
            schedule_type="cron",
            request_text="Give me the weather",
            cron_expression="0 7 * * *",
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        assert item.schedule_type == ScheduleType.CRON
        assert item.cron_expression == "0 7 * * *"
        # next_run should be computed and in the future
        next_run_dt = datetime.fromisoformat(item.next_run)
        assert next_run_dt > datetime.now(timezone.utc) - timedelta(seconds=5)

    def test_create_interval_schedule(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(
            name="Health check",
            schedule_type="interval",
            request_text="Run system health check",
            interval_seconds=300,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        assert item.schedule_type == ScheduleType.INTERVAL
        assert item.interval_seconds == 300
        next_run_dt = datetime.fromisoformat(item.next_run)
        expected = datetime.now(timezone.utc) + timedelta(seconds=300)
        # Should be within a few seconds of now + 300s
        assert abs((next_run_dt - expected).total_seconds()) < 5

    def test_get_by_id(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        created = svc.create(
            name="Fetch task",
            schedule_type="once",
            request_text="Do something",
            run_at=run_at,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        fetched = svc.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Fetch task"

    def test_get_by_prefix(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        created = svc.create(
            name="Prefix schedule",
            schedule_type="once",
            request_text="Do it",
            run_at=run_at,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        prefix = created.id[:4]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_nonexistent(self, tmp_path):
        svc = _make_service(str(tmp_path))
        assert svc.get("nonexistent") is None

    def test_list_all(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        svc.create(name="A", schedule_type="once", request_text="a", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.create(name="B", schedule_type="once", request_text="b", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        items = svc.list()
        assert len(items) == 2

    def test_list_by_enabled(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item_a = svc.create(name="A", schedule_type="once", request_text="a", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.create(name="B", schedule_type="once", request_text="b", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.disable(item_a.id)
        enabled = svc.list(enabled=True)
        assert len(enabled) == 1
        assert enabled[0].name == "B"

    def test_list_by_type(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        svc.create(name="Once", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.create(name="Cron", schedule_type="cron", request_text="y", cron_expression="0 7 * * *", timezone="UTC", user_id=1, created_by="user")
        cron_items = svc.list(schedule_type="cron")
        assert len(cron_items) == 1
        assert cron_items[0].name == "Cron"

    def test_update_fields(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Original", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        updated = svc.update(item.id, name="Changed")
        assert updated is not None
        assert updated.name == "Changed"

    def test_delete(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Delete me", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        assert svc.delete(item.id) is True
        assert svc.get(item.id) is None

    def test_delete_nonexistent(self, tmp_path):
        svc = _make_service(str(tmp_path))
        assert svc.delete("nonexistent") is False

    def test_enable_disable(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Toggle me", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")

        disabled = svc.disable(item.id)
        assert disabled is not None
        assert disabled.enabled is False

        enabled = svc.enable(item.id)
        assert enabled is not None
        assert enabled.enabled is True


# =====================================================================
# SchedulerService tests — tick / firing logic
# =====================================================================


class TestSchedulerServiceTick:
    """Test scheduling tick and fire logic."""

    def test_get_due_schedules_past(self, tmp_path):
        svc = _make_service(str(tmp_path))
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        svc.create(name="Overdue", schedule_type="once", request_text="late", run_at=past, timezone="UTC", user_id=1, created_by="user")
        due = svc.get_due_schedules()
        assert len(due) == 1
        assert due[0].name == "Overdue"

    def test_get_due_schedules_future(self, tmp_path):
        svc = _make_service(str(tmp_path))
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        svc.create(name="Not yet", schedule_type="once", request_text="later", run_at=future, timezone="UTC", user_id=1, created_by="user")
        due = svc.get_due_schedules()
        assert len(due) == 0

    def test_get_due_schedules_disabled(self, tmp_path):
        svc = _make_service(str(tmp_path))
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        item = svc.create(name="Disabled", schedule_type="once", request_text="off", run_at=past, timezone="UTC", user_id=1, created_by="user")
        svc.disable(item.id)
        due = svc.get_due_schedules()
        assert len(due) == 0

    def test_mark_fired_once_disables(self, tmp_path):
        svc = _make_service(str(tmp_path))
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        item = svc.create(name="One-shot", schedule_type="once", request_text="fire", run_at=past, timezone="UTC", user_id=1, created_by="user")
        fired = svc.mark_fired(item.id)
        assert fired is not None
        assert fired.enabled is False

    def test_mark_fired_cron_advances(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(
            name="Recurring cron",
            schedule_type="cron",
            request_text="repeat",
            cron_expression="0 7 * * *",
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        # Manually set next_run to the past so it's due
        svc.update(item.id, next_run=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat())
        fired = svc.mark_fired(item.id)
        assert fired is not None
        assert fired.last_run is not None
        next_run_dt = datetime.fromisoformat(fired.next_run)
        assert next_run_dt > datetime.now(timezone.utc)

    def test_mark_fired_interval_advances(self, tmp_path):
        svc = _make_service(str(tmp_path))
        item = svc.create(
            name="Every 5min",
            schedule_type="interval",
            request_text="check",
            interval_seconds=300,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )
        # Set next_run to the past
        svc.update(item.id, next_run=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
        fired = svc.mark_fired(item.id)
        assert fired is not None
        next_run_dt = datetime.fromisoformat(fired.next_run)
        expected = datetime.now(timezone.utc) + timedelta(seconds=300)
        assert abs((next_run_dt - expected).total_seconds()) < 5


# =====================================================================
# SchedulerAgent tests — operation dispatch
# =====================================================================


class TestSchedulerAgentOperations:
    """Test the agent's operation dispatch (no network needed)."""

    def _make_agent(self, tmp_path, ai_response='{"op":"list"}'):
        svc = _make_service(str(tmp_path))
        client = FakeAIClient(ai_response)
        return SchedulerAgent(ai_client=client, scheduler_service=svc, logger=None), svc

    def test_schedule_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        result = agent._execute_op({
            "op": "schedule",
            "name": "Test schedule",
            "schedule_type": "once",
            "request_text": "Turn on lights",
            "run_at": run_at,
            "timezone": "UTC",
        })
        assert result.success is True
        assert "Test schedule" in result.response
        items = svc.list()
        assert len(items) == 1

    def test_list_op_empty(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "list"})
        assert result.success is True

    def test_list_op_with_items(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        svc.create(name="Sched A", schedule_type="once", request_text="a", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.create(name="Sched B", schedule_type="once", request_text="b", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        result = agent._execute_op({"op": "list"})
        assert result.success is True
        assert "Sched A" in result.response
        assert "Sched B" in result.response

    def test_cancel_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Doomed", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        result = agent._execute_op({"op": "cancel", "id": item.id})
        assert result.success is True
        assert svc.get(item.id) is None

    def test_cancel_nonexistent(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "cancel", "id": "nope"})
        assert result.success is False
        assert "not found" in result.response.lower()

    def test_pause_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Pausable", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        result = agent._execute_op({"op": "pause", "id": item.id})
        assert result.success is True
        fetched = svc.get(item.id)
        assert fetched.enabled is False

    def test_resume_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        item = svc.create(name="Resumable", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        svc.disable(item.id)
        result = agent._execute_op({"op": "resume", "id": item.id})
        assert result.success is True
        fetched = svc.get(item.id)
        assert fetched.enabled is True

    def test_unknown_op(self, tmp_path):
        agent, svc = self._make_agent(tmp_path)
        result = agent._execute_op({"op": "explode"})
        assert result.success is False
        assert "Unknown" in result.response


# =====================================================================
# SchedulerAgent tests — full _process pipeline
# =====================================================================


class TestSchedulerAgentProcess:
    """Test the full _process pipeline (AI parsing -> execution)."""

    @pytest.mark.asyncio
    async def test_process_schedule(self, tmp_path):
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        ai_resp = (
            '{"op":"schedule","name":"AI-created",'
            f'"schedule_type":"once","request_text":"Do it","run_at":"{run_at}","timezone":"UTC"}}'
        )
        svc = _make_service(str(tmp_path))
        agent = SchedulerAgent(ai_client=FakeAIClient(ai_resp), scheduler_service=svc)
        result = await agent._process("schedule a one-time task")
        assert result.success is True
        assert "AI-created" in result.response
        assert len(svc.list()) == 1

    @pytest.mark.asyncio
    async def test_process_list(self, tmp_path):
        svc = _make_service(str(tmp_path))
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        svc.create(name="Existing", schedule_type="once", request_text="x", run_at=run_at, timezone="UTC", user_id=1, created_by="user")
        ai_resp = '{"op":"list"}'
        agent = SchedulerAgent(ai_client=FakeAIClient(ai_resp), scheduler_service=svc)
        result = await agent._process("show my schedules")
        assert result.success is True
        assert "Existing" in result.response

    @pytest.mark.asyncio
    async def test_process_invalid_json(self, tmp_path):
        svc = _make_service(str(tmp_path))
        agent = SchedulerAgent(ai_client=FakeAIClient("not json at all"), scheduler_service=svc)
        result = await agent._process("do something weird")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_process_markdown_fenced(self, tmp_path):
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        ai_resp = (
            '```json\n'
            '{"op":"schedule","name":"Fenced",'
            f'"schedule_type":"once","request_text":"Go","run_at":"{run_at}","timezone":"UTC"}}\n'
            '```'
        )
        svc = _make_service(str(tmp_path))
        agent = SchedulerAgent(ai_client=FakeAIClient(ai_resp), scheduler_service=svc)
        result = await agent._process("add a fenced schedule")
        assert result.success is True
        assert "Fenced" in result.response


# =====================================================================
# SchedulerAgent tests — metadata properties
# =====================================================================


class TestSchedulerAgentProperties:
    """Test agent metadata."""

    def test_capabilities(self, tmp_path):
        agent, _ = TestSchedulerAgentOperations()._make_agent(tmp_path)
        caps = agent.capabilities
        assert len(caps) >= 5
        # The five expected capabilities
        expected = {
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "pause_schedule",
            "resume_schedule",
        }
        assert expected == caps

    def test_name(self, tmp_path):
        agent, _ = TestSchedulerAgentOperations()._make_agent(tmp_path)
        assert agent.name == "SchedulerAgent"

    def test_description(self, tmp_path):
        agent, _ = TestSchedulerAgentOperations()._make_agent(tmp_path)
        assert "schedule" in agent.description.lower()


# =====================================================================
# SchedulerAgent tests — tick loop / firing
# =====================================================================


class TestSchedulerTickLoop:
    """Test the tick/fire mechanism."""

    @pytest.mark.asyncio
    async def test_fire_schedule_calls_orchestrator(self, tmp_path):
        svc = _make_service(str(tmp_path))
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        item = svc.create(
            name="Fire me",
            schedule_type="once",
            request_text="Turn on all lights",
            run_at=past,
            timezone="UTC",
            user_id=1,
            created_by="user",
        )

        client = FakeAIClient()
        agent = SchedulerAgent(ai_client=client, scheduler_service=svc, logger=None)

        # Mock the orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.process_request = AsyncMock(return_value={"success": True})
        agent.set_orchestrator(mock_orchestrator)

        await agent._fire_schedule(item)

        mock_orchestrator.process_request.assert_called_once_with(
            user_input="Turn on all lights",
            tz_name="UTC",
            metadata={"source": "scheduler", "schedule_id": item.id},
        )
