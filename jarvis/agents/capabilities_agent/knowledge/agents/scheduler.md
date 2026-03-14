# SchedulerAgent

**Class**: `SchedulerAgent`
**Module**: `jarvis/agents/scheduler_agent/__init__.py`
**Feature Flag**: `enable_scheduler`

## Capabilities

### create_schedule
Set up reminders or recurring tasks.
- "Remind me to stand up every hour"
- "Set a reminder for 3pm"
- "Schedule a weekly report every Monday"

### list_schedules
View active schedules and reminders.
- "What reminders do I have?"
- "Show my schedules"
- "List active timers"

### delete_schedule
Remove a schedule or reminder.
- "Cancel my hourly reminder"
- "Delete the weekly report schedule"
- "Stop the standing reminder"

## How It Works
- Background tick loop checks for due items every 15 seconds (configurable: `scheduler_tick_interval`)
- SQLite-backed persistence via `SchedulerService`
- Supports one-time and recurring schedules
- AI client parses natural language into schedule parameters

## Architecture
- `SchedulerService` manages SQLite storage and due-item queries
- Background `asyncio.Task` runs the tick loop
- Natural language parsing for time expressions
