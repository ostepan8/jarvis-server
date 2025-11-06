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
- `sounddevice`
- `soundfile`

`sounddevice` and `soundfile` depend on the system libraries PortAudio and libsndfile respectively. Ensure these libraries are installed in runtime environments.

## Overview

- **Language**: Python 3.11+
- **App**: FastAPI server exposing AI agents for calendar management.
- **Key modules**:
  - `jarvis/agents/` – agent implementations and network infrastructure.
  - `jarvis/core/system.py` – creates the `JarvisSystem` using the agent network.
  - `jarvis/ai_clients/` – wrappers for OpenAI and Anthropic APIs.
  - `jarvis/services/` – service layer utilities like the calendar API client.
  - `jarvis/logging/jarvis_logger.py` – writes logs to stdout and SQLite.
  - `server/main.py` – FastAPI entrypoint exposing the `/jarvis` endpoint. Run with `python -m server.main`.

## Running the server

```bash
python -m server.main
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
- `JWT_SECRET` – secret key for signing authentication tokens (required).
- `AUTH_DB_PATH` – path to the SQLite auth database (defaults to `auth.db`).
- `ROKU_IP_ADDRESS` – IP address of the Roku device for TV control (e.g., `192.168.1.150`).
- `ROKU_USERNAME` – optional username for Roku authentication.
- `ROKU_PASSWORD` – optional password for Roku authentication.
- `JARVIS_VERBOSE` – enable verbose logging mode. When set to `true`, `1`, or `yes`, all log levels (DEBUG, INFO, WARNING, ERROR) are written to console and database. When `false` (default), only WARNING and ERROR level logs are written to reduce console spam and database bloat.
- `JARVIS_LOG_LEVEL` – standard logging level for console output (defaults to `INFO`). Only applies when `JARVIS_VERBOSE=true`.

## JarvisSystem options

- `response_timeout` – number of seconds the orchestrator waits for
  capability responses when processing a user request. Defaults to 10 seconds.
- `intent_timeout` – seconds to wait for NLU classification before giving up. Defaults to 5 seconds.

## Logs

Logs are stored in `jarvis_logs.db`. Use the log viewer:

```bash
python -m jarvis.logging.log_viewer
```

By default, logging operates in **non-verbose mode** to reduce console output and database size. In this mode, only WARNING and ERROR level messages are written to both console and database. Set `JARVIS_VERBOSE=true` to enable full logging of all levels (DEBUG, INFO, WARNING, ERROR).

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
