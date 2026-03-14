# Productivity Skills

## Calendar Management
**Agent**: CalendarAgent (CollaborativeCalendarAgent)
**Always enabled** (requires Calendar API)

Full calendar management with natural language event creation and modification.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `create_event` | Create calendar events | "Schedule a meeting tomorrow at 3pm" |
| `list_events` | View upcoming events | "What's on my calendar today?" |
| `delete_event` | Remove events | "Cancel my 4pm meeting" |
| `modify_event` | Change event details | "Move my meeting to Thursday" |
| `get_all_events` | List all events | "Show my schedule" |
| `get_next_event` | Next upcoming event | "What's my next meeting?" |
| `schedule_appointment` | Book appointments | "Book a dentist appointment Friday" |

### Multi-Agent Collaboration
CalendarAgent supports the CollaborationMixin, enabling multi-agent coordination. It can participate in complex workflows where calendar data feeds into other agents (e.g., search for a restaurant, then schedule dinner).

### Requirements
- Calendar API running at `CALENDAR_API_URL` (default: localhost:8080)

---

## Task Management
**Agent**: TodoAgent
**Feature Flag**: `enable_todo`

A Linear-style task board with kanban semantics. SQLite-backed for persistence.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `create_task` | Add a new task | "Add a task to review the PR" |
| `list_tasks` | View tasks by status | "Show my tasks" |
| `update_task` | Modify task details | "Change the priority of task 3" |
| `complete_task` | Mark task done | "Mark the review task as done" |
| `delete_task` | Remove a task | "Delete task 5" |

### Task Properties
- Title, description, priority (low/medium/high/urgent)
- Status: backlog, todo, in_progress, done, cancelled
- Tags for categorization
- Due dates

---

## Scheduling & Reminders
**Agent**: SchedulerAgent
**Feature Flag**: `enable_scheduler`

Cron-like scheduling with natural language. SQLite-backed.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `create_schedule` | Set up reminders/recurring tasks | "Remind me to stand up every hour" |
| `list_schedules` | View active schedules | "What reminders do I have?" |
| `delete_schedule` | Remove a schedule | "Cancel my hourly reminder" |

### How It Works
- Tick interval: 15 seconds (configurable)
- Supports one-time and recurring schedules
- Background task checks for due items automatically

---

## Protocol Execution
**Agent**: ProtocolAgent
**Always enabled**

Execute recorded multi-step workflows as directed acyclic graphs (DAGs).

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `execute_protocol` | Run a saved workflow | "Run my morning routine" |
| `list_protocols` | View available protocols | "What protocols do I have?" |

### How Protocols Work
- Protocols are YAML-defined workflows with steps and dependencies
- Steps execute in parallel where the DAG allows
- Built-in protocols in `jarvis/protocols/defaults/`
- User-recorded protocols in `jarvis/protocols/recorded/`
- Each step maps to a capability request to an agent
