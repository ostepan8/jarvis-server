"""Tests for Message data structure."""

import uuid
from datetime import datetime

import pytest

from jarvis.agents.message import Message


class TestMessageCreation:
    """Test Message dataclass creation."""

    def test_default_fields(self):
        """Test message with default fields."""
        msg = Message()
        assert msg.from_agent == ""
        assert msg.to_agent is None
        assert msg.message_type == ""
        assert msg.content is None
        assert msg.request_id == ""
        assert msg.reply_to is None
        assert msg.id is not None
        assert msg.timestamp is not None

    def test_id_is_uuid(self):
        """Test message id is a valid UUID string."""
        msg = Message()
        # Should not raise
        parsed = uuid.UUID(msg.id)
        assert str(parsed) == msg.id

    def test_unique_ids(self):
        """Test each message gets a unique id."""
        msg1 = Message()
        msg2 = Message()
        assert msg1.id != msg2.id

    def test_timestamp_is_datetime(self):
        """Test timestamp is a datetime object."""
        msg = Message()
        assert isinstance(msg.timestamp, datetime)

    def test_timestamps_are_recent(self):
        """Test timestamps are approximately 'now'."""
        before = datetime.now()
        msg = Message()
        after = datetime.now()
        assert before <= msg.timestamp <= after

    def test_custom_fields(self):
        """Test message with all custom fields."""
        msg = Message(
            id="custom-id",
            from_agent="agent_a",
            to_agent="agent_b",
            message_type="capability_request",
            content={"key": "value"},
            request_id="req-123",
            reply_to="msg-456",
        )
        assert msg.id == "custom-id"
        assert msg.from_agent == "agent_a"
        assert msg.to_agent == "agent_b"
        assert msg.message_type == "capability_request"
        assert msg.content == {"key": "value"}
        assert msg.request_id == "req-123"
        assert msg.reply_to == "msg-456"


class TestMessageContent:
    """Test various content types in Message."""

    def test_string_content(self):
        """Test message with string content."""
        msg = Message(content="Hello, World!")
        assert msg.content == "Hello, World!"

    def test_dict_content(self):
        """Test message with dict content."""
        msg = Message(content={"capability": "search", "data": {"query": "test"}})
        assert msg.content["capability"] == "search"
        assert msg.content["data"]["query"] == "test"

    def test_list_content(self):
        """Test message with list content."""
        msg = Message(content=[1, 2, 3])
        assert msg.content == [1, 2, 3]

    def test_none_content(self):
        """Test message with None content."""
        msg = Message(content=None)
        assert msg.content is None

    def test_nested_dict_content(self):
        """Test message with deeply nested content."""
        nested = {
            "level1": {
                "level2": {
                    "level3": "deep_value"
                }
            }
        }
        msg = Message(content=nested)
        assert msg.content["level1"]["level2"]["level3"] == "deep_value"

    def test_integer_content(self):
        """Test message with integer content."""
        msg = Message(content=42)
        assert msg.content == 42

    def test_boolean_content(self):
        """Test message with boolean content."""
        msg = Message(content=True)
        assert msg.content is True


class TestMessageTypes:
    """Test common message type patterns."""

    def test_capability_request_message(self):
        """Test creating a capability_request message."""
        msg = Message(
            from_agent="nlu",
            to_agent=None,
            message_type="capability_request",
            content={
                "capability": "search",
                "data": {"query": "Chicago weather"},
            },
            request_id="req-1",
        )
        assert msg.message_type == "capability_request"
        assert msg.to_agent is None  # broadcast

    def test_capability_response_message(self):
        """Test creating a capability_response message."""
        msg = Message(
            from_agent="search_agent",
            to_agent="nlu",
            message_type="capability_response",
            content={
                "success": True,
                "response": "75F in Chicago",
            },
            request_id="req-1",
            reply_to="msg-original",
        )
        assert msg.message_type == "capability_response"
        assert msg.reply_to == "msg-original"

    def test_error_message(self):
        """Test creating an error message."""
        msg = Message(
            from_agent="search_agent",
            to_agent="nlu",
            message_type="error",
            content={"error": "API key expired"},
            request_id="req-1",
        )
        assert msg.message_type == "error"
        assert msg.content["error"] == "API key expired"


class TestMessageBroadcast:
    """Test broadcast message pattern (to_agent is None)."""

    def test_broadcast_message(self):
        """Test creating a broadcast message."""
        msg = Message(
            from_agent="nlu",
            to_agent=None,
            message_type="capability_request",
            content={"capability": "search"},
            request_id="req-1",
        )
        assert msg.to_agent is None

    def test_directed_message(self):
        """Test creating a directed message."""
        msg = Message(
            from_agent="agent_a",
            to_agent="agent_b",
            message_type="custom",
            content={},
            request_id="req-1",
        )
        assert msg.to_agent == "agent_b"


class TestMessageEquality:
    """Test message comparison behavior."""

    def test_different_messages_not_equal(self):
        """Test two messages with different IDs are not equal by default."""
        msg1 = Message(from_agent="a", content="test")
        msg2 = Message(from_agent="a", content="test")
        # dataclasses compare by value, but IDs differ
        assert msg1 != msg2

    def test_same_id_messages_equal(self):
        """Test two messages with same fields are equal."""
        ts = datetime.now()
        msg1 = Message(id="same-id", from_agent="a", timestamp=ts)
        msg2 = Message(id="same-id", from_agent="a", timestamp=ts)
        assert msg1 == msg2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
