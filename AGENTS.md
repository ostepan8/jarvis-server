# Jarvis Server AGENTS Guide

This file gives high level guidance for working with the code base. It is intended for agents (including Codex) that need context when working on tasks in this repository.

## Overview
- **Language**: Python 3.11+
- **App**: FastAPI server exposing AI agents for calendar management.
- **Key modules**:
  - `jarvis/agent.py` – calendar agent implementing tool-based operations.
  - `jarvis/main_agent.py` – main agent that delegates to sub agents.
  - `jarvis/ai_clients/` – wrappers for OpenAI and Anthropic APIs.
  - `jarvis/calendar_service.py` – HTTP client for an external calendar API.
  - `jarvis/logger.py` – writes logs to stdout and SQLite.
  - `server.py` – FastAPI entrypoint exposing `/calendar-agent` and `/jarvis` endpoints.

## Running the server
```bash
python server.py
```
The API will listen on port 8000.

## Demo script
`main.py` contains an async demo that uses the calendar agent directly. Run with:
```bash
python -m asyncio run main.py
```

## Environment variables
- `OPENAI_API_KEY` – key for OpenAI based clients.
- `ANTHROPIC_API_KEY` – key for Anthropic based clients.

## Logs
Logs are stored in `jarvis_logs.db`. Use the log viewer:
```bash
python -m jarvis.log_viewer
```

## Tests
There are currently no automated tests. When adding new features, prefer small functions and consider adding tests under a new `tests/` folder using `pytest`.

## Pull Request instructions for Agents
1. Keep the repository in a clean state (`git status` should show no changes) before finishing.
2. If you add code requiring new dependencies, list them at the top of this file.
3. Provide concise commit messages and include relevant citations in PR summaries.
