"""Comprehensive tests for CanvasAgent."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from jarvis.agents.canvas import CanvasAgent
from jarvis.agents.message import Message
from jarvis.ai_clients.base import BaseAIClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyAIClient(BaseAIClient):
    """AI client that returns a simple text response with no tool calls."""

    def __init__(self, response_text="Here is your Canvas data."):
        self._response_text = response_text

    async def strong_chat(self, messages, tools=None):
        msg = MagicMock()
        msg.content = self._response_text
        msg.model_dump = MagicMock(return_value={
            "role": "assistant",
            "content": self._response_text,
        })
        return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = MagicMock()
        msg.content = self._response_text
        return msg, None


class ToolCallAIClient(BaseAIClient):
    """AI client that issues a tool call on first round, then returns text."""

    def __init__(self, tool_name, tool_args, final_response="Done", tool_result=None):
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._final_response = final_response
        self._tool_result = tool_result or {"success": True, "message": "ok"}
        self._call_count = 0

    async def strong_chat(self, messages, tools=None):
        self._call_count += 1
        if self._call_count == 1:
            func = MagicMock()
            func.name = self._tool_name
            func.arguments = json.dumps(self._tool_args)
            call = MagicMock()
            call.id = "call_001"
            call.function = func
            msg = MagicMock()
            msg.content = None
            msg.model_dump = MagicMock(return_value={
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_001",
                    "type": "function",
                    "function": {
                        "name": self._tool_name,
                        "arguments": json.dumps(self._tool_args),
                    }
                }],
            })
            return msg, [call]
        else:
            msg = MagicMock()
            msg.content = self._final_response
            return msg, None

    async def weak_chat(self, messages, tools=None):
        msg = MagicMock()
        msg.content = "dummy"
        return msg, None


def _make_mock_canvas_service():
    """Create a mock CanvasService with all expected methods."""
    service = MagicMock()
    service.get_courses = AsyncMock(return_value={"success": True, "courses": []})
    service.get_current_courses = AsyncMock(return_value={
        "success": True,
        "current_courses": 3,
        "total_courses": 5,
        "courses": [],
    })
    service.get_enrollments = AsyncMock(return_value={"success": True, "enrollments": []})
    service.get_course_assignments = AsyncMock(return_value={"success": True, "assignments": []})
    service.get_todo = AsyncMock(return_value={"success": True, "todos": []})
    service.get_calendar_events = AsyncMock(return_value={"success": True, "events": []})
    service.get_notifications = AsyncMock(return_value={"success": True, "notifications": []})
    service.get_messages = AsyncMock(return_value={"success": True, "messages": []})
    service.get_homework_summary = AsyncMock(return_value={
        "success": True,
        "homework_summary": {
            "weekend_homework": [],
            "overdue_homework": [],
            "upcoming_homework": [],
            "weekend_count": 0,
        },
    })
    service.get_comprehensive_homework = AsyncMock(return_value={
        "success": True,
        "weekend_homework": [],
        "due_soon": [],
        "total_assignments": 0,
        "weekend_homework_count": 0,
        "due_soon_count": 0,
    })
    return service


def _make_canvas_message(capability, prompt="What's my homework?",
                         from_agent="tester", request_id="req-1", context=None):
    """Build a capability_request Message for CanvasAgent."""
    data = {"prompt": prompt}
    if context is not None:
        data["context"] = context
    return Message(
        from_agent=from_agent,
        to_agent="CanvasAgent",
        message_type="capability_request",
        content={"capability": capability, "data": data},
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Tests: metadata & properties
# ---------------------------------------------------------------------------

class TestCanvasAgentProperties:
    """Test CanvasAgent metadata and configuration."""

    def test_name(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        assert agent.name == "CanvasAgent"

    def test_description(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        assert "Canvas" in agent.description

    def test_capabilities_include_all_intents(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        expected_caps = {
            "get_courses", "get_current_courses", "get_enrollments",
            "get_course_assignments", "get_todo", "get_calendar_events",
            "get_notifications", "get_messages", "get_homework_summary",
            "get_comprehensive_homework",
        }
        assert agent.capabilities == expected_caps

    def test_tools_defined(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        assert isinstance(agent.tools, list)
        assert len(agent.tools) > 0
        # Verify tool names match intent_map
        tool_names = {t["function"]["name"] for t in agent.tools}
        for name in tool_names:
            assert name in agent.intent_map

    def test_system_prompt_exists(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        assert isinstance(agent.system_prompt, str)
        assert "Canvas" in agent.system_prompt


# ---------------------------------------------------------------------------
# Tests: _execute_function
# ---------------------------------------------------------------------------

class TestExecuteFunction:
    """Test the _execute_function method."""

    @pytest.mark.asyncio
    async def test_execute_known_function(self):
        """Known functions are delegated to the service."""
        service = _make_mock_canvas_service()
        service.get_todo.return_value = {"success": True, "todos": ["item1"]}
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = await agent._execute_function("get_todo", {})
        assert result["success"] is True
        assert result["todos"] == ["item1"]
        service.get_todo.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_function(self):
        """Unknown functions return an error dict."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = await agent._execute_function("nonexistent_function", {})
        assert result["success"] is False
        assert "Unknown function" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_function_with_arguments(self):
        """Arguments are passed through to the service method."""
        service = _make_mock_canvas_service()
        service.get_course_assignments.return_value = {
            "success": True,
            "assignments": [{"name": "HW1"}],
        }
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = await agent._execute_function(
            "get_course_assignments",
            {"course_id": "123", "recent_only": True},
        )
        assert result["success"] is True
        service.get_course_assignments.assert_called_once_with(
            course_id="123", recent_only=True
        )

    @pytest.mark.asyncio
    async def test_execute_function_exception(self):
        """Exceptions from the service are caught and returned as error dict."""
        service = _make_mock_canvas_service()
        service.get_courses.side_effect = ConnectionError("API down")
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = await agent._execute_function("get_courses", {})
        assert result["success"] is False
        assert "API down" in result["error"]


# ---------------------------------------------------------------------------
# Tests: _process_canvas_command
# ---------------------------------------------------------------------------

class TestProcessCanvasCommand:
    """Test the LLM-driven command processing loop."""

    @pytest.mark.asyncio
    async def test_simple_response_no_tool_calls(self):
        """When AI returns text with no tool calls, result is immediate."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient("Your courses are: Math, Science"),
                            canvas_service=service)

        result = await agent._process_canvas_command("What are my courses?")
        assert result["success"] is True
        assert "Math, Science" in result["response"]
        assert result.get("actions", []) == []

    @pytest.mark.asyncio
    async def test_command_with_tool_call(self):
        """Tool calls are executed and fed back into the LLM."""
        service = _make_mock_canvas_service()
        service.get_todo.return_value = {"success": True, "todos": ["Study"]}

        ai = ToolCallAIClient("get_todo", {}, "You need to study.", service.get_todo.return_value)
        agent = CanvasAgent(ai_client=ai, canvas_service=service)

        result = await agent._process_canvas_command("What's on my to-do list?")
        assert result["success"] is True
        assert len(result["actions"]) >= 1
        assert result["actions"][0]["function"] == "get_todo"

    @pytest.mark.asyncio
    async def test_command_context_length_exceeded(self):
        """Context length error is handled gracefully."""

        class ContextErrorAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                raise Exception("context_length_exceeded: too many tokens")

            async def weak_chat(self, messages, tools=None):
                msg = MagicMock()
                msg.content = "dummy"
                return msg, None

        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=ContextErrorAIClient(), canvas_service=service)

        result = await agent._process_canvas_command("lots of data")
        assert result["success"] is False
        assert "too large" in result["error"].lower() or "specific" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_command_general_error(self):
        """General LLM errors are handled gracefully."""

        class ErrorAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                raise RuntimeError("LLM service unavailable")

            async def weak_chat(self, messages, tools=None):
                msg = MagicMock()
                msg.content = "dummy"
                return msg, None

        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=ErrorAIClient(), canvas_service=service)

        result = await agent._process_canvas_command("test")
        assert result["success"] is False
        assert "LLM service unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Command processing stops after MAX_ITERATIONS (5) tool-call rounds."""
        call_count = 0

        class InfiniteToolAIClient(BaseAIClient):
            async def strong_chat(self, messages, tools=None):
                nonlocal call_count
                call_count += 1
                func = MagicMock()
                func.name = "get_todo"
                func.arguments = json.dumps({})
                call_obj = MagicMock()
                call_obj.id = f"call_{call_count}"
                call_obj.function = func
                msg = MagicMock()
                msg.content = f"iteration {call_count}"
                msg.model_dump = MagicMock(return_value={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": f"call_{call_count}",
                        "type": "function",
                        "function": {"name": "get_todo", "arguments": "{}"},
                    }]
                })
                return msg, [call_obj]

            async def weak_chat(self, messages, tools=None):
                msg = MagicMock()
                msg.content = "dummy"
                return msg, None

        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=InfiniteToolAIClient(), canvas_service=service)
        result = await agent._process_canvas_command("loop")
        # Should stop after 5 iterations
        assert call_count <= 6


# ---------------------------------------------------------------------------
# Tests: _handle_capability_request
# ---------------------------------------------------------------------------

class TestCanvasCapabilityRequest:
    """Test message-based capability request handling."""

    @pytest.mark.asyncio
    async def test_valid_capability_request(self, monkeypatch):
        """Valid capability request processes and sends response."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(
            ai_client=DummyAIClient("Your homework list"),
            canvas_service=service,
        )
        captured = {}

        async def fake_send(to, content, request_id, reply_to=None):
            captured["content"] = content
            captured["to"] = to

        monkeypatch.setattr(agent, "send_capability_response", fake_send)

        msg = _make_canvas_message("get_todo", "What's my homework?")
        await agent._handle_capability_request(msg)

        assert captured["content"]["success"] is True
        assert captured["to"] == "tester"

    @pytest.mark.asyncio
    async def test_unknown_capability_ignored(self, monkeypatch):
        """Unknown capabilities are silently ignored."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        captured = {}

        async def fake_send(to, content, request_id, reply_to=None):
            captured["sent"] = True

        monkeypatch.setattr(agent, "send_capability_response", fake_send)

        msg = _make_canvas_message("weather_forecast")
        await agent._handle_capability_request(msg)

        assert "sent" not in captured

    @pytest.mark.asyncio
    async def test_invalid_prompt_sends_error(self, monkeypatch):
        """Non-string prompt sends error response."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)

        msg = Message(
            from_agent="tester",
            to_agent="CanvasAgent",
            message_type="capability_request",
            content={"capability": "get_todo", "data": {"prompt": 12345}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)

        assert len(errors) == 1
        assert "Invalid prompt" in errors[0]

    @pytest.mark.asyncio
    async def test_missing_prompt_sends_error(self, monkeypatch):
        """Missing prompt sends error response."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)

        msg = Message(
            from_agent="tester",
            to_agent="CanvasAgent",
            message_type="capability_request",
            content={"capability": "get_todo", "data": {}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)

        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_exception_in_processing_sends_error(self, monkeypatch):
        """Exception during processing sends an error message."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)

        async def fail(cmd):
            raise RuntimeError("Unexpected failure")

        monkeypatch.setattr(agent, "_process_canvas_command", fail)

        msg = _make_canvas_message("get_todo", "homework")
        await agent._handle_capability_request(msg)

        assert len(errors) == 1
        assert "Unexpected failure" in errors[0]

    @pytest.mark.asyncio
    async def test_context_enhancement_with_previous_results(self, monkeypatch):
        """Previous DAG results enhance the prompt."""
        service = _make_mock_canvas_service()
        captured_commands = []

        ai = DummyAIClient("Enhanced response")
        agent = CanvasAgent(ai_client=ai, canvas_service=service)

        original_process = agent._process_canvas_command

        async def spy_process(cmd):
            captured_commands.append(cmd)
            return await original_process(cmd)

        monkeypatch.setattr(agent, "_process_canvas_command", spy_process)

        async def fake_send(to, content, request_id, reply_to=None):
            pass

        monkeypatch.setattr(agent, "send_capability_response", fake_send)

        context = {
            "previous_results": [
                {
                    "capability": "weather",
                    "from_agent": "WeatherAgent",
                    "result": {"response": "It is raining"},
                }
            ]
        }
        msg = _make_canvas_message("get_todo", "my homework", context=context)
        await agent._handle_capability_request(msg)

        assert len(captured_commands) == 1
        # The command should contain context from previous results
        assert "raining" in captured_commands[0].lower() or "previous" in captured_commands[0].lower()

    @pytest.mark.asyncio
    async def test_active_task_tracking(self, monkeypatch):
        """Capability requests are tracked in active_tasks."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        async def fake_send(to, content, request_id, reply_to=None):
            pass

        monkeypatch.setattr(agent, "send_capability_response", fake_send)

        msg = _make_canvas_message("get_todo", "homework", request_id="track-123")
        await agent._handle_capability_request(msg)

        assert "track-123" in agent.active_tasks
        assert agent.active_tasks["track-123"]["original_requester"] == "tester"


# ---------------------------------------------------------------------------
# Tests: _handle_capability_response
# ---------------------------------------------------------------------------

class TestCanvasCapabilityResponse:
    """Test capability response handler."""

    @pytest.mark.asyncio
    async def test_handle_known_response(self):
        """Responses for known request IDs are collected."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        # Register a task
        agent.active_tasks["req-1"] = {
            "data": {},
            "original_requester": "tester",
            "responses": [],
        }

        msg = Message(
            from_agent="WeatherAgent",
            to_agent="CanvasAgent",
            message_type="capability_response",
            content={"weather": "sunny"},
            request_id="req-1",
        )
        await agent._handle_capability_response(msg)

        assert len(agent.active_tasks["req-1"]["responses"]) == 1
        assert agent.active_tasks["req-1"]["responses"][0]["from_agent"] == "WeatherAgent"

    @pytest.mark.asyncio
    async def test_handle_unknown_response(self):
        """Responses for unknown request IDs are ignored gracefully."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        msg = Message(
            from_agent="WeatherAgent",
            to_agent="CanvasAgent",
            message_type="capability_response",
            content={"weather": "sunny"},
            request_id="unknown-req",
        )
        # Should not raise
        await agent._handle_capability_response(msg)


# ---------------------------------------------------------------------------
# Tests: _format_homework_response
# ---------------------------------------------------------------------------

class TestFormatHomeworkResponse:
    """Test the homework response formatter."""

    def test_format_homework_summary(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = {
            "success": True,
            "homework_summary": {
                "weekend_homework": [
                    {
                        "course_name": "Math 101",
                        "assignment": {"name": "Problem Set 5"},
                        "due_date": "2026-03-15",
                        "days_until_due": 6,
                    }
                ],
                "overdue_homework": [],
                "upcoming_homework": [],
            },
        }
        formatted = agent._format_homework_response(result)
        assert "Problem Set 5" in formatted
        assert "Math 101" in formatted

    def test_format_homework_failure(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = {"success": False, "error": "API timeout"}
        formatted = agent._format_homework_response(result)
        assert "API timeout" in formatted

    def test_format_comprehensive_homework(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = {
            "success": True,
            "weekend_homework": [
                {
                    "name": "Essay Draft",
                    "course_name": "English 201",
                    "due_date_formatted": "March 15, 2026",
                    "points_possible": 100,
                    "brief_description": "Write a 5-page essay",
                }
            ],
            "due_soon": [],
            "total_assignments": 5,
            "weekend_homework_count": 1,
            "due_soon_count": 0,
        }
        formatted = agent._format_homework_response(result)
        assert "Essay Draft" in formatted
        assert "English 201" in formatted
        assert "100" in formatted

    def test_format_no_homework(self):
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)

        result = {
            "success": True,
            "homework_summary": {
                "weekend_homework": [],
                "overdue_homework": [],
                "upcoming_homework": [],
            },
        }
        formatted = agent._format_homework_response(result)
        assert "no homework" in formatted.lower() or "great news" in formatted.lower()


# ---------------------------------------------------------------------------
# Tests: receive_message routing
# ---------------------------------------------------------------------------

class TestReceiveMessage:
    """Test the receive_message dispatcher."""

    @pytest.mark.asyncio
    async def test_receive_capability_request(self, monkeypatch):
        """capability_request messages are routed to handler."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        handled = {}

        async def fake_handle(msg):
            handled["called"] = True

        monkeypatch.setattr(agent, "_handle_capability_request", fake_handle)
        msg = _make_canvas_message("get_todo", "homework")
        await agent.receive_message(msg)
        assert handled.get("called") is True

    @pytest.mark.asyncio
    async def test_receive_capability_response(self, monkeypatch):
        """capability_response messages are routed to response handler."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        handled = {}

        async def fake_handle(msg):
            handled["called"] = True

        monkeypatch.setattr(agent, "_handle_capability_response", fake_handle)
        msg = Message(
            from_agent="other",
            to_agent="CanvasAgent",
            message_type="capability_response",
            content={},
            request_id="req-1",
        )
        await agent.receive_message(msg)
        assert handled.get("called") is True

    @pytest.mark.asyncio
    async def test_receive_unknown_message_type(self):
        """Unknown message types are logged but do not raise."""
        service = _make_mock_canvas_service()
        agent = CanvasAgent(ai_client=DummyAIClient(), canvas_service=service)
        msg = Message(
            from_agent="other",
            to_agent="CanvasAgent",
            message_type="unknown_type",
            content={},
            request_id="req-1",
        )
        # Should not raise
        await agent.receive_message(msg)
