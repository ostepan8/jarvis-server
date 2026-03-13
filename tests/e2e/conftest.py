"""E2E fixtures — boot the real Jarvis pipeline with deterministic AI responses.

The system is real: NLU classifies, the network routes, agents execute.
Only things that leave the machine are mocked: HTTP APIs, MongoDB, vector DBs.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.core.config import JarvisConfig, FeatureFlags
from jarvis.core.builder import JarvisBuilder
from jarvis.core.system import JarvisSystem
from jarvis.ai_clients.scripted_client import ScriptedAIClient
from jarvis.protocols.loggers import ProtocolUsageLogger, InteractionLogger


# ---------------------------------------------------------------------------
# Deterministic search results returned by the mocked GoogleSearchService
# ---------------------------------------------------------------------------
MOCK_SEARCH_RESULTS = {
    "success": True,
    "results": [
        {
            "title": "Weather Today",
            "snippet": "Current conditions: 72F, sunny, light breeze from the west.",
            "link": "https://example.com/weather",
        },
        {
            "title": "Python Tutorials",
            "snippet": "Learn Python with hands-on examples and projects.",
            "link": "https://example.com/python",
        },
    ],
    "total_results": 2,
    "error": None,
}

MOCK_SEARCH_ERROR = {
    "success": False,
    "results": [],
    "total_results": 0,
    "error": "Service temporarily unavailable",
}

# ---------------------------------------------------------------------------
# Deterministic calendar responses
# ---------------------------------------------------------------------------
MOCK_CALENDAR_EVENTS = [
    {
        "id": "evt-001",
        "title": "Team standup",
        "time": "10:00",
        "duration_minutes": 30,
        "description": "Daily sync",
        "category": "meeting",
    },
    {
        "id": "evt-002",
        "title": "Lunch",
        "time": "12:00",
        "duration_minutes": 60,
        "description": "",
        "category": "personal",
    },
]

MOCK_CALENDAR_ADD_RESPONSE = {
    "id": "evt-003",
    "title": "Meeting",
    "time": "15:00",
    "duration_minutes": 60,
    "description": "Scheduled via Jarvis",
    "category": "meeting",
}


# ---------------------------------------------------------------------------
# Config for E2E tests — minimal, deterministic, no external dependencies
# ---------------------------------------------------------------------------
def _make_e2e_config(tmp_path) -> JarvisConfig:
    return JarvisConfig(
        ai_provider="scripted",
        api_key=None,  # No VectorMemoryService / ChromaDB
        google_search_api_key="fake-google-key",
        google_search_engine_id="fake-engine-id",
        calendar_api_url="http://localhost:9999",
        response_timeout=10.0,
        intent_timeout=5.0,
        use_fast_classifier=False,
        classification_cache_ttl=0.0,  # No caching — every request classifies fresh
        memory_vault_dir=str(tmp_path / "memory_vault"),
        feedback_dir=str(tmp_path / "feedback"),
        flags=FeatureFlags(
            enable_lights=False,
            enable_canvas=False,
            enable_night_mode=False,
            enable_roku=False,
            enable_coordinator=False,
            enable_health=False,
            enable_self_improvement=False,
            enable_feedback=False,
            enable_todo=True,
        ),
    )


# ---------------------------------------------------------------------------
# Patch targets for MongoDB loggers — prevent any real connections
# ---------------------------------------------------------------------------
_MONGO_PATCHES = [
    patch.object(ProtocolUsageLogger, "connect", new_callable=AsyncMock),
    patch.object(ProtocolUsageLogger, "close", new_callable=AsyncMock),
    patch.object(ProtocolUsageLogger, "log_usage", new_callable=AsyncMock),
    patch.object(ProtocolUsageLogger, "log_usage_structured", new_callable=AsyncMock),
    patch.object(InteractionLogger, "connect", new_callable=AsyncMock),
    patch.object(InteractionLogger, "close", new_callable=AsyncMock),
    patch.object(InteractionLogger, "log_interaction", new_callable=AsyncMock),
]


def _start_mongo_patches():
    mocks = []
    for p in _MONGO_PATCHES:
        mocks.append(p.start())
    return mocks


def _stop_mongo_patches():
    for p in _MONGO_PATCHES:
        p.stop()


# ---------------------------------------------------------------------------
# Mock external services on agent instances post-build
# ---------------------------------------------------------------------------
def _mock_search_service(system: JarvisSystem, fail: bool = False) -> AsyncMock:
    """Replace GoogleSearchService.search with a deterministic mock."""
    search_agent = system.network.agents.get("SearchAgent")
    if not search_agent:
        return AsyncMock()

    mock = AsyncMock(return_value=MOCK_SEARCH_ERROR if fail else MOCK_SEARCH_RESULTS)
    search_agent.search_service.search = mock
    return mock


def _mock_calendar_service(system: JarvisSystem) -> None:
    """Replace CalendarService methods with deterministic mocks."""
    calendar_agent = system.network.agents.get("CalendarAgent")
    if not calendar_agent:
        return

    svc = calendar_agent.command_processor.function_registry.calendar_service

    svc.get_today_events = AsyncMock(return_value=MOCK_CALENDAR_EVENTS)
    svc.get_all_events = AsyncMock(return_value=MOCK_CALENDAR_EVENTS)
    svc.get_events_by_date = AsyncMock(return_value=MOCK_CALENDAR_EVENTS)
    svc.add_event = AsyncMock(return_value=MOCK_CALENDAR_ADD_RESPONSE)
    svc.delete_event = AsyncMock(return_value={"success": True})
    svc.get_week_events = AsyncMock(return_value=MOCK_CALENDAR_EVENTS)
    svc.search_events = AsyncMock(return_value=MOCK_CALENDAR_EVENTS)
    svc.find_free_slots = AsyncMock(return_value=[])
    svc.check_conflicts = AsyncMock(return_value=[])
    svc.get_schedule_summary = AsyncMock(return_value="2 events today")


# ---------------------------------------------------------------------------
# The main fixture
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def jarvis_system(tmp_path):
    """Boot a real Jarvis system with ScriptedAIClient and mocked externals.

    Yields a running JarvisSystem ready for process_request() calls.
    """
    _start_mongo_patches()
    try:
        config = _make_e2e_config(tmp_path)
        builder = (
            JarvisBuilder(config)
            .memory(True)
            .nlu(True)
            .calendar(True)
            .chat(True)
            .search(True)
            .todo(True)
            .lights(False)
            .roku(False)
            .health(False)
            .canvas(False)
            .night_agents(False)
            .self_improvement(False)
            .protocols(True)
            .protocol_directory(False)
        )

        system = await builder.build()

        # Mock external services
        _mock_search_service(system)
        _mock_calendar_service(system)

        yield system

        await system.shutdown()
    finally:
        _stop_mongo_patches()


@pytest_asyncio.fixture
async def jarvis_system_search_fail(tmp_path):
    """Same as jarvis_system but search service returns errors."""
    _start_mongo_patches()
    try:
        config = _make_e2e_config(tmp_path)
        builder = (
            JarvisBuilder(config)
            .memory(True)
            .nlu(True)
            .calendar(True)
            .chat(True)
            .search(True)
            .todo(True)
            .lights(False)
            .roku(False)
            .health(False)
            .canvas(False)
            .night_agents(False)
            .self_improvement(False)
            .protocols(True)
            .protocol_directory(False)
        )

        system = await builder.build()
        _mock_search_service(system, fail=True)
        _mock_calendar_service(system)

        yield system

        await system.shutdown()
    finally:
        _stop_mongo_patches()
