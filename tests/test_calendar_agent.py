"""Comprehensive tests for CalendarAgent, CalendarCommandProcessor, and CalendarFunctionRegistry."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.agents.calendar_agent import (
    CollaborativeCalendarAgent,
    CalendarCommandProcessor,
    CalendarFunctionRegistry,
)
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient
from jarvis.services.calendar_service import CalendarService
from jarvis.utils import safe_json_dumps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ai_client(content="Done.", tool_calls=None):
    """Build a mock AI client returning the given content/tool_calls."""
    client = MagicMock(spec=BaseAIClient)
    msg = MagicMock()
    msg.content = content
    msg.model_dump = MagicMock(return_value={"role": "assistant", "content": content})
    client.weak_chat = AsyncMock(return_value=(msg, tool_calls))
    client.strong_chat = AsyncMock(return_value=(msg, None))
    return client


def _make_tool_call(name, arguments, call_id="call-1"):
    """Build a mock tool call object matching the OpenAI shape."""
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def _make_calendar_service():
    """Build a mock CalendarService with common stubs."""
    service = MagicMock(spec=CalendarService)
    service.current_date.return_value = "2026-03-17"
    service.get_all_events = AsyncMock(return_value=[])
    service.get_next_event = AsyncMock(return_value=None)
    service.get_today_events = AsyncMock(return_value=[])
    service.get_tomorrow_events = AsyncMock(return_value=[])
    service.get_events_by_date = AsyncMock(return_value=[])
    service.get_month_events = AsyncMock(return_value=[])
    service.get_week_events = AsyncMock(return_value=[])
    service.search_events = AsyncMock(return_value=[])
    service.get_events_in_range = AsyncMock(return_value=[])
    service.get_events_by_duration = AsyncMock(return_value=[])
    service.get_categories = AsyncMock(return_value=[])
    service.get_events_by_category = AsyncMock(return_value=[])
    service.check_conflicts = AsyncMock(return_value={"conflicts": []})
    service.validate_event_time = AsyncMock(return_value={"valid": True})
    service.find_free_slots = AsyncMock(return_value=[])
    service.find_next_available_slot = AsyncMock(return_value=None)
    service.add_event = AsyncMock(return_value={"id": "evt-1", "title": "Meeting"})
    service.update_event = AsyncMock(return_value={"id": "evt-1"})
    service.update_event_fields = AsyncMock(return_value={"id": "evt-1"})
    service.reschedule_event = AsyncMock(return_value={"id": "evt-1"})
    service.get_recurring_events = AsyncMock(return_value=[])
    service.add_recurring_event = AsyncMock(return_value={"id": "rec-1"})
    service.update_recurring_event = AsyncMock(return_value={"id": "rec-1"})
    service.delete_recurring_event = AsyncMock(return_value=True)
    service.add_events_bulk = AsyncMock(return_value=[])
    service.delete_events_bulk = AsyncMock(return_value=[])
    service.delete_event = AsyncMock(return_value=True)
    service.delete_all_events = AsyncMock(return_value=True)
    service.delete_events_by_date = AsyncMock(return_value=0)
    service.delete_events_in_week = AsyncMock(return_value=0)
    service.delete_events_before = AsyncMock(return_value=0)
    service.get_deleted_events = AsyncMock(return_value=[])
    service.restore_event = AsyncMock(return_value=True)
    service.get_schedule_summary = AsyncMock(return_value={})
    service.get_busy_days = AsyncMock(return_value=[])
    service.get_overlapping_events = AsyncMock(return_value=[])
    service.get_event_by_id = AsyncMock(return_value=None)
    service.get_event_stats = AsyncMock(return_value={})
    service.find_best_time_for_event = AsyncMock(return_value=None)
    return service


def _make_agent(ai_client=None, calendar_service=None):
    """Build a CollaborativeCalendarAgent with mock dependencies."""
    client = ai_client or _make_ai_client()
    service = calendar_service or _make_calendar_service()
    agent = CollaborativeCalendarAgent(
        ai_client=client,
        calendar_service=service,
    )
    # Stub network so send_message doesn't blow up
    agent.network = MagicMock()
    agent.network.send_message = AsyncMock()
    return agent


def _make_capability_message(
    capability, prompt="test prompt", data_extra=None, from_agent="tester",
    request_id="req-1",
):
    """Build a capability_request Message for CalendarAgent."""
    data = {"prompt": prompt}
    if data_extra:
        data.update(data_extra)
    return Message(
        from_agent=from_agent,
        to_agent="CalendarAgent",
        message_type="capability_request",
        content={"capability": capability, "data": data},
        request_id=request_id,
    )


# ===========================================================================
# Tests: safe_json_dumps utility
# ===========================================================================

class TestSafeJsonDumps:
    """Tests for the shared safe_json_dumps utility."""

    def test_serializable_dict(self):
        result = safe_json_dumps({"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_serializable_list(self):
        result = safe_json_dumps([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_non_serializable_with_dict_attr(self):
        class Obj:
            def __init__(self):
                self.x = 42
        result = safe_json_dumps(Obj())
        assert json.loads(result) == {"x": 42}

    def test_non_serializable_fallback_to_str(self):
        result = safe_json_dumps(object())
        assert isinstance(result, str)
        assert "object" in result

    def test_function_serializes_to_dict(self):
        """Functions have an empty __dict__ which serializes to '{}'."""
        def my_func():
            pass
        result = safe_json_dumps(my_func)
        # Functions have __dict__ which is {} — serializes fine
        assert isinstance(result, str)

    def test_nested_non_serializable_falls_back(self):
        """Object whose __dict__ is also non-serializable."""
        class Inner:
            def __init__(self):
                self.ref = object()  # not JSON-able
        result = safe_json_dumps(Inner())
        assert isinstance(result, str)


# ===========================================================================
# Tests: CalendarFunctionRegistry
# ===========================================================================

class TestCalendarFunctionRegistry:
    """Tests for CalendarFunctionRegistry."""

    def test_capabilities_is_nonempty_set(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        caps = registry.capabilities
        assert isinstance(caps, set)
        assert len(caps) > 0

    def test_core_capabilities_present(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        expected = {
            "add_event", "delete_event", "get_all_events",
            "search_events", "get_today_events", "check_conflicts",
        }
        assert expected.issubset(registry.capabilities)

    def test_alias_capabilities_present(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        assert "schedule_appointment" in registry.capabilities
        assert "cancel_appointment" in registry.capabilities

    def test_get_function_returns_callable(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        func = registry.get_function("add_event")
        assert callable(func)

    def test_get_function_unknown_returns_none(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        assert registry.get_function("nonexistent_capability") is None

    def test_has_function(self):
        service = _make_calendar_service()
        registry = CalendarFunctionRegistry(service)
        assert registry.has_function("add_event") is True
        assert registry.has_function("fake") is False


# ===========================================================================
# Tests: CalendarCommandProcessor
# ===========================================================================

class TestCalendarCommandProcessor:
    """Tests for CalendarCommandProcessor."""

    def _make_processor(self, ai_client=None, calendar_service=None):
        service = calendar_service or _make_calendar_service()
        client = ai_client or _make_ai_client()
        registry = CalendarFunctionRegistry(service)
        from jarvis.agents.calendar_agent.tools.tools import tools
        return CalendarCommandProcessor(
            ai_client=client,
            calendar_service=service,
            function_registry=registry,
            tools=tools,
        )

    # --- execute_function ---

    @pytest.mark.asyncio
    async def test_execute_function_unknown_returns_error(self):
        proc = self._make_processor()
        result = await proc.execute_function("totally_fake", {})
        assert "error" in result
        assert "Unknown function" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_function_success(self):
        service = _make_calendar_service()
        service.get_today_events = AsyncMock(return_value=[{"id": "e1", "title": "Standup"}])
        proc = self._make_processor(calendar_service=service)
        result = await proc.execute_function("get_today_events", {})
        assert result == [{"id": "e1", "title": "Standup"}]

    @pytest.mark.asyncio
    async def test_execute_function_exception_returns_error_dict(self):
        service = _make_calendar_service()
        service.add_event = AsyncMock(side_effect=ValueError("bad date"))
        proc = self._make_processor(calendar_service=service)
        result = await proc.execute_function("add_event", {"title": "x", "date": "bad", "time": "bad"})
        assert "error" in result
        assert "bad date" in result["error"]
        assert result["function"] == "add_event"

    @pytest.mark.asyncio
    async def test_execute_function_working_hours_tuple_conversion(self):
        """The working_hours list->tuple conversion fires for find_best_time_for_event."""
        service = _make_calendar_service()
        captured_args = {}

        async def capture(**kwargs):
            captured_args.update(kwargs)
            return {"slot": "09:00"}

        proc = self._make_processor(calendar_service=service)
        # Inject the function into the registry so execute_function can find it
        proc.function_registry.add_function("find_best_time_for_event", capture)

        await proc.execute_function(
            "find_best_time_for_event",
            {"duration_minutes": 60, "preferred_dates": ["2026-03-20"], "working_hours": [9, 17]},
        )
        assert isinstance(captured_args["working_hours"], tuple)
        assert captured_args["working_hours"] == (9, 17)

    # --- process_command ---

    @pytest.mark.asyncio
    async def test_process_command_no_tool_calls_returns_success(self):
        """When the LLM responds with text only (no tool calls), return success."""
        client = _make_ai_client(content="You have no events today.")
        proc = self._make_processor(ai_client=client)
        result = await proc.process_command("What's on my calendar?")
        assert result["success"] is True
        assert "no events" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_process_command_with_tool_call(self):
        """When LLM issues a tool call, execute it and return the result."""
        service = _make_calendar_service()
        service.get_today_events = AsyncMock(return_value=[{"id": "e1", "title": "Standup"}])

        tool_call = _make_tool_call("get_today_events", {})

        # First call returns tool_call, second call returns final text
        msg_with_tools = MagicMock()
        msg_with_tools.content = ""
        msg_with_tools.model_dump = MagicMock(
            return_value={"role": "assistant", "content": ""}
        )
        msg_final = MagicMock()
        msg_final.content = "You have a standup today."

        client = MagicMock(spec=BaseAIClient)
        client.weak_chat = AsyncMock(
            side_effect=[
                (msg_with_tools, [tool_call]),
                (msg_final, None),
            ]
        )

        proc = self._make_processor(ai_client=client, calendar_service=service)
        result = await proc.process_command("Show today's events")

        assert result["success"] is True
        assert len(result.get("actions", [])) == 1
        assert result["actions"][0]["function"] == "get_today_events"

    @pytest.mark.asyncio
    async def test_process_command_tool_call_with_error_returns_error_response(self):
        """When a tool call produces an error, the response should flag it."""
        service = _make_calendar_service()
        service.add_event = AsyncMock(side_effect=RuntimeError("conflict"))

        tool_call = _make_tool_call(
            "add_event",
            {"title": "Meeting", "date": "2026-03-17", "time": "10:00"},
        )

        msg_with_tools = MagicMock()
        msg_with_tools.content = ""
        msg_with_tools.model_dump = MagicMock(
            return_value={"role": "assistant", "content": ""}
        )
        msg_final = MagicMock()
        msg_final.content = "Failed to add event."

        client = MagicMock(spec=BaseAIClient)
        client.weak_chat = AsyncMock(
            side_effect=[
                (msg_with_tools, [tool_call]),
                (msg_final, None),
            ]
        )

        proc = self._make_processor(ai_client=client, calendar_service=service)
        result = await proc.process_command("Add a meeting at 10")

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["error_type"] == "FunctionExecutionError"

    @pytest.mark.asyncio
    async def test_process_command_max_iterations_guard(self):
        """Ensure the loop terminates after MAX_ITERATIONS."""
        tool_call = _make_tool_call("get_today_events", {})

        msg = MagicMock()
        msg.content = ""
        msg.model_dump = MagicMock(return_value={"role": "assistant", "content": ""})

        # Always return tool calls so the loop never naturally breaks
        client = MagicMock(spec=BaseAIClient)
        client.weak_chat = AsyncMock(return_value=(msg, [tool_call]))

        proc = self._make_processor(ai_client=client)
        result = await proc.process_command("loop forever")

        # Should still return a result (not hang)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_process_command_ai_client_exception_in_loop(self):
        """If the AI client throws inside the loop, the loop breaks gracefully."""
        client = MagicMock(spec=BaseAIClient)
        client.weak_chat = AsyncMock(side_effect=ConnectionError("API down"))

        proc = self._make_processor(ai_client=client)
        result = await proc.process_command("anything")

        # Inner loop catches the exception and breaks; returns "No response generated"
        assert result["success"] is True
        assert result["response"] == "No response generated"

    @pytest.mark.asyncio
    async def test_process_command_outer_exception_returns_error(self):
        """If something fails before the loop, the outer handler catches it."""
        service = _make_calendar_service()
        service.current_date.side_effect = RuntimeError("service down")

        proc = self._make_processor(calendar_service=service)
        result = await proc.process_command("anything")

        assert result["success"] is False
        assert "service down" in result["response"]

    @pytest.mark.asyncio
    async def test_process_command_no_response_message(self):
        """When weak_chat returns None message with no tool calls."""
        client = MagicMock(spec=BaseAIClient)
        client.weak_chat = AsyncMock(return_value=(None, None))

        proc = self._make_processor(ai_client=client)
        result = await proc.process_command("hello")

        assert result["success"] is True
        assert result["response"] == "No response generated"


# ===========================================================================
# Tests: CollaborativeCalendarAgent — properties
# ===========================================================================

class TestCalendarAgentProperties:
    """Test agent metadata and configuration."""

    def test_name(self):
        agent = _make_agent()
        assert agent.name == "CalendarAgent"

    def test_description_mentions_calendar(self):
        agent = _make_agent()
        assert "calendar" in agent.description.lower()

    def test_capabilities_nonempty(self):
        agent = _make_agent()
        assert len(agent.capabilities) > 0

    def test_capabilities_contains_core_ops(self):
        agent = _make_agent()
        assert "add_event" in agent.capabilities
        assert "delete_event" in agent.capabilities
        assert "get_all_events" in agent.capabilities

    def test_supports_dialogue(self):
        agent = _make_agent()
        assert agent.supports_dialogue is True


# ===========================================================================
# Tests: CollaborativeCalendarAgent — capability request handling
# ===========================================================================

class TestCalendarAgentCapabilityRequest:
    """Test _handle_capability_request paths."""

    @pytest.mark.asyncio
    async def test_unknown_capability_silently_returns(self):
        agent = _make_agent()
        msg = _make_capability_message("totally_fake_capability")
        # Should not raise, should not send anything
        await agent._handle_capability_request(msg)
        agent.network.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_prompt_sends_error(self):
        agent = _make_agent()
        msg = Message(
            from_agent="tester",
            to_agent="CalendarAgent",
            message_type="capability_request",
            content={
                "capability": "add_event",
                "data": {"prompt": 12345},  # not a string
            },
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        # Should have sent an error message
        agent.network.send_message.assert_called_once()
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "error"
        assert "Invalid prompt" in sent_msg.content["error"]

    @pytest.mark.asyncio
    async def test_missing_prompt_sends_error(self):
        agent = _make_agent()
        msg = Message(
            from_agent="tester",
            to_agent="CalendarAgent",
            message_type="capability_request",
            content={
                "capability": "add_event",
                "data": {},  # no prompt key at all
            },
            request_id="req-2",
        )
        await agent._handle_capability_request(msg)
        agent.network.send_message.assert_called_once()
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "error"

    @pytest.mark.asyncio
    async def test_valid_prompt_processes_and_responds(self):
        client = _make_ai_client(content="All clear on the calendar front.")
        agent = _make_agent(ai_client=client)
        msg = _make_capability_message("add_event", prompt="Show my events")
        await agent._handle_capability_request(msg)
        # Should send a capability_response
        assert agent.network.send_message.call_count >= 1
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "capability_response"

    @pytest.mark.asyncio
    async def test_command_processor_exception_sends_error(self):
        """When process_command itself raises, the agent catches it and sends error."""
        agent = _make_agent()
        agent.command_processor.process_command = AsyncMock(
            side_effect=RuntimeError("kaboom")
        )
        msg = _make_capability_message("add_event", prompt="Add meeting")
        await agent._handle_capability_request(msg)
        # Should send error, not raise
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "error"
        assert "kaboom" in sent_msg.content["error"]

    @pytest.mark.asyncio
    async def test_dialogue_context_delegates_to_respond_to_dialogue(self):
        """When dialogue_context is present, delegate to _respond_to_dialogue."""
        agent = _make_agent()
        agent._respond_to_dialogue = AsyncMock(return_value={"response": "dialogue ok", "success": True})
        msg = Message(
            from_agent="LeadAgent",
            to_agent="CalendarAgent",
            message_type="capability_request",
            content={
                "capability": "add_event",
                "data": {
                    "prompt": "Can you check my schedule?",
                    "dialogue_context": {
                        "goal": "schedule coordination",
                        "transcript": "",
                        "capability": "add_event",
                    },
                },
            },
            request_id="req-d",
        )
        await agent._handle_capability_request(msg)
        agent._respond_to_dialogue.assert_called_once()
        # Should send a capability_response (not error)
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "capability_response"


# ===========================================================================
# Tests: CollaborativeCalendarAgent — capability response handling
# ===========================================================================

class TestCalendarAgentCapabilityResponse:
    """Test _handle_capability_response."""

    @pytest.mark.asyncio
    async def test_unknown_request_id_is_ignored(self):
        agent = _make_agent()
        msg = Message(
            from_agent="SearchAgent",
            to_agent="CalendarAgent",
            message_type="capability_response",
            content={"data": "sunny"},
            request_id="unknown-req",
        )
        # Should not raise
        await agent._handle_capability_response(msg)

    @pytest.mark.asyncio
    async def test_known_request_id_stores_response(self):
        agent = _make_agent()
        agent.active_tasks["req-1"] = {
            "data": {},
            "original_requester": "tester",
            "original_message_id": "msg-1",
            "responses": [],
        }
        msg = Message(
            from_agent="SearchAgent",
            to_agent="CalendarAgent",
            message_type="capability_response",
            content={"forecast": "rain"},
            request_id="req-1",
        )
        await agent._handle_capability_response(msg)
        assert len(agent.active_tasks["req-1"]["responses"]) == 1
        assert agent.active_tasks["req-1"]["responses"][0]["from_agent"] == "SearchAgent"


# ===========================================================================
# Tests: CollaborativeCalendarAgent — run_capability
# ===========================================================================

class TestCalendarAgentRunCapability:
    """Test run_capability dispatch."""

    @pytest.mark.asyncio
    async def test_run_known_capability(self):
        service = _make_calendar_service()
        service.get_today_events = AsyncMock(return_value=[{"id": "e1"}])
        agent = _make_agent(calendar_service=service)
        result = await agent.run_capability("get_today_events")
        assert result == [{"id": "e1"}]

    @pytest.mark.asyncio
    async def test_run_unknown_capability_raises(self):
        agent = _make_agent()
        with pytest.raises(NotImplementedError, match="not implemented"):
            await agent.run_capability("warp_drive_engage")


# ===========================================================================
# Tests: CollaborativeCalendarAgent — error handling
# ===========================================================================

class TestCalendarAgentSendError:
    """Test the overridden send_error method."""

    @pytest.mark.asyncio
    async def test_send_error_dispatches_error_message(self):
        agent = _make_agent()
        await agent.send_error("Orchestrator", "something broke", "req-1")
        agent.network.send_message.assert_called_once()
        sent_msg = agent.network.send_message.call_args[0][0]
        assert sent_msg.message_type == "error"
        assert sent_msg.content["error"] == "something broke"

    @pytest.mark.asyncio
    async def test_send_error_survives_network_failure(self):
        agent = _make_agent()
        agent.network.send_message = AsyncMock(side_effect=RuntimeError("network down"))
        # Should not raise — error is logged, not propagated
        await agent.send_error("Orchestrator", "oops", "req-1")


# ===========================================================================
# Tests: CollaborativeCalendarAgent — lead agent support
# ===========================================================================

class TestCalendarAgentLeadSupport:
    """Test _build_lead_system_prompt."""

    def test_lead_prompt_mentions_scheduling(self):
        agent = _make_agent()
        # Minimal MissionBrief mock
        brief = MagicMock()
        brief.user_input = "Schedule a meeting and search for restaurants"
        brief.available_capabilities = {
            "CalendarAgent": ["add_event"],
            "SearchAgent": ["search"],
        }
        prompt = agent._build_lead_system_prompt(brief)
        assert "scheduling" in prompt.lower()
        assert "SearchAgent" in prompt


# ===========================================================================
# Tests: CollaborativeCalendarAgent — active tasks
# ===========================================================================

class TestCalendarAgentActiveTasks:
    """Test get_active_tasks."""

    def test_returns_copy_of_top_level(self):
        agent = _make_agent()
        agent.active_tasks["req-1"] = {"data": "stuff"}
        tasks = agent.get_active_tasks()
        assert tasks == {"req-1": {"data": "stuff"}}
        # Adding a new key to the copy should not affect the original
        tasks["req-new"] = {"data": "extra"}
        assert "req-new" not in agent.active_tasks
