---
name: jarvis-self-improvement
description: >
  Interact with the Jarvis self-improvement system via its local HTTP API.
  Use when you need to: discover issues in the Jarvis codebase, run tests
  and get structured results, submit improvement tasks, check improvement
  cycle status, or get night reports. Enables bidirectional conversation
  between Claude Code and the running Jarvis server.
---

# Jarvis Self-Improvement Skill

Communicate with a running Jarvis server to discover issues, run tests, submit tasks, and monitor improvement cycles.

## Available Commands

| Command | Script | Description |
|---------|--------|-------------|
| Discover issues | `scripts/discover.py` | Run analysis to find bugs, test failures, TODOs, and code quality issues |
| Run tests | `scripts/run_tests.py` | Execute pytest and poll for structured results |
| Check status | `scripts/get_status.py` | See if an improvement cycle is running |
| Submit task | `scripts/submit_task.py` | Queue a new improvement task |
| Get report | `scripts/get_report.py` | Fetch the latest or all night reports |
| Get context | `scripts/get_context.py` | Read a project file via the API |

## Configuration

Set `JARVIS_API_URL` environment variable to override the default base URL.
Default: `http://localhost:52718/self-improvement`

## Usage

All scripts use stdlib `urllib` only — no pip dependencies required.

```bash
# Discover issues
python scripts/discover.py
python scripts/discover.py --types logs,tests --lookback-hours 48

# Run tests
python scripts/run_tests.py tests/test_builder.py
python scripts/run_tests.py  # full suite

# Check cycle status
python scripts/get_status.py

# Submit a task
python scripts/submit_task.py --title "Fix flaky test" --description "test_calendar sometimes times out" --priority high

# Get latest report
python scripts/get_report.py
python scripts/get_report.py --all --limit 5

# Read a project file
python scripts/get_context.py jarvis/services/self_improvement_service.py
```

## API Reference

See `references/api_reference.md` for full endpoint documentation.
