# Jarvis Server AGENTS Guide

This file gives high level guidance for working with the code base. It is intended for agents (including Codex) that need context when working on tasks in this repository.

## Dependencies
Additional Python packages used by the project:
- `fastapi`
- `uvicorn`
- `pydantic`
- `httpx`
- `aiohttp`
- `tzlocal`
- `colorama`
- `python-dotenv`
- `openai`
- `anthropic`
- `pytest`
- `pytest-asyncio`
- `pymongo`
- `pvporcupine`
- `vosk`
- `chromadb`
- `passlib[bcrypt]`
- `PyJWT`
- `cryptography`

## Overview
- **Language**: Python 3.11+
- **App**: FastAPI server exposing AI agents for calendar management.
- **Key modules**:
  - `jarvis/agents/` – agent implementations and network infrastructure.
  - `jarvis/main_network.py` – creates the `JarvisSystem` using the agent network.
  - `jarvis/ai_clients/` – wrappers for OpenAI and Anthropic APIs.
  - `jarvis/services/` – service layer utilities like the calendar API client.
  - `jarvis/logger.py` – writes logs to stdout and SQLite.
  - `server.py` – FastAPI entrypoint exposing the `/jarvis` endpoint.

## Running the server
```bash
python server.py
```
The API will listen on port 8000.

## Demo script
`main.py` contains an async demo that uses the collaborative Jarvis system. Run with:
```bash
python -m asyncio run main.py
```

## Environment variables
- `OPENAI_API_KEY` – key for OpenAI based clients.
- `ANTHROPIC_API_KEY` – key for Anthropic based clients.

## JarvisSystem options
- `response_timeout` – number of seconds the orchestrator waits for
  capability responses when processing a user request. Defaults to 10 seconds.
- `intent_timeout` – seconds to wait for NLU classification before giving up. Defaults to 5 seconds.

## Logs
Logs are stored in `jarvis_logs.db`. Use the log viewer:
```bash
python -m jarvis.log_viewer
```

## Orchestrator prompts
The orchestrator now calls `weak_chat` to craft a short prompt for each capability step. Agents expect this
`prompt` string in incoming `capability_request` messages and no longer receive a `command` field.

## Tests
Automated tests live under the `tests/` directory. Install the dependencies from
`requirements.txt` (or run `poetry install`) and execute:
```bash
pytest
```
The suite uses `pytest` and `pytest-asyncio`.

## Pull Request instructions for Agents
1. Keep the repository in a clean state (`git status` should show no changes) before finishing.
2. If you add code requiring new dependencies, list them at the top of this file.
3. Provide concise commit messages and include relevant citations in PR summaries.
