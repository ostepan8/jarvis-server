# Personal Scheduler Integration with Jarvis

This document explains how to run the Personal Scheduler C++ server and connect it to Jarvis.

## Prerequisites

- C++17 compiler (g++ or clang++)
- SQLite3 development libraries
- libcurl development libraries
- Python 3.11+ (for Jarvis)

## Building the Scheduler Server

1. Navigate to the personal-scheduler directory:
```bash
cd personal-scheduler
```

2. Build the server:
```bash
make clean && make server
```

3. The executable will be created as `scheduler_server` in the personal-scheduler directory.

## Configuration

### Scheduler Server (.env)

Create a `.env` file in the `personal-scheduler` directory (or use environment variables):

```env
# API Authentication (optional - leave empty to disable auth)
API_KEY=
ADMIN_API_KEY=

# Server Configuration
HOST=127.0.0.1
PORT=8080

# CORS Configuration
CORS_ORIGIN=http://localhost:3004

# Rate Limiting
RATE_LIMIT=100
RATE_WINDOW=60

# Wake Server (optional)
WAKE_SERVER_URL=
```

### Jarvis Configuration

The Jarvis system is already configured to connect to the scheduler at `http://localhost:8080` by default.

In your main `.env` file (at the root of mcp-server), ensure you have:

```env
CALENDAR_API_URL=http://localhost:8080
```

Or leave it unset to use the default.

## Running the Systems

### Step 1: Start the Scheduler Server

In one terminal:

```bash
cd personal-scheduler
./scheduler_server
```

The server will start on `http://localhost:8080` (or the port specified in your `.env`).

### Step 2: Start Jarvis

In another terminal:

```bash
# From the mcp-server root directory
python -m server.main
```

Or run the demo:

```bash
python main.py
```

## API Endpoints

The scheduler server provides the following endpoints that Jarvis uses:

- `GET /events` - List all events
- `GET /events/next` - Get next event
- `GET /events/day/{date}` - Get events for a specific date (YYYY-MM-DD)
- `GET /events/week/{date}` - Get events for a week starting from date
- `GET /events/month/{year-month}` - Get events for a month (YYYY-MM)
- `GET /events/search?q={query}` - Search events
- `GET /events/range/{start}/{end}` - Get events in date range
- `POST /events` - Create new event
- `PUT /events/{id}` - Update event
- `PATCH /events/{id}` - Partially update event
- `DELETE /events/{id}` - Delete event
- `GET /free-slots/{date}` - Find free time slots
- `GET /free-slots/next` - Find next available slot
- `GET /categories` - Get all event categories
- `GET /recurring` - Get recurring events
- `POST /recurring` - Create recurring event

## Testing the Integration

1. Start the scheduler server
2. Start Jarvis
3. Use Jarvis to interact with the calendar:

```python
# Example: Ask Jarvis to add an event
"What's on my calendar today?"
"Add a meeting tomorrow at 2pm"
"Show me my schedule for next week"
```

## Troubleshooting

### Server won't start

- Check that port 8080 is not already in use
- Verify SQLite3 and libcurl are installed
- Check build errors: `make clean && make server`

### Jarvis can't connect to scheduler

- Verify the scheduler server is running: `curl http://localhost:8080/events`
- Check `CALENDAR_API_URL` in your `.env` file
- Ensure the port matches (default: 8080)

### Authentication errors

- If you set `API_KEY` in the scheduler `.env`, you must also set `CALENDAR_API_KEY` in Jarvis's `.env`
- Or leave both empty to disable authentication

## Database

The scheduler uses SQLite and creates `events.db` in the `personal-scheduler` directory automatically on first run.






