# NotificationAgent

**Class**: `NotificationAgent`
**Module**: `jarvis/agents/notification_agent/__init__.py`
**Feature Flag**: `enable_notifications`

## Capabilities

### send_notification
Deliver a notification to the user through all available backends.
- "Notify me"
- "Send me an alert"
- "Ping me when it's done"
- "Give me a heads up"

### list_notifications
Retrieve recent notification history (useful after stepping away).
- "What notifications did I get"
- "What did I miss"
- "Show recent alerts"
- "Notification history"

## Notification Backends
- **macOS** (default): Native OS notifications via osascript. Sound plays for high/critical priority.
- Additional backends (Slack, SMS, email) can be added by implementing `NotificationBackend`.

## Architecture
- `NotificationService` manages backend registration and delivery
- Pluggable `NotificationBackend` interface for extensibility
- Rolling history kept in memory for "what did I miss" queries
- Automatically forwards critical health alerts from other agents as user notifications

## Priority Levels
- `low` — informational, no sound
- `normal` — standard notification
- `high` — plays alert sound
- `critical` — plays alert sound, used for system alerts
