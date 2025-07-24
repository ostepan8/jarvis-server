# Frontend Integration Guide

This document describes how to interface with the Jarvis Server REST API. It covers each HTTP endpoint, the expected request/response formats and headers, and general workflow recommendations for a frontend AI client.

## Server Overview

The FastAPI server exposes collaborative AI agents that can process natural language commands, execute predefined protocols and manage user preferences. Authentication uses JSON Web Tokens (JWT).

Start the server with:

```bash
python server.py
```

The default port is `8000`.

## Authentication Endpoints

All authenticated routes expect an `Authorization: Bearer <token>` header. Obtain a token via `/auth/signup` or `/auth/login`.

### `POST /auth/signup`
Create a new account.

Request body (`application/json`):
```json
{ "email": "user@example.com", "password": "..." }
```

Successful response:
```json
{ "token": "<jwt>" }
```
If the user already exists an error message is returned with status `401`.

### `POST /auth/login`
Login with existing credentials.
Body and response are identical to `/auth/signup`.
Failed authentication returns `401`.

### `GET /auth/verify`
Check if a provided token is valid.
Requires `Authorization` header. Response on success:
```json
{ "email": "user@example.com" }
```

## Jarvis Command Endpoints

### `POST /jarvis`
Execute a natural language command with the agent network.

Headers:
- `Authorization: Bearer <token>`
- `X-Timezone` *(optional)* – IANA timezone name. Defaults to the server timezone.
- `X-Device`, `X-Location`, `X-User`, `X-Source` *(optional)* – additional context passed as metadata.

Request body:
```json
{ "command": "Schedule a meeting tomorrow" }
```

Response is the final structured result returned by the orchestrator. Example:
```json
{
  "result": "Event created",
  "steps": [...]
}
```
The exact schema depends on the active agents and protocols.

### `GET /jarvis/agents`
Return a mapping of all available agents.
Example response:
```json
{
  "CalendarAgent": "CollaborativeCalendarAgent",
  "WeatherAgent": "WeatherAgent"
}
```

### `GET /jarvis/agents/{name}/capabilities`
List capability definitions for the specified agent.
Response is an array describing each capability and its parameters.

## Protocol Management

Protocols define reusable sequences of agent steps.

### `GET /protocols`
Return all registered protocols and their metadata.
Response format:
```json
{ "protocols": [ { "name": "greet", "description": "..." }, ... ] }
```

### `POST /protocols/run`
Execute a protocol by name or provide a complete definition.

Body (`protocol` and `protocol_name` are mutually exclusive):
```json
{
  "protocol_name": "greet",
  "arguments": { "name": "Alice" }
}
```
Or
```json
{
  "protocol": { "name": "greet", "steps": [...] },
  "arguments": { ... }
}
```

Response example:
```json
{
  "protocol": "greet",
  "results": ["Hello Alice", "Bye Alice"]
}
```

## User Agent Preferences

Each user can allow or block specific agents.

### `GET /users/me/agents`
Return two lists: `allowed` and `disallowed` agents for the current user. If no preferences exist all agents are allowed by default.

### `POST /users/me/agents`
Update the user's allowed/disallowed agents.

Body format:
```json
{ "allowed": ["WeatherAgent"], "disallowed": ["LightsAgent"] }
```

Response:
```json
{ "success": true }
```

## Usage Workflow
1. **Sign up or log in** to obtain a JWT token.
2. **Call `/jarvis`** with a natural language command. Optionally query `/jarvis/agents` to inspect available agents first.
3. **Review the result** and use `/protocols` or `/protocols/run` to execute complex multi-step workflows.
4. **Manage agent permissions** using `/users/me/agents` to restrict which agents may act on the user's behalf.

Include the token in the `Authorization` header for all protected endpoints. Provide timezone information with `X-Timezone` for accurate calendar handling.

## Environment Variables

The server relies on several environment variables:
- `OPENAI_API_KEY` – used by default AI clients.
- `CALENDAR_API_URL` – URL of the calendar backend (defaults to `http://localhost:8080`).
- `WEATHER_API_KEY` – required by the `WeatherAgent`.
- `JWT_SECRET` – secret key for signing tokens.
- `AUTH_DB_PATH` – path of the SQLite auth database (defaults to `auth.db`).

Ensure these are set before launching the server.

## Example Curl Session
```bash
# Sign up
curl -X POST http://localhost:8000/auth/signup -d '{"email": "a@b.com", "password": "pass"}' -H 'Content-Type: application/json'
# -> {"token": "..."}

# Use the token
curl -X POST http://localhost:8000/jarvis \
     -H 'Authorization: Bearer <token>' \
     -H 'X-Timezone: America/Los_Angeles' \
     -d '{"command": "list my meetings"}' -H 'Content-Type: application/json'
```
This should return the AI-generated result of the command.

