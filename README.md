# Jarvis Server

FastAPI server exposing collaborative calendar agents. The project provides both an HTTP API and a small demo script that interact with a network of AI agents to manage calendar events.

## Requirements
- Python 3.11+
- Dependencies listed in `requirements.txt`

Install the dependencies with:
```bash
pip install -r requirements.txt
```
If you prefer Poetry, run `poetry install` instead.

## Environment variables
Create a `.env` file or export the following variables before running the server:
- `OPENAI_API_KEY` – API key for OpenAI based clients
- `ANTHROPIC_API_KEY` – key for Anthropic clients (optional)
- `CALENDAR_API_URL` – base URL of the calendar API (defaults to `http://localhost:8080`)

## Running the server
Start the FastAPI application on port 8000:
```bash
python server.py
```
The `/jarvis` endpoint accepts a JSON body with a `command` field describing the calendar request.

## Demo script
To try the collaborative Jarvis system from the command line:
```bash
python -m asyncio run main.py
```
The script prompts for a natural language command and prints the agent response.

## Viewing logs
Agent activity is stored in `jarvis_logs.db`. Launch the interactive viewer with:
```bash
python -m jarvis.log_viewer
```

## Project structure
- `jarvis/` – main package with agent implementations and utilities
- `server.py` – FastAPI entrypoint
- `main.py` – simple demo using `create_collaborative_jarvis`


