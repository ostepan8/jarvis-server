# Jarvis Server

FastAPI server exposing collaborative AI agents with a sophisticated multi-agent architecture. The project provides both an HTTP API and an interactive demo that leverage a network of specialized AI agents to manage calendar events, weather information, smart home devices, and more.

## Recent Architecture Improvements

This project has recently undergone a major refactoring to improve code quality, maintainability, and resilience:

- **Standardized Agent Responses**: Unified response format across all agents for consistent output rendering (60% reduction in display logic complexity)
- **Request Orchestrator**: Decoupled complex request processing logic from the main system class, reducing cognitive complexity
- **Standardized Error Handling**: Comprehensive exception hierarchy with typed errors (`ServiceUnavailableError`, `InvalidParameterError`, etc.)
- **Retry Logic**: HTTP client with exponential backoff for resilient external API calls
- **Circuit Breaker Pattern**: Prevents repeated calls to failing services, improving system stability
- **Response Logger**: Centralized interaction logging for better observability
- **Code Cleanup**: Reduced main system file by 57% (608 → 257 lines) by extracting responsibilities

## Requirements

- Python 3.11+
- Dependencies listed in `requirements.txt`

Install the dependencies with:

```bash
pip install -r requirements.txt
```

If you prefer Poetry, run `poetry install` instead.

## Environment variables

Create a `.env` file or export the following variables before running the server.
See `env.example` for a complete example configuration file.

- `OPENAI_API_KEY` – API key for OpenAI based clients
- `ANTHROPIC_API_KEY` – key for Anthropic clients (optional)
- `CALENDAR_API_URL` – base URL of the calendar API (defaults to `http://localhost:8080`)
- `WEATHER_API_KEY` – API key for OpenWeatherMap used by `WeatherAgent`
- `CONFIG_SECRET` – 32-byte base64 key used to encrypt user configuration
- `JWT_SECRET` – secret key for signing authentication tokens (required)
- `LIGHTING_BACKEND` – Lighting backend to use: `"phillips_hue"` or `"yeelight"` (default: `"phillips_hue"`)
- `PHILLIPS_HUE_BRIDGE_IP` – IP address of the Philips Hue Bridge (required if using `phillips_hue` backend)
- `PHILLIPS_HUE_USERNAME` – Username for Philips Hue Bridge authentication (optional)
- `YEELIGHT_BULB_IPS` – Comma-separated list of Yeelight bulb IP addresses (optional, auto-discovers if empty)

## Running the server

Start the FastAPI application on port 8000:

```bash
python -m server.main
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

### User profiles

Jarvis now stores a profile for each authenticated user. The profile tracks the user's
name, preferred personality, interests and other traits which are injected into prompts
to personalize responses.

Use the following endpoints to manage your profile:

- `GET /users/me/profile` – retrieve the current profile data.
- `POST /users/me/profile` – update profile fields by sending any subset of the profile attributes.
- `GET /users/me/config` – fetch your stored API keys and service settings.
- `POST /users/me/config` – update any of those configuration values.

When a `/jarvis` request is processed, the stored profile is included in the request
metadata so agents can tailor their output to the user.

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
python -m jarvis.logging.log_viewer
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
from jarvis.logging import JarvisLogger

network = AgentNetwork()
# register agents with `intent_map` entries...
executor = ProtocolExecutor(network, JarvisLogger())
proto = Protocol.from_file("greet.json")
results = await executor.execute(proto, {"name": "Alice"})
```

## Recording and replaying protocols

The `MethodRecorder` can capture capability calls into an `InstructionProtocol` and replay them later. Steps may be tweaked before replay using `replace_step`:

```python
from jarvis.core import MethodRecorder

recorder = MethodRecorder()
recorder.start("demo")
recorder.record_step("dummy", "dummy_cap", {"msg": "hi"})

# Adjust the recorded step before executing
recorder.replace_step(0, "dummy", "dummy_cap", {"msg": "hello"})

# Run the recorded protocol
await recorder.replay_last_protocol(network, logger)
```

`replay_last_protocol` executes the currently recorded protocol using a `ProtocolExecutor`. This allows quick iteration on protocol steps without persisting them first.

## Standardized Agent Response Format

All agents in the Jarvis system now return responses in a consistent, structured format:

```python
{
    "success": bool,          # Whether the operation succeeded
    "response": str,          # Natural language response for the user
    "actions": [...],         # Optional: List of actions taken
    "data": {...},            # Optional: Structured data
    "metadata": {...},        # Optional: Agent-specific metadata
    "error": {...}            # Optional: Structured error information
}
```

### Benefits

- **Consistency**: All agents speak the same "language"
- **Simplified Integration**: 60% reduction in display logic complexity
- **Better Error Handling**: Structured errors with severity levels and retry hints
- **Type Safety**: Dataclasses provide validation and serialization
- **Future-Proof**: Easy to extend with new optional fields

### Example Usage

```python
from jarvis.agents.response import AgentResponse

# Success response
response = AgentResponse.success_response(
    response="I've scheduled your meeting for 2pm tomorrow.",
    actions=[{"function": "create_event", "result": {...}}],
    data={"event_id": "evt_123"}
)

# Error response
response = AgentResponse.error_response(
    response="Unable to schedule due to a conflict.",
    error=ErrorInfo(message="Calendar conflict detected")
)

# From exception
try:
    result = await risky_operation()
except Exception as e:
    response = AgentResponse.from_exception(e, user_message="Please try again.")

# Always convert to dict for network transmission
return response.to_dict()
```

See `jarvis/agents/response.py` for the complete implementation and `tests/test_agent_response.py` for comprehensive examples.

## Project structure

- `jarvis/` – main package with agent implementations and utilities
- `server/main.py` – FastAPI entrypoint (run with `python -m server.main`)
- `main.py` – simple demo using

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
