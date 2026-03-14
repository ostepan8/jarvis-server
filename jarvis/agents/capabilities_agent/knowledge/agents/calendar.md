# CalendarAgent

**Class**: `CollaborativeCalendarAgent`
**Module**: `jarvis/agents/calendar_agent/agent.py`
**Always enabled**

## Capabilities

### create_event
Create a new calendar event from natural language.
- "Schedule a meeting tomorrow at 3pm"
- "Add a dentist appointment on Friday at 10am"
- "Book a team standup every Monday at 9"

### list_events / get_all_events
List events for a time range.
- "What's on my calendar today?"
- "Show my schedule for this week"
- "What do I have tomorrow?"

### get_next_event
Get the next upcoming event.
- "What's my next meeting?"
- "When's my next appointment?"

### schedule_appointment
Alias for create_event with appointment semantics.
- "Book a dentist appointment"
- "Schedule a haircut for Saturday"

### modify_event
Change details of an existing event.
- "Move my 3pm meeting to 4pm"
- "Rename the team standup to daily sync"
- "Change the meeting room to Conference B"

### delete_event
Remove a calendar event.
- "Cancel my 4pm meeting"
- "Delete the dentist appointment"
- "Remove tomorrow's standup"

## Architecture
- `CalendarService` handles REST API communication with retries
- `command_processor.py` uses AI to parse natural language into structured commands
- `function_registry.py` maps capabilities to handler functions
- Tool definitions in `tools/` subdirectory
- Supports CollaborationMixin for multi-agent workflows

## Multi-Agent Collaboration
CalendarAgent can participate in complex multi-agent workflows:
- Search for a restaurant, then schedule dinner
- Check weather, then decide on outdoor event timing
- Review tasks, then schedule work blocks

## Requirements
- Calendar API server running at `CALENDAR_API_URL` (default: http://localhost:8080)
