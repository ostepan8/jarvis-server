"""
Tests for enhanced MemoryAgent with fact extraction and user-scoped memory.
"""

import pytest
import asyncio
import sqlite3
import tempfile
import os
import json

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.memory_agent import MemoryAgent
from jarvis.agents.base import NetworkAgent
from jarvis.services.vector_memory import VectorMemoryService
from jarvis.services.fact_memory import FactMemoryService
from jarvis.logging import JarvisLogger
from jarvis.ai_clients.base import BaseAIClient


class DummyVectorMemory:
    """Mock vector memory service for testing."""

    def __init__(self):
        self.memories = []
        self.searches = []

    async def add_memory(self, text, metadata=None, user_id=None):
        self.memories.append(
            {"text": text, "metadata": metadata or {}, "user_id": user_id}
        )
        return "mem_123"

    async def similarity_search(
        self, query, top_k=3, user_id=None, metadata_filter=None
    ):
        self.searches.append({"query": query, "top_k": top_k, "user_id": user_id})
        # Return relevant memories based on user_id
        results = []
        for mem in self.memories:
            if user_id is None or mem.get("user_id") == user_id:
                if query.lower() in mem["text"].lower():
                    results.append({"text": mem["text"], "metadata": mem["metadata"]})
        return results[:top_k]


class DummyAIClient(BaseAIClient):
    """Mock AI client for testing."""

    def __init__(self, extraction_response=None):
        self.extraction_response = extraction_response or json.dumps(
            [
                {
                    "fact_text": "User loves Italian food",
                    "category": "preference",
                    "entity": "food",
                    "confidence": 0.9,
                }
            ]
        )
        self.call_history = []

    async def strong_chat(self, messages, tools=None):
        self.call_history.append(("strong_chat", messages))
        content = self.extraction_response
        msg = type("Msg", (), {"content": content})
        return (msg, None)

    async def weak_chat(self, messages, tools=None):
        self.call_history.append(("weak_chat", messages))
        content = self.extraction_response
        if "enhanced query" in str(messages):
            content = "Italian cuisine food preferences"
        elif "metadata" in str(messages):
            content = json.dumps(
                {"category": "preference", "topics": "food", "entities": "user"}
            )
        elif "rank" in str(messages):
            content = "1,2"
        elif "summarize" in str(messages):
            content = "The user loves Italian food."

        msg = type("Msg", (), {"content": content})
        return (msg, None)


class DummyAgent(NetworkAgent):
    """Dummy agent for testing."""

    def __init__(self, name="dummy"):
        super().__init__(name, logger=JarvisLogger())

    @property
    def capabilities(self):
        return set()

    async def _handle_capability_request(self, message):
        pass

    async def _handle_capability_response(self, message):
        pass


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Create users table
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    conn.commit()
    conn.close()

    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def memory_setup(temp_db):
    """Setup memory services and agent."""
    vector_memory = DummyVectorMemory()
    fact_service = FactMemoryService(db_path=temp_db)
    ai_client = DummyAIClient()
    logger = JarvisLogger()
    memory_agent = MemoryAgent(vector_memory, fact_service, logger, ai_client)

    return {
        "vector_memory": vector_memory,
        "fact_service": fact_service,
        "memory_agent": memory_agent,
        "ai_client": ai_client,
    }


@pytest.mark.asyncio
async def test_store_fact_capability(memory_setup, temp_db):
    """Test storing a fact via MemoryAgent."""
    network = AgentNetwork(logger=JarvisLogger())
    memory_agent = memory_setup["memory_agent"]
    fact_service = memory_setup["fact_service"]
    dummy = DummyAgent()

    network.register_agent(memory_agent)
    network.register_agent(dummy)
    await network.start()

    # Store a fact
    req_id = await dummy.request_capability(
        "store_fact",
        {
            "fact_text": "User loves pizza",
            "category": "preference",
            "entity": "food",
            "user_id": 1,
            "confidence": 0.9,
        },
    )

    # Wait for response
    await asyncio.sleep(0.1)  # Give time for async processing

    # Verify fact was stored
    facts = fact_service.get_facts(user_id=1)
    assert len(facts) == 1
    assert facts[0].fact_text == "User loves pizza"

    await network.stop()


@pytest.mark.asyncio
async def test_get_facts_capability(memory_setup):
    """Test retrieving facts via MemoryAgent."""
    network = AgentNetwork(logger=JarvisLogger())
    memory_agent = memory_setup["memory_agent"]
    fact_service = memory_setup["fact_service"]
    dummy = DummyAgent()

    # Pre-populate facts
    fact_service.add_fact(1, "User loves pizza", "preference", "food")
    fact_service.add_fact(1, "User's name is Alice", "personal_info", "user")

    network.register_agent(memory_agent)
    network.register_agent(dummy)
    await network.start()

    # Request facts
    req_id = await dummy.request_capability(
        "get_facts",
        {
            "user_id": 1,
            "category": "preference",
            "limit": 10,
        },
    )

    await asyncio.sleep(0.1)

    await network.stop()


@pytest.mark.asyncio
async def test_extract_facts_capability(memory_setup):
    """Test extracting facts from conversation."""
    network = AgentNetwork(logger=JarvisLogger())
    memory_agent = memory_setup["memory_agent"]
    fact_service = memory_setup["fact_service"]
    dummy = DummyAgent()

    network.register_agent(memory_agent)
    network.register_agent(dummy)
    await network.start()

    # Extract facts from conversation
    req_id = await dummy.request_capability(
        "extract_facts",
        {
            "conversation_text": "User: I love Italian food\nAssistant: That's great!",
            "user_id": 1,
        },
    )

    await asyncio.sleep(0.5)  # Give time for AI processing

    # Verify facts were extracted and stored
    facts = fact_service.get_facts(user_id=1)
    assert len(facts) > 0

    await network.stop()


@pytest.mark.asyncio
async def test_recall_with_user_scoping(memory_setup):
    """Test that recall respects user_id scoping."""
    network = AgentNetwork(logger=JarvisLogger())
    memory_agent = memory_setup["memory_agent"]
    vector_memory = memory_setup["vector_memory"]
    fact_service = memory_setup["fact_service"]
    dummy = DummyAgent()

    # Store facts for different users
    fact_service.add_fact(1, "User 1 loves pizza", "preference")
    fact_service.add_fact(2, "User 2 loves sushi", "preference")

    await vector_memory.add_memory("User 1 loves pizza", {"user_id": 1}, user_id=1)
    await vector_memory.add_memory("User 2 loves sushi", {"user_id": 2}, user_id=2)

    network.register_agent(memory_agent)
    network.register_agent(dummy)
    await network.start()

    # Recall for user 1
    req_id = await dummy.request_capability(
        "recall_from_memory",
        {
            "prompt": "pizza",
            "top_k": 5,
            "user_id": 1,
        },
    )

    await asyncio.sleep(0.2)

    # Verify search was scoped to user 1
    searches = vector_memory.searches
    assert len(searches) > 0
    assert searches[-1]["user_id"] == 1

    await network.stop()


@pytest.mark.asyncio
async def test_add_to_memory_with_user_id(memory_setup):
    """Test adding memory with user_id."""
    network = AgentNetwork(logger=JarvisLogger())
    memory_agent = memory_setup["memory_agent"]
    vector_memory = memory_setup["vector_memory"]
    dummy = DummyAgent()

    network.register_agent(memory_agent)
    network.register_agent(dummy)
    await network.start()

    # Add memory with user_id
    req_id = await dummy.request_capability(
        "add_to_memory",
        {
            "prompt": "Remember: User loves coffee",
            "metadata": {"type": "preference"},
            "user_id": 1,
        },
    )

    await asyncio.sleep(0.1)

    # Verify memory was stored with user_id
    assert len(vector_memory.memories) > 0
    stored = vector_memory.memories[-1]
    assert stored["user_id"] == 1

    await network.stop()
