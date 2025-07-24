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
- `REPO_PATH` – path to the repository used by the SoftwareEngineeringAgent (defaults to `.`)
- `WEATHER_API_KEY` – API key for OpenWeatherMap used by `WeatherAgent`

## Running the server

Start the FastAPI application on port 8000:

```bash
python server.py
```

The `/jarvis` endpoint accepts a JSON body with a `command` field describing the calendar request.
The orchestrator now uses a quick LLM call to translate each step into a precise prompt for the relevant agent. Capability requests therefore include a `prompt` field that agents interpret themselves.
The `/protocols` endpoint returns all registered protocols and their details as JSON.
You can also run a protocol directly via `/protocols/run` by sending either a protocol definition or the name of a registered protocol.

The `/agents` route exposes information about each available agent. `GET /agents`
returns the full list, `GET /agents/{name}` retrieves details for a single agent
and `GET /agents/{name}/capabilities` lists its capabilities. These endpoints are
also accessible under `/jarvis/agents` for compatibility.

### User agent permissions

Each authenticated user may allow or deny individual agents. Use the following endpoints to manage preferences:

- `GET /users/me/agents` – list allowed and disallowed agents for the current user.
- `POST /users/me/agents` – update preferences by sending `{"allowed": [...], "disallowed": [...]}`.

Requests to `/jarvis` will only use agents that the user has allowed. If no preferences exist, all agents are considered allowed by default.

## Demo script

Run the interactive demo from the command line:

```bash
python -m asyncio run main.py
```

The demo now supports multiple commands in a single session. Type your request
and Jarvis will respond until you enter `exit`.
Input and output handling is implemented via pluggable classes in
`jarvis.io`, allowing future integrations with custom interfaces.

## Viewing logs

Agent activity is stored in `jarvis_logs.db`. Launch the interactive viewer with:

```bash
python -m jarvis.log_viewer
```

## Default protocols

Several common protocols are provided under `jarvis/protocols/defaults`.
To load them into `protocols.db` run:

```bash
python -m jarvis.protocols.defaults.loader load
```

You can also run a protocol directly from a JSON file:

```bash
python -m jarvis.protocols.defaults.loader run path/to/protocol.json
```

### Protocol arguments

Protocols can define an `arguments` object which specifies parameter names and default values.
When executed, you may pass a dictionary of values that override these defaults. Parameter values
within each step can reference arguments using Python `str.format` syntax.

Example protocol definition:

```json
{
  "name": "greet",
  "description": "Echo a greeting twice",
  "arguments": { "name": "world" },
  "steps": [
    { "intent": "dummy_cap", "parameters": { "text": "Hello {name}" } },
    { "intent": "dummy_cap", "parameters": { "text": "Bye {name}" } }
  ]
}
```

Manually executing this protocol:

```python
from jarvis.protocols import ProtocolExecutor, Protocol
from jarvis.agents.agent_network import AgentNetwork
from jarvis.logger import JarvisLogger

network = AgentNetwork()
# register agents with `intent_map` entries...
executor = ProtocolExecutor(network, JarvisLogger())
proto = Protocol.from_file("greet.json")
results = await executor.execute(proto, {"name": "Alice"})
```

## Project structure

- `jarvis/` – main package with agent implementations and utilities
- `server.py` – FastAPI entrypoint
- `main.py` – simple demo using `create_collaborative_jarvis`

## Running tests

Install all dependencies and run the suite with `pytest`.

Using `pip`:

```bash
make install
make test
```

Or run the helper script which creates a virtual environment and installs
dependencies automatically:

```bash
./scripts/run_tests.sh
```

With Poetry:

```bash
poetry install
poetry run make test
```

## License

This project is licensed under the [MIT License](LICENSE).
