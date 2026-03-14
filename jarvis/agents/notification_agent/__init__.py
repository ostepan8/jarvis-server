"""NotificationAgent — Jarvis's way of tapping the human on the shoulder.

Capabilities:
    send_notification  — deliver a notification via all available backends
    list_notifications — retrieve recent notification history
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ..response import AgentResponse, ErrorInfo
from ...logging import JarvisLogger
from ...services.notification_service import (
    NotificationPriority,
    NotificationService,
)


class NotificationAgent(NetworkAgent):
    """Delivers notifications to the user through pluggable backends."""

    def __init__(
        self,
        notification_service: Optional[NotificationService] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__("NotificationAgent", logger)
        self.notification_service = notification_service or NotificationService(
            logger=logger,
        )
        self.intent_map: Dict[str, Any] = {
            "send_notification": self._handle_send_notification,
            "list_notifications": self._handle_list_notifications,
        }

    @property
    def description(self) -> str:
        return (
            "Delivers notifications to the user via native OS alerts "
            "and other configurable backends."
        )

    @property
    def capabilities(self) -> Set[str]:
        return {"send_notification", "list_notifications"}

    @property
    def supports_dialogue(self) -> bool:
        return False

    # -- Message handlers ---------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        handler = self.intent_map.get(capability)
        if not handler:
            await self.send_error(
                message.from_agent,
                f"Unknown capability: {capability}",
                message.request_id,
            )
            return

        result = await handler(data)
        await self.send_capability_response(
            message.from_agent,
            result.to_dict(),
            message.request_id,
            message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:  # noqa: ARG002
        pass  # NotificationAgent never sends sub-requests

    # -- Capability implementations -----------------------------------------

    async def _handle_send_notification(self, data: Dict[str, Any]) -> AgentResponse:
        """Send a notification to the user."""
        prompt = data.get("prompt", "")
        title = data.get("title") or "Jarvis"
        message = data.get("message") or prompt
        priority_str = data.get("priority", "normal").lower()
        source = data.get("source", "")

        if not message:
            return AgentResponse.error_response(
                response="No message provided. Even a butler needs something to say.",
                error=ErrorInfo(
                    message="Missing required field: message",
                    error_type="ValueError",
                ),
            )

        try:
            priority = NotificationPriority(priority_str)
        except ValueError:
            priority = NotificationPriority.NORMAL

        notification = self.notification_service.send(
            title=title,
            message=message,
            priority=priority,
            source=source,
        )

        if notification.delivered_via:
            backends_str = ", ".join(notification.delivered_via)
            response_text = f"Notification delivered via {backends_str}."
        elif notification.delivery_errors:
            error_summary = "; ".join(
                f"{k}: {v}" for k, v in notification.delivery_errors.items()
            )
            return AgentResponse.error_response(
                response=f"Notification could not be delivered. {error_summary}",
                error=ErrorInfo(
                    message=error_summary,
                    error_type="DeliveryError",
                ),
            )
        else:
            response_text = "Notification queued but no backends available."

        return AgentResponse.success_response(
            response=response_text,
            data=notification.to_dict(),
            actions=[{"type": "notification_sent", "details": notification.to_dict()}],
            metadata={"agent": "notification", "capability": "send_notification"},
        )

    async def _handle_list_notifications(self, data: Dict[str, Any]) -> AgentResponse:
        """Retrieve recent notification history."""
        limit = int(data.get("limit", 20))
        priority_filter = data.get("priority")
        source_filter = data.get("source")

        priority = None
        if priority_filter:
            try:
                priority = NotificationPriority(priority_filter.lower())
            except ValueError:
                pass

        notifications = self.notification_service.get_history(
            limit=limit,
            priority=priority,
            source=source_filter,
        )

        if not notifications:
            return AgentResponse.success_response(
                response="No recent notifications. Blissful silence.",
                data={"notifications": [], "count": 0},
                metadata={"agent": "notification", "capability": "list_notifications"},
            )

        lines = [f"{len(notifications)} recent notification(s):"]
        for n in notifications:
            ts = n.timestamp[:19].replace("T", " ")
            prio = f" [{n.priority.value.upper()}]" if n.priority != NotificationPriority.NORMAL else ""
            src = f" (from {n.source})" if n.source else ""
            lines.append(f"  {ts}{prio}{src} — {n.title}: {n.message}")

        return AgentResponse.success_response(
            response="\n".join(lines),
            data={
                "notifications": [n.to_dict() for n in notifications],
                "count": len(notifications),
            },
            metadata={"agent": "notification", "capability": "list_notifications"},
        )

    # -- Health alert handling ----------------------------------------------

    async def _handle_health_alert(self, message: Message) -> None:
        """Forward health alerts as user notifications when severity warrants it."""
        content = message.content
        new_status = content.get("new_status", "")
        component = content.get("component", "unknown")
        details = content.get("details", "")

        if new_status == "critical":
            self.notification_service.send(
                title=f"Alert: {component}",
                message=details or f"{component} has reached critical status.",
                priority=NotificationPriority.CRITICAL,
                source=content.get("source", message.from_agent),
            )
