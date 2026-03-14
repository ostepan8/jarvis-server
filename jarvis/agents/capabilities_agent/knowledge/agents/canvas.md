# CanvasAgent

**Class**: `CanvasAgent`
**Module**: `jarvis/agents/canvas/__init__.py`
**Feature Flag**: `enable_canvas`

## Capabilities

### get_courses
List enrolled courses from Canvas LMS.
- "What courses am I taking?"
- "Show my courses"
- "List my classes"

### get_comprehensive_homework
View assignments, due dates, and submission status.
- "What homework do I have?"
- "Show my assignments"
- "What's due this week?"
- "Any upcoming deadlines?"

## Architecture
- `CanvasService` handles Canvas LMS API communication
- AI client used for response formatting
- Returns structured course and assignment data

## Requirements
- Canvas LMS API credentials configured
- `CanvasService` initialized with API URL and token
