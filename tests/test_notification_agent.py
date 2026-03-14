"""Tests for NotificationAgent and NotificationService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.agents.notification_agent import NotificationAgent
from jarvis.services.notification_service import (
    MacOSNotificationBackend,
    Notification,
    NotificationBackend,
    NotificationPriority,
    NotificationService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(service=None, logger=None) -> NotificationAgent:
    logger = logger or MagicMock()
    svc = service or NotificationService(logger=MagicMock(), history_limit=50)
    agent = NotificationAgent(notification_service=svc, logger=logger)
    return agent


def _make_message(capability: str, data: dict | None = None):
    msg = MagicMock()
    msg.id = "msg-1"
    msg.from_agent = "TestRequester"
    msg.request_id = "req-1"
    msg.content = {
        "capability": capability,
        "data": data or {},
    }
    return msg


class DummyBackend(NotificationBackend):
    """Test backend that records sent notifications."""

    def __init__(self, available: bool = True, succeed: bool = True) -> None:
        self._available = available
        self._succeed = succeed
        self.sent: list[Notification] = []

    @property
    def name(self) -> str:
        return "dummy"

    def is_available(self) -> bool:
        return self._available

    def send(self, notification: Notification) -> bool:
        if self._succeed:
            self.sent.append(notification)
        return self._succeed


class FailingBackend(NotificationBackend):
    """Backend that raises on send."""

    @property
    def name(self) -> str:
        return "failing"

    def is_available(self) -> bool:
        return True

    def send(self, notification: Notification) -> bool:
        raise RuntimeError("Backend exploded")


# ---------------------------------------------------------------------------
# NotificationService tests
# ---------------------------------------------------------------------------


class TestNotificationService:

    def _make_service(self, **kwargs) -> NotificationService:
        """Service with no auto-registered backends."""
        with patch.object(MacOSNotificationBackend, "is_available", return_value=False):
            return NotificationService(logger=MagicMock(), **kwargs)

    def test_send_with_no_backends(self):
        svc = self._make_service()
        result = svc.send("Test", "Hello")
        assert not result.delivered_via
        assert "_global" in result.delivery_errors

    def test_send_with_dummy_backend(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        result = svc.send("Title", "Body", source="test_agent")
        assert result.delivered_via == ["dummy"]
        assert not result.delivery_errors
        assert len(backend.sent) == 1
        assert backend.sent[0].title == "Title"

    def test_send_with_unavailable_backend(self):
        svc = self._make_service()
        backend = DummyBackend(available=False)
        svc.register_backend(backend)

        result = svc.send("Title", "Body")
        assert not result.delivered_via
        assert "dummy" in result.delivery_errors

    def test_send_with_failing_backend(self):
        svc = self._make_service()
        svc.register_backend(FailingBackend())

        result = svc.send("Title", "Boom")
        assert not result.delivered_via
        assert "failing" in result.delivery_errors
        assert "exploded" in result.delivery_errors["failing"]

    def test_send_with_mixed_backends(self):
        svc = self._make_service()
        good = DummyBackend()
        bad = DummyBackend(succeed=False)
        svc.register_backend(good)
        svc.register_backend(bad)

        result = svc.send("Title", "Body")
        assert "dummy" in result.delivered_via  # good backend
        assert result.delivery_errors  # bad backend logged

    def test_priority_propagation(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        svc.send("Alert", "Fire", priority=NotificationPriority.CRITICAL)
        assert backend.sent[0].priority == NotificationPriority.CRITICAL

    def test_history_basic(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        svc.send("A", "First")
        svc.send("B", "Second")
        svc.send("C", "Third")

        history = svc.get_history()
        assert len(history) == 3
        # Most recent first
        assert history[0].title == "C"
        assert history[2].title == "A"

    def test_history_limit(self):
        svc = self._make_service(history_limit=3)
        backend = DummyBackend()
        svc.register_backend(backend)

        for i in range(5):
            svc.send(f"N{i}", f"Message {i}")

        history = svc.get_history(limit=10)
        assert len(history) == 3  # Only 3 kept in deque

    def test_history_filter_by_priority(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        svc.send("Low", "msg", priority=NotificationPriority.LOW)
        svc.send("High", "msg", priority=NotificationPriority.HIGH)
        svc.send("Normal", "msg", priority=NotificationPriority.NORMAL)

        high_only = svc.get_history(priority=NotificationPriority.HIGH)
        assert len(high_only) == 1
        assert high_only[0].title == "High"

    def test_history_filter_by_source(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        svc.send("A", "msg", source="device_monitor")
        svc.send("B", "msg", source="health")
        svc.send("C", "msg", source="device_monitor")

        dm_only = svc.get_history(source="device_monitor")
        assert len(dm_only) == 2

    def test_clear_history(self):
        svc = self._make_service()
        backend = DummyBackend()
        svc.register_backend(backend)

        svc.send("A", "msg")
        svc.send("B", "msg")

        cleared = svc.clear_history()
        assert cleared == 2
        assert svc.get_history() == []

    def test_available_backends(self):
        svc = self._make_service()
        svc.register_backend(DummyBackend(available=True))
        svc.register_backend(DummyBackend(available=False))

        assert svc.available_backends == ["dummy"]

    def test_notification_to_dict(self):
        n = Notification(
            title="Test",
            message="Hello",
            priority=NotificationPriority.HIGH,
            source="agent_x",
        )
        d = n.to_dict()
        assert d["title"] == "Test"
        assert d["message"] == "Hello"
        assert d["priority"] == "high"
        assert d["source"] == "agent_x"
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# MacOS backend tests
# ---------------------------------------------------------------------------


class TestMacOSBackend:

    @patch("jarvis.services.notification_service.platform")
    def test_available_on_darwin(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        backend = MacOSNotificationBackend()
        assert backend.is_available() is True

    @patch("jarvis.services.notification_service.platform")
    def test_unavailable_on_linux(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        backend = MacOSNotificationBackend()
        assert backend.is_available() is False

    @patch("jarvis.services.notification_service.platform")
    @patch("jarvis.services.notification_service.subprocess")
    def test_send_calls_osascript(self, mock_subprocess, mock_platform):
        mock_platform.system.return_value = "Darwin"
        backend = MacOSNotificationBackend()
        notification = Notification(title="Test", message="Hello")

        result = backend.send(notification)
        assert result is True
        mock_subprocess.Popen.assert_called_once()
        args = mock_subprocess.Popen.call_args[0][0]
        assert args[0] == "osascript"
        assert "Hello" in args[2]

    @patch("jarvis.services.notification_service.platform")
    @patch("jarvis.services.notification_service.subprocess")
    def test_critical_priority_includes_sound(self, mock_subprocess, mock_platform):
        mock_platform.system.return_value = "Darwin"
        backend = MacOSNotificationBackend()
        notification = Notification(
            title="Alert", message="Fire", priority=NotificationPriority.CRITICAL
        )

        backend.send(notification)
        args = mock_subprocess.Popen.call_args[0][0]
        assert "sound name" in args[2]

    @patch("jarvis.services.notification_service.platform")
    @patch("jarvis.services.notification_service.subprocess")
    def test_normal_priority_no_sound(self, mock_subprocess, mock_platform):
        mock_platform.system.return_value = "Darwin"
        backend = MacOSNotificationBackend()
        notification = Notification(title="Info", message="Quiet")

        backend.send(notification)
        args = mock_subprocess.Popen.call_args[0][0]
        assert "sound name" not in args[2]

    @patch("jarvis.services.notification_service.platform")
    def test_send_on_non_darwin_returns_false(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        backend = MacOSNotificationBackend()
        notification = Notification(title="Test", message="Nope")
        assert backend.send(notification) is False

    def test_name(self):
        backend = MacOSNotificationBackend()
        assert backend.name == "macos"


# ---------------------------------------------------------------------------
# NotificationAgent tests
# ---------------------------------------------------------------------------


class TestNotificationAgent:

    def _make_service_with_backend(self) -> tuple[NotificationService, DummyBackend]:
        with patch.object(MacOSNotificationBackend, "is_available", return_value=False):
            svc = NotificationService(logger=MagicMock())
        backend = DummyBackend()
        svc.register_backend(backend)
        return svc, backend

    @pytest.mark.asyncio
    async def test_send_notification_basic(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        result = await agent._handle_send_notification({
            "title": "Heads Up",
            "message": "Task complete",
        })

        assert result.success is True
        assert "dummy" in result.response
        assert len(backend.sent) == 1
        assert backend.sent[0].title == "Heads Up"

    @pytest.mark.asyncio
    async def test_send_notification_from_prompt(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        result = await agent._handle_send_notification({
            "prompt": "Your build is done",
        })

        assert result.success is True
        assert len(backend.sent) == 1
        assert backend.sent[0].message == "Your build is done"

    @pytest.mark.asyncio
    async def test_send_notification_empty_message(self):
        agent = _make_agent()

        result = await agent._handle_send_notification({})

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_notification_with_priority(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        result = await agent._handle_send_notification({
            "title": "Alert",
            "message": "Disk critical",
            "priority": "critical",
            "source": "device_monitor",
        })

        assert result.success is True
        assert backend.sent[0].priority == NotificationPriority.CRITICAL
        assert backend.sent[0].source == "device_monitor"

    @pytest.mark.asyncio
    async def test_send_notification_invalid_priority_defaults_to_normal(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        result = await agent._handle_send_notification({
            "message": "Test",
            "priority": "super_urgent",
        })

        assert result.success is True
        assert backend.sent[0].priority == NotificationPriority.NORMAL

    @pytest.mark.asyncio
    async def test_send_notification_delivery_failure(self):
        with patch.object(MacOSNotificationBackend, "is_available", return_value=False):
            svc = NotificationService(logger=MagicMock())
        svc.register_backend(DummyBackend(succeed=False))
        agent = _make_agent(service=svc)

        result = await agent._handle_send_notification({
            "message": "Will fail",
        })

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_list_notifications_empty(self):
        agent = _make_agent()

        result = await agent._handle_list_notifications({})

        assert result.success is True
        assert result.data["count"] == 0
        assert "silence" in result.response.lower()

    @pytest.mark.asyncio
    async def test_list_notifications_with_history(self):
        svc, _ = self._make_service_with_backend()
        svc.send("First", "msg1", source="health")
        svc.send("Second", "msg2", source="device_monitor")
        agent = _make_agent(service=svc)

        result = await agent._handle_list_notifications({})

        assert result.success is True
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_list_notifications_with_filters(self):
        svc, _ = self._make_service_with_backend()
        svc.send("A", "msg", priority=NotificationPriority.LOW, source="x")
        svc.send("B", "msg", priority=NotificationPriority.HIGH, source="y")
        agent = _make_agent(service=svc)

        result = await agent._handle_list_notifications({"priority": "high"})
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_capabilities(self):
        agent = _make_agent()
        assert "send_notification" in agent.capabilities
        assert "list_notifications" in agent.capabilities

    @pytest.mark.asyncio
    async def test_description(self):
        agent = _make_agent()
        assert "notification" in agent.description.lower()

    @pytest.mark.asyncio
    async def test_supports_dialogue(self):
        agent = _make_agent()
        assert agent.supports_dialogue is False

    @pytest.mark.asyncio
    async def test_handle_health_alert_critical(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        msg = MagicMock()
        msg.from_agent = "DeviceMonitorAgent"
        msg.content = {
            "alert_type": "status_change",
            "source": "device_monitor",
            "component": "cpu",
            "old_status": "warning",
            "new_status": "critical",
            "details": "CPU has reached critical levels",
        }

        await agent._handle_health_alert(msg)

        assert len(backend.sent) == 1
        assert backend.sent[0].priority == NotificationPriority.CRITICAL
        assert "cpu" in backend.sent[0].title.lower()

    @pytest.mark.asyncio
    async def test_handle_health_alert_non_critical_ignored(self):
        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)

        msg = MagicMock()
        msg.from_agent = "DeviceMonitorAgent"
        msg.content = {
            "alert_type": "status_change",
            "source": "device_monitor",
            "component": "cpu",
            "old_status": "ok",
            "new_status": "warning",
            "details": "CPU is elevated",
        }

        await agent._handle_health_alert(msg)

        # Warning alerts don't trigger notifications
        assert len(backend.sent) == 0

    @pytest.mark.asyncio
    async def test_handle_capability_request_dispatches(self):
        from unittest.mock import AsyncMock

        svc, backend = self._make_service_with_backend()
        agent = _make_agent(service=svc)
        agent.network = MagicMock()
        agent.send_capability_response = AsyncMock()

        msg = _make_message("send_notification", {"message": "Test dispatch"})
        await agent._handle_capability_request(msg)

        assert len(backend.sent) == 1

    @pytest.mark.asyncio
    async def test_handle_capability_request_unknown(self):
        from unittest.mock import AsyncMock

        agent = _make_agent()
        agent.network = MagicMock()
        agent.send_error = AsyncMock()

        msg = _make_message("nonexistent_capability")
        await agent._handle_capability_request(msg)

        agent.send_error.assert_called_once()
