# Jarvis Self-Improvement API Reference

Base URL: `http://localhost:52718/self-improvement`

## Endpoints

### GET /status
Returns the current state of the self-improvement system.

**Response:**
```json
{
  "running": false,
  "discoveries_count": 3,
  "submitted_tasks_count": 1,
  "active_test_runs": 0
}
```

### POST /discover
Run discovery analysis to find issues.

**Request Body:**
```json
{
  "types": ["logs", "tests", "todos", "code_quality"],
  "lookback_hours": 24
}
```

**Response:**
```json
{
  "discoveries": [
    {
      "discovery_type": "test_failure",
      "title": "Test failure: tests/test_foo.py::test_bar",
      "description": "Test failed: assertion error",
      "priority": "urgent",
      "relevant_files": ["tests/test_foo.py"],
      "source_detail": "assertion error"
    }
  ],
  "count": 1
}
```

### GET /discoveries
Get cached discoveries from the last discovery run.

**Query Parameters:**
- `type` (optional): Filter by discovery type (e.g., `test_failure`, `log_error`)

### POST /cycle
Start a full improvement cycle (runs in background).

**Request Body:**
```json
{
  "max_tasks": 3,
  "dry_run": false
}
```

**Response:**
```json
{
  "status": "started",
  "message": "Improvement cycle started"
}
```

Returns 409 if a cycle is already running.

### POST /tasks
Submit an external improvement task.

**Request Body:**
```json
{
  "title": "Fix flaky test",
  "description": "test_calendar sometimes times out on CI",
  "priority": "high",
  "relevant_files": ["tests/test_calendar_agent.py"]
}
```

### GET /tasks
List all submitted tasks.

### POST /tests/run
Run pytest asynchronously. Returns a run_id for polling.

**Request Body:**
```json
{
  "test_files": ["tests/test_builder.py"],
  "working_directory": null,
  "timeout": 120
}
```

**Response:**
```json
{
  "run_id": "uuid-here",
  "status": "pending"
}
```

### GET /tests/{run_id}
Poll for test run results.

**Response (completed):**
```json
{
  "run_id": "uuid-here",
  "status": "completed",
  "success": true,
  "stdout": "...",
  "stderr": "",
  "exit_code": 0,
  "duration_seconds": 12.5
}
```

### GET /reports/latest
Get the most recent night report.

### GET /reports
List all available reports.

**Query Parameters:**
- `limit` (optional, default 10): Maximum reports to return

### GET /context/{file_path}
Read a project file. Path must be within the project root.

**Response:**
```json
{
  "file_path": "jarvis/services/self_improvement_service.py",
  "content": "...",
  "size": 12345
}
```

Returns 403 for path traversal attempts, 404 for missing files.
