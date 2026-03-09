# Jarvis Server — Claude Code Guidelines

## Worktree-First Workflow

**EVERY code change goes into a worktree. No exceptions.** Multiple Claude Code instances run concurrently on this repo. Working on `main` or a shared branch will cause conflicts and failures.

### Rules

1. **Immediately enter a worktree** at session start before any code changes — use `EnterWorktree` and auto-generate the name from the task (e.g., user says "add Spotify agent" → worktree name `feature-spotify-agent`). Never ask the user to name it.
2. **One worktree = one concern.** If the user asks for 3 things, that's 3 worktrees via parallel `Task` agents with `isolation: "worktree"`.
3. **Never commit directly to `main`.** All work happens in worktrees. Merge to `main` only via the merge procedure below. Never reuse another session's worktree.
4. **Auto-name worktrees** using the format `{type}-{kebab-description}` derived from the task:
   - `feature-spotify-agent`
   - `fix-nlu-empty-input-timeout`
   - `refactor-agent-factory-cleanup`
   - `test-memory-agent-edge-cases`

### Parallel Execution

Multiple Claude Code instances are running at the same time. Design every change to be merge-safe:

1. **Decompose immediately** — split every request into the smallest independent units. Each gets its own worktree.
2. **Launch in parallel** — use `Task` tool with `isolation: "worktree"` for each unit. Run them concurrently.
3. **Make changes additive** — append to lists, add new methods, add new files. Never rewrite existing lines in shared files unless that's the actual task.
4. **Use the isolation map** to determine what's safe to parallelize.

### Module Isolation Map

| Module | Files | Safe to parallelize? |
|--------|-------|---------------------|
| `agents/*_agent/` | Individual agent dirs | Yes — agents are self-contained |
| `services/` | Individual service files | Yes — services are independent |
| `core/` | system, builder, config, orchestrator | CAUTION — shared by everything |
| `protocols/` | Protocol system | Yes — isolated subsystem |
| `cli/` | Dashboards and modes | Yes — UI layer only |
| `server/routers/` | Individual route files | Yes — routers are independent |
| `io/` | Input/output handlers | Yes — isolated subsystem |
| `ai_clients/` | LLM client wrappers | CAUTION — shared by agents |
| `tests/` | Test files | Yes — tests are independent |

**High-conflict files** (never modify these in parallel across worktrees):
- `jarvis/core/system.py`
- `jarvis/agents/factory.py`
- `jarvis/core/config.py`
- `jarvis/agents/nlu_agent/__init__.py`

### After Work Completes — Mandatory Merge & Cleanup

**Every worktree MUST be merged and removed before reporting done. No orphaned worktrees.**

A task is NOT done until the worktree is gone and the code is on `main`. Follow this exact sequence:

1. **Run targeted tests** in the worktree:
   ```bash
   pytest tests/test_affected.py -v
   ```
2. **Commit** all changes with a proper commit message (see Naming Conventions).
3. **Switch to main** and merge the worktree branch:
   ```bash
   # From the main repo root (not the worktree dir)
   GIT_DIR=/path/to/repo/.git GIT_WORK_TREE=/path/to/repo git merge <worktree-branch> --no-edit
   ```
4. **Resolve conflicts** if any — keep changes from both sides, never silently drop code. After resolving, stage and complete the merge commit.
5. **Run the full test suite** on main:
   ```bash
   pytest -x --timeout=30 -q
   ```
   If tests fail, fix them on main and commit the fix before proceeding.
6. **Remove the worktree and its branch**:
   ```bash
   git worktree remove --force .claude/worktrees/<name>
   git branch -D worktree-<name>
   ```
7. **Push to origin**:
   ```bash
   git push origin main
   ```
8. **Report** to the user: branch merged, files changed, test count & result, conflicts resolved (if any).

### Merge Rules

- **Merge immediately** — do not leave worktrees sitting around "for later." When the code works and tests pass, merge it.
- **One worktree at a time** — if multiple worktrees are ready, merge them sequentially (smallest/safest first) to catch conflicts early.
- **Never force-push main** — if the remote has diverged, pull first, then push.
- **Conflict resolution principle** — when merging touches the same file from different worktrees, keep ALL additions from both sides. Only remove code if it was the explicit purpose of one of the branches.
- **Test after every merge** — run `pytest -x --timeout=30 -q` after each merge, not just the last one. Fix failures before merging the next branch.

### Subagent Worktrees (Task tool with `isolation: "worktree"`)

When launching parallel subagents with `isolation: "worktree"`:
1. Each subagent works in its own worktree — this is automatic.
2. **The parent agent is responsible for merging.** When subagents complete, the parent must merge each worktree branch into main following the sequence above.
3. Merge in dependency order — if agent B's changes depend on agent A's, merge A first.

## Testing Requirements

**No code ships without tests. Tests are not optional — they are part of the definition of done.**

### Test-Driven Rules

1. **Write tests alongside code, not after.** Every new function, capability, or agent gets tests in the same worktree, same commit.
2. **Run tests before committing.** Run `pytest` on affected test files before every commit. If tests fail, fix them before committing. Never commit with failing tests.
3. **Run the full suite before reporting done.** After all changes are complete, run `pytest` to catch regressions. Report the result.
4. **Test coverage expectations:**
   - New agent → test file `tests/test_{name}_agent.py` with tests for every capability
   - New service → test file `tests/test_{name}_service.py`
   - Bug fix → add a regression test that reproduces the bug
   - Refactor → existing tests must still pass; add tests if coverage gaps are found
5. **Never delete or skip tests** to make a commit pass

### Test Patterns

```python
# Framework: pytest + pytest-asyncio
# Location: tests/test_{feature}.py

import pytest
from jarvis.agents.response import AgentResponse

class TestFeatureName:
    """Group related tests in a class."""

    def test_success_case(self):
        """Test the happy path."""
        ...

    def test_error_handling(self):
        """Test failure modes."""
        ...

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Async tests use the marker."""
        ...
```

- Use `DummyAIClient` from `jarvis/ai_clients/dummy_client.py` for mocking LLM calls
- Use descriptive test names: `test_calendar_create_event_with_missing_date_returns_error`
- Test edge cases: empty input, None values, timeouts, malformed data
- Assert on `AgentResponse` fields: `success`, `response`, `actions`, `error`

### What to Run

```bash
pytest tests/test_specific.py -v   # Targeted (run this during development)
pytest                              # Full suite (run this before reporting done)
pytest -x                           # Stop on first failure (useful for debugging)
```

## Project Overview

Jarvis Server is a **FastAPI-based multi-agent orchestration system**. It routes user requests through NLU classification to specialized agents (calendar, weather, lights, Roku, search, memory, chat) that communicate over a decentralized agent network.

### Architecture

```
User Request → RequestOrchestrator → Protocol Match (fast) / NLU Route (fallback)
  → Agent(s) execute capability → AgentResponse → Aggregation → User
```

### Key Modules

| Path | Purpose |
|------|---------|
| `jarvis/core/system.py` | `JarvisSystem` — main orchestrator, manages agent lifecycle |
| `jarvis/core/builder.py` | `JarvisBuilder` — fluent API for system construction |
| `jarvis/core/config.py` | `JarvisConfig`, `ConfigProfile`, `FeatureFlags` |
| `jarvis/core/orchestrator.py` | `RequestOrchestrator` — request routing pipeline |
| `jarvis/agents/base.py` | `NetworkAgent` — base class all agents inherit |
| `jarvis/agents/factory.py` | `AgentFactory` — builds agents from config |
| `jarvis/agents/agent_network.py` | `AgentNetwork` — decentralized message routing |
| `jarvis/agents/response.py` | `AgentResponse` — standardized response format |
| `jarvis/agents/nlu_agent/` | NLU intent classification and routing |
| `jarvis/ai_clients/` | LLM client wrappers (OpenAI, Anthropic) |
| `jarvis/services/` | External service integrations |
| `jarvis/protocols/` | Protocol system — recorded workflows with DAG execution |
| `jarvis/cli/` | CLI dashboards (config, commands) |
| `jarvis/io/` | Input (wake word, transcription) and output (TTS) |
| `jarvis/logging/` | `JarvisLogger` — stdout + SQLite logging |
| `server/` | FastAPI HTTP server, routers, auth, database |
| `main.py` | Interactive demo (console/voice modes) |

### Agents

| Agent | Capabilities |
|-------|-------------|
| `NLUAgent` | `intent_matching` — classifies and routes requests |
| `ChatAgent` | `chat` — conversational AI, fact storage |
| `CalendarAgent` | `create_event`, `list_events`, `delete_event`, `modify_event` |
| `WeatherAgent` | `get_weather`, `get_forecast` |
| `MemoryAgent` | `store_fact`, `retrieve_facts` — vector + structured memory |
| `LightingAgent` | `set_color`, `set_brightness`, `toggle_lights`, `list_lights` |
| `RokuAgent` | `play_app`, `navigate`, `type`, `press_button`, `get_status` |
| `SearchAgent` | `search`, `news_search` |
| `ProtocolAgent` | `execute_protocol`, `list_protocols` |
| `CanvasAgent` | Canvas drawing operations |

### Data Flow

1. Request enters via CLI (`main.py`), HTTP (`server/main.py`), or voice
2. `RequestOrchestrator` checks protocol matches first (fast path)
3. Falls back to `NLUAgent` for intent classification
4. Routed agent executes capability, returns `AgentResponse`
5. Responses aggregated and returned to user

## Naming Conventions

### Branch Names

Format: `{type}/{kebab-case-description}`

| Type | Use When | Example |
|------|----------|---------|
| `feature/` | Adding new functionality | `feature/recurring-calendar-events` |
| `fix/` | Fixing a bug | `fix/nlu-timeout-on-empty-input` |
| `refactor/` | Restructuring without behavior change | `refactor/agent-factory-cleanup` |
| `test/` | Adding or improving tests only | `test/memory-agent-edge-cases` |
| `chore/` | Config, deps, CI, non-code changes | `chore/update-requirements` |

### Commit Messages

Format: `{type}({scope}): {imperative description}`

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `chore`

**Scopes:** `agents`, `nlu`, `core`, `protocols`, `services`, `cli`, `server`, `io`, `logging`, `ai-clients`, `tests`

**Examples:**
```
feat(agents): add recurring event support to CalendarAgent
fix(nlu): handle empty input without timeout
refactor(core): extract orchestrator retry logic into mixin
test(protocols): add DAG execution edge case coverage
perf(services): cache weather API responses for 5 minutes
```

**Rules:**
- Imperative mood: "add", "fix", "remove" — not "added", "fixes", "removing"
- Lowercase after the colon, no period, under 72 chars
- Never write vague messages like "changes", "updates", "fix stuff"

### Code Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Agent classes | `PascalCase` + `Agent` | `CalendarAgent` |
| Service classes | `PascalCase` + `Service` | `CalendarService` |
| Factory/Registry | `PascalCase` + type suffix | `AgentFactory` |
| Config classes | `PascalCase` + `Config` | `JarvisConfig` |
| Capabilities | `snake_case` verb phrases | `create_event` |
| Feature flags | `enable_` prefix | `enable_weather` |
| Files | `snake_case.py` | `weather_service.py` |
| Agent dirs | `{name}_agent/` with `__init__.py` | `calendar_agent/` |
| Test files | `test_{feature}.py` | `test_calendar_agent.py` |
| Private methods | `_` prefix | `_handle_capability_request` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |

## Coding Standards

### Adding a New Agent (checklist)

**Independent** (can parallelize in separate worktrees):
1. `jarvis/agents/{name}_agent/__init__.py` — agent implementation
2. `jarvis/services/{name}_service.py` — service layer if needed
3. `tests/test_{name}_agent.py` — tests for every capability

**Shared files** (do in one pass after independent work merges):
4. `jarvis/agents/factory.py` — register in factory
5. `jarvis/agents/nlu_agent/__init__.py` — add intent route
6. `jarvis/core/config.py` — add feature flag

### Response Format

All agents MUST return `AgentResponse`:
```python
AgentResponse(
    success=True,
    response="Human-friendly message",
    actions=[{"type": "event_created", "details": {...}}],
    data={"structured": "data"},
    metadata={"agent": "calendar"},
)
```

### Patterns to Follow

- **Factory pattern** for agent/client construction
- **Fluent builder** for system setup
- **Async everywhere** — all handlers and network calls
- **Decentralized messaging** — agents talk through `AgentNetwork`, never direct imports
- **Feature flags** — gate new capabilities behind `JarvisConfig.feature_flags`
- **Standardized errors** — use `jarvis/core/errors.py` exception hierarchy

### Anti-Patterns

- Don't import one agent from another — use the network
- Don't add capabilities without updating NLU routing
- Don't skip `AgentResponse` — raw dicts/strings break the pipeline
- Don't put business logic in routers — keep it in agents/services
- Don't hardcode IPs or secrets — use env vars and config

## Running the Project

```bash
python -m server.main              # FastAPI server on port 8000
python main.py                     # Interactive demo
pytest                              # Full test suite
python -m jarvis.logging.log_viewer # Log viewer
```

## Environment Variables

Required: `OPENAI_API_KEY`, `JWT_SECRET`
Optional: `ANTHROPIC_API_KEY`, `WEATHER_API_KEY`, `ROKU_IP_ADDRESS`, `PHILLIPS_HUE_BRIDGE_IP`, `PHILLIPS_HUE_USERNAME`, `LIGHTING_BACKEND`, `YEELIGHT_BULB_IPS`, `GOOGLE_SEARCH_API_KEY`, `MONGO_URI`, `CALENDAR_API_URL`, `JARVIS_VERBOSE`
