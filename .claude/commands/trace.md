# Jarvis Trace Analysis

You are analyzing Jarvis request traces. The trace system provides hierarchical request tracing — every user request produces a **trace** containing a tree of **spans** stored in SQLite (`jarvis_traces.db`).

If the user provided arguments, pass them directly to the trace CLI as a subcommand:

```
$ARGUMENTS
```

If no arguments were provided, ask the user what they want to investigate.

---

## Trace CLI

All commands go through:

```bash
python -m jarvis.logging.trace_cli <subcommand> [options]
```

Output is JSON (or ASCII tree) to stdout — pipe-friendly.

### Subcommands

#### `last [--tree]`

Most recent trace. Returns full JSON by default, or an ASCII tree with `--tree`.

```bash
python -m jarvis.logging.trace_cli last
python -m jarvis.logging.trace_cli last --tree
```

#### `get <trace_id>`

Full trace as nested JSON — the trace record plus all spans organized into a tree via `parent_span_id`.

```bash
python -m jarvis.logging.trace_cli get <trace_id>
```

#### `tree <trace_id>`

ASCII tree visualization of a trace. Shows timing, status, agent names, capabilities, and errors at a glance.

```bash
python -m jarvis.logging.trace_cli tree <trace_id>
```

Example output:

```
[342ms] TRACE a1b2c3d4: "turn on the living room lights"  OK
├── [5ms] orchestrator.classify OK  agent=NLUAgent cap=intent_matching
├── [312ms] agent.execute OK  agent=LightingAgent cap=toggle_lights
│   ├── [8ms] service.hue_api OK
│   └── [280ms] llm.chat OK  model=gpt-4o-mini
└── [2ms] orchestrator.aggregate OK
```

#### `list [options]`

Search and filter traces. Returns an array of trace summary objects.

| Option | Description | Example |
|--------|-------------|---------|
| `--since` | Time window (relative: `1h`, `30m`, `2d`; or ISO timestamp) | `--since 1h` |
| `--until` | End time (same format as `--since`) | `--until 2025-01-01T00:00:00` |
| `--status` | Filter by status: `OK` or `ERROR` | `--status ERROR` |
| `--agent` | Filter by agent name (matches span agent_name) | `--agent LightingAgent` |
| `--capability` | Filter by capability (matches span capability) | `--capability create_event` |
| `--limit` | Max results (default: 20) | `--limit 50` |

```bash
python -m jarvis.logging.trace_cli list --since 1h --status ERROR
python -m jarvis.logging.trace_cli list --agent CalendarAgent --limit 10
```

#### `spans [options]`

Search individual spans across all traces.

| Option | Description | Example |
|--------|-------------|---------|
| `--trace-id` | Filter spans within a specific trace | `--trace-id abc123` |
| `--agent` | Filter by agent name | `--agent WeatherAgent` |
| `--capability` | Filter by capability | `--capability get_weather` |
| `--kind` | Filter by span kind (see below) | `--kind llm` |
| `--status` | Filter by status: `OK` or `ERROR` | `--status ERROR` |
| `--limit` | Max results (default: 50) | `--limit 100` |

```bash
python -m jarvis.logging.trace_cli spans --kind llm --limit 20
python -m jarvis.logging.trace_cli spans --agent RokuAgent --status ERROR
```

---

## Data Model

### Trace

One trace = one user request lifecycle, from arrival through orchestration to response.

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | string (UUID) | Unique identifier |
| `user_input` | string | The original user request text |
| `user_id` | integer | User who made the request |
| `source` | string | Request source (e.g., "api", "cli") |
| `start_time` | ISO timestamp | When the request arrived |
| `end_time` | ISO timestamp | When processing completed |
| `duration_ms` | float | Total wall-clock time in milliseconds |
| `status` | string | `OK` or `ERROR` |
| `metadata` | JSON string | Additional context |

### Span

One span = one operation within a request. Spans form a tree via `parent_span_id` — a root span has no parent, child spans reference their parent.

| Field | Type | Description |
|-------|------|-------------|
| `span_id` | string (UUID) | Unique identifier |
| `trace_id` | string (UUID) | Parent trace |
| `parent_span_id` | string (UUID) or null | Parent span (null for root spans) |
| `name` | string | Operation name (e.g., `agent.execute`, `llm.chat`) |
| `kind` | string | Span category (see SpanKinds below) |
| `agent_name` | string or null | Which agent owns this span |
| `capability` | string or null | Which capability is being executed |
| `start_time` | ISO timestamp | When the operation started |
| `end_time` | ISO timestamp | When it finished |
| `duration_ms` | float | Wall-clock time in milliseconds |
| `status` | string | `OK` or `ERROR` |
| `input_data` | JSON string | Truncated input (max 4KB) |
| `output_data` | JSON string | Truncated output (max 4KB) |
| `error` | string or null | Error message if status is ERROR |
| `attributes` | JSON string | Extra metadata (e.g., `{"model": "gpt-4o"}`) |

### SpanKinds

| Kind | What it represents |
|------|--------------------|
| `orchestrator` | Request orchestration — classification, routing, aggregation |
| `agent` | Agent-level execution of a capability |
| `llm` | LLM API call (OpenAI, Anthropic) |
| `service` | External service call (Hue API, Google Calendar, Roku, etc.) |
| `network` | Inter-agent message passing via AgentNetwork |
| `internal` | Internal helper operations |

---

## Common Diagnostic Patterns

### Find slow requests

```bash
python -m jarvis.logging.trace_cli list --since 1h --limit 50
```

Then inspect the JSON output — sort mentally or with `jq` by `duration_ms`. For a specific slow trace:

```bash
python -m jarvis.logging.trace_cli tree <trace_id>
```

The tree shows per-span timing, making it obvious where time was spent.

### Find errors

```bash
# All failed traces in the last hour
python -m jarvis.logging.trace_cli list --since 1h --status ERROR

# All failed spans (more granular — a trace can be OK overall but have a retried error span)
python -m jarvis.logging.trace_cli spans --status ERROR --limit 20
```

The `error` field on spans contains the exception type and message.

### Trace a specific request end-to-end

```bash
# Get the full nested JSON
python -m jarvis.logging.trace_cli get <trace_id>

# Or the visual tree
python -m jarvis.logging.trace_cli tree <trace_id>
```

The nested JSON from `get` includes `children` arrays on each span, showing the full hierarchy. The tree view is better for quick visual inspection.

### Analyze agent performance

```bash
# All spans for a specific agent
python -m jarvis.logging.trace_cli spans --agent CalendarAgent --limit 30

# Traces that involved a specific agent
python -m jarvis.logging.trace_cli list --agent LightingAgent --since 1d
```

### Measure LLM latency

```bash
# All LLM spans
python -m jarvis.logging.trace_cli spans --kind llm --limit 30
```

Check `duration_ms` and `attributes` (which may contain `model` info). Note: full prompt/response content is only captured when `JARVIS_TRACE_LLM_CONTENT=true` (disabled by default for privacy).

### Find traces for a specific capability

```bash
python -m jarvis.logging.trace_cli list --capability toggle_lights --since 2h
python -m jarvis.logging.trace_cli spans --capability create_event --status ERROR
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_TRACING` | `true` | Master switch — set to `false` to disable tracing entirely |
| `JARVIS_TRACE_LLM_CONTENT` | `false` | Capture full LLM prompts/responses (privacy-sensitive) |

---

## Tips

- Trace data lives in `jarvis_traces.db` (SQLite, WAL mode). You can query it directly if the CLI does not cover your needs.
- `input_data` and `output_data` are truncated to 4KB. For LLM content, enable `JARVIS_TRACE_LLM_CONTENT`.
- Context propagation uses `contextvars` — async tasks inherit the current trace automatically. Cross-boundary propagation (e.g., agent network messages) uses `trace_id` and `parent_span_id` fields on `Message`.
- The `list` command returns traces ordered by `start_time DESC`. The `spans` command also returns newest first.
- Relative time strings (`1h`, `30m`, `2d`) are converted to ISO timestamps internally. You can also pass ISO timestamps directly.
