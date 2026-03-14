# TodoAgent

**Class**: `TodoAgent`
**Module**: `jarvis/agents/todo_agent/__init__.py`
**Feature Flag**: `enable_todo`

## Capabilities

### create_task
Create a new task on the board.
- "Add a task to review the PR"
- "Create a high priority task: fix the login bug"
- "New task: buy groceries, due Friday"

### list_tasks
View tasks, optionally filtered by status.
- "Show my tasks"
- "What's in progress?"
- "List completed tasks"
- "Any urgent tasks?"

### update_task
Modify an existing task's details.
- "Change task 3 to high priority"
- "Add a due date to the review task"
- "Move task 5 to in progress"

### complete_task
Mark a task as done.
- "Mark the review task as done"
- "Complete task 3"
- "I finished the grocery shopping"

### delete_task
Remove a task from the board.
- "Delete task 5"
- "Remove the cancelled meeting task"

## Task Model
```
- id: Auto-generated integer
- title: Task name
- description: Detailed description
- priority: low | medium | high | urgent
- status: backlog | todo | in_progress | done | cancelled
- tags: List of categorization tags
- due_date: Optional deadline
- created_at: Timestamp
- updated_at: Timestamp
```

## Architecture
- `TodoService` provides SQLite-backed persistence
- AI client parses natural language into structured operations
- Returns JSON operation descriptors that map to service methods
