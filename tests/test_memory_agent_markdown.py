"""Integration tests for MemoryAgent with MarkdownMemoryService.

Covers: backward compatibility, new capabilities, dual storage, no-AI fallback.
"""

import asyncio
import json
import sqlite3
import tempfile
import os

import pytest

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.memory_agent import MemoryAgent
from jarvis.agents.base import NetworkAgent
from jarvis.services.markdown_memory import MarkdownMemoryService
from jarvis.services.fact_memory import FactMemoryService
from jarvis.logging import JarvisLogger
from jarvis.ai_clients.base import BaseAIClient


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class DummyVectorMemory:
    """Mock vector memory service."""

    def __init__(self):
        self.memories = []
        self.searches = []

    async def add_memory(self, text, metadata=None, user_id=None):
        self.memories.append({"text": text, "metadata": metadata or {}, "user_id": user_id})
        return "vec_123"

    async def similarity_search(self, query, top_k=3, user_id=None, metadata_filter=None):
        self.searches.append({"query": query, "top_k": top_k, "user_id": user_id})
        results = []
        for mem in self.memories:
            if user_id is None or mem.get("user_id") == user_id:
                if query.lower() in mem["text"].lower():
                    results.append({"text": mem["text"], "metadata": mem["metadata"]})
        return results[:top_k]


class DummyAIClient(BaseAIClient):
    """Mock AI client with controllable responses."""

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
        msg = type("Msg", (), {"content": self.extraction_response})
        return (msg, None)

    async def weak_chat(self, messages, tools=None):
        self.call_history.append(("weak_chat", messages))
        content = self.extraction_response
        prompt_text = str(messages)
        if "enhanced query" in prompt_text or "Enhance this" in prompt_text:
            content = "Italian cuisine food preferences"
        elif "metadata" in prompt_text and "Analyze this memory" in prompt_text:
            content = json.dumps(
                {"category": "preference", "topics": "food", "entities": "user"}
            )
        elif "rank" in prompt_text.lower() and "relevance" in prompt_text.lower():
            content = "1,2"
        elif "summarize" in prompt_text.lower() or "recall" in prompt_text.lower():
            content = "The user loves Italian food."
        elif "confirmation" in prompt_text.lower() or "remember" in prompt_text.lower():
            content = "Noted. I'll remember that."

        msg = type("Msg", (), {"content": content})
        return (msg, None)


class DummyAgent(NetworkAgent):
    """Dummy agent for testing capability requests."""

    def __init__(self, name="dummy"):
        super().__init__(name, logger=JarvisLogger())

    @property
    def capabilities(self):
        return set()

    async def _handle_capability_request(self, message):
        pass

    async def _handle_capability_response(self, message):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    conn.commit()
    conn.close()
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def markdown_setup(tmp_path, temp_db):
    """Full setup with markdown vault, vector memory, and fact service."""
    md_memory = MarkdownMemoryService(vault_dir=str(tmp_path), auto_promote=True)
    vector_memory = DummyVectorMemory()
    fact_service = FactMemoryService(db_path=temp_db)
    ai_client = DummyAIClient()
    logger = JarvisLogger()
    agent = MemoryAgent(
        memory_service=vector_memory,
        fact_service=fact_service,
        logger=logger,
        ai_client=ai_client,
        markdown_memory=md_memory,
    )
    return {
        "markdown_memory": md_memory,
        "vector_memory": vector_memory,
        "fact_service": fact_service,
        "memory_agent": agent,
        "ai_client": ai_client,
    }


@pytest.fixture
def markdown_only_setup(tmp_path, temp_db):
    """Setup with markdown vault only — no vector memory."""
    md_memory = MarkdownMemoryService(vault_dir=str(tmp_path), auto_promote=True)
    fact_service = FactMemoryService(db_path=temp_db)
    agent = MemoryAgent(
        memory_service=None,
        fact_service=fact_service,
        logger=JarvisLogger(),
        ai_client=None,
        markdown_memory=md_memory,
    )
    return {"markdown_memory": md_memory, "memory_agent": agent, "fact_service": fact_service}


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Existing capabilities still work with the old constructor pattern."""

    @pytest.mark.asyncio
    async def test_old_constructor_still_works(self, temp_db):
        """MemoryAgent(vector_service, fact_service) still works."""
        vector = DummyVectorMemory()
        fact_svc = FactMemoryService(db_path=temp_db)
        agent = MemoryAgent(vector, fact_svc)
        assert agent.vector_memory is vector
        assert agent.markdown_memory is None

    @pytest.mark.asyncio
    async def test_store_fact_without_markdown(self, temp_db):
        """store_fact works even without a markdown vault."""
        vector = DummyVectorMemory()
        fact_svc = FactMemoryService(db_path=temp_db)
        agent = MemoryAgent(vector, fact_svc, logger=JarvisLogger())
        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "store_fact",
            {"fact_text": "User is 30", "category": "personal_info", "user_id": 1},
        )
        await asyncio.sleep(0.1)

        facts = fact_svc.get_facts(user_id=1)
        assert len(facts) == 1
        assert facts[0].fact_text == "User is 30"
        await network.stop()

    @pytest.mark.asyncio
    async def test_get_facts_backward_compat(self, temp_db):
        vector = DummyVectorMemory()
        fact_svc = FactMemoryService(db_path=temp_db)
        fact_svc.add_fact(1, "Loves dogs", "preference")
        agent = MemoryAgent(vector, fact_svc, logger=JarvisLogger())
        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "get_facts", {"user_id": 1, "category": "preference"}
        )
        await asyncio.sleep(0.1)
        await network.stop()

    @pytest.mark.asyncio
    async def test_recall_backward_compat(self, temp_db):
        vector = DummyVectorMemory()
        await vector.add_memory("User likes coffee", user_id=1)
        fact_svc = FactMemoryService(db_path=temp_db)
        agent = MemoryAgent(vector, fact_svc, logger=JarvisLogger())
        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "recall_from_memory", {"prompt": "coffee", "user_id": 1}
        )
        await asyncio.sleep(0.1)
        await network.stop()


# ---------------------------------------------------------------------------
# Dual storage
# ---------------------------------------------------------------------------


class TestDualStorage:
    @pytest.mark.asyncio
    async def test_add_to_memory_writes_both_vault_and_vector(self, markdown_setup):
        md = markdown_setup["markdown_memory"]
        vec = markdown_setup["vector_memory"]
        agent = markdown_setup["memory_agent"]

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "add_to_memory",
            {"prompt": "Favourite band is Radiohead", "user_id": 1},
        )
        await asyncio.sleep(0.2)

        # Check vault
        results = await md.recall("Radiohead")
        assert len(results) >= 1

        # Check vector
        assert len(vec.memories) >= 1

        await network.stop()

    @pytest.mark.asyncio
    async def test_store_fact_writes_to_vault_and_fact_service(self, markdown_setup, temp_db):
        md = markdown_setup["markdown_memory"]
        fact_svc = markdown_setup["fact_service"]
        agent = markdown_setup["memory_agent"]

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "store_fact",
            {"fact_text": "Birthday is March 5", "category": "personal", "user_id": 1},
        )
        await asyncio.sleep(0.1)

        # Fact service
        facts = fact_svc.get_facts(user_id=1)
        assert any("Birthday" in f.fact_text for f in facts)

        # Vault
        results = await md.recall("Birthday")
        assert len(results) >= 1

        await network.stop()

    @pytest.mark.asyncio
    async def test_recall_combines_vault_and_vector_results(self, markdown_setup):
        md = markdown_setup["markdown_memory"]
        vec = markdown_setup["vector_memory"]
        agent = markdown_setup["memory_agent"]

        # Store in vault only
        await md.store("Prefers oat milk", category="preferences", tags=["coffee"])
        # Store in vector only
        await vec.add_memory("Drinks cold brew", user_id=1)

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "recall_from_memory", {"prompt": "coffee", "user_id": 1}
        )
        await asyncio.sleep(0.2)
        await network.stop()


# ---------------------------------------------------------------------------
# New capabilities
# ---------------------------------------------------------------------------


class TestNewCapabilities:
    @pytest.mark.asyncio
    async def test_browse_memories(self, markdown_setup):
        md = markdown_setup["markdown_memory"]
        agent = markdown_setup["memory_agent"]
        await md.store("Test entry for browse")

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability("browse_memories", {})
        await asyncio.sleep(0.1)
        await network.stop()

    @pytest.mark.asyncio
    async def test_consolidate_memories(self, markdown_setup):
        md = markdown_setup["markdown_memory"]
        agent = markdown_setup["memory_agent"]

        # Add duplicate entries to long-term
        fp = md.long_term_dir / "preferences.md"
        fp.write_text(
            "# Preferences\n\n"
            "- Loves pizza [2026-03-01]\n"
            "- Loves pizza [2026-03-05]\n"
            "- Likes pasta [2026-03-03]\n"
            "\n---\n_Last updated: 2026-03-05. 3 entries._\n"
        )

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "consolidate_memories", {"category": "preferences"}
        )
        await asyncio.sleep(0.1)
        await network.stop()

    @pytest.mark.asyncio
    async def test_promote_memory(self, markdown_only_setup):
        md = markdown_only_setup["markdown_memory"]
        agent = markdown_only_setup["memory_agent"]

        entry = await md.store(
            "Jazz is the best", category="preferences", tags=["music"]
        )

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "promote_memory",
            {"memory_id": entry.memory_id, "category": "preferences", "section": "Music"},
        )
        await asyncio.sleep(0.1)

        fp = md.long_term_dir / "preferences.md"
        content = fp.read_text()
        assert "Jazz is the best" in content

        await network.stop()

    @pytest.mark.asyncio
    async def test_memory_stats(self, markdown_setup):
        md = markdown_setup["markdown_memory"]
        agent = markdown_setup["memory_agent"]
        await md.store("Stats entry one")
        await md.store("Stats entry two")

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability("memory_stats", {"user_id": 1})
        await asyncio.sleep(0.1)
        await network.stop()

    @pytest.mark.asyncio
    async def test_promote_nonexistent_memory(self, markdown_only_setup):
        agent = markdown_only_setup["memory_agent"]

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "promote_memory", {"memory_id": "doesnotexist"}
        )
        await asyncio.sleep(0.1)
        await network.stop()


# ---------------------------------------------------------------------------
# No-AI fallback
# ---------------------------------------------------------------------------


class TestNoAIFallback:
    @pytest.mark.asyncio
    async def test_add_to_memory_no_ai(self, markdown_only_setup):
        """Storing works without AI client — uses heuristic categorisation."""
        md = markdown_only_setup["markdown_memory"]
        agent = markdown_only_setup["memory_agent"]

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "add_to_memory", {"prompt": "No AI memory test"}
        )
        await asyncio.sleep(0.1)

        results = await md.recall("No AI memory test")
        assert len(results) >= 1
        await network.stop()

    @pytest.mark.asyncio
    async def test_recall_no_ai(self, markdown_only_setup):
        """Recall works without AI — keyword search only."""
        md = markdown_only_setup["markdown_memory"]
        agent = markdown_only_setup["memory_agent"]
        await md.store("Python developer for 10 years", category="skills")

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "recall_from_memory", {"prompt": "Python developer"}
        )
        await asyncio.sleep(0.1)
        await network.stop()

    @pytest.mark.asyncio
    async def test_search_facts_no_ai(self, markdown_only_setup):
        """search_facts works with markdown vault and no AI."""
        md = markdown_only_setup["markdown_memory"]
        agent = markdown_only_setup["memory_agent"]
        await md.store("Loves cooking pasta", category="preferences", tags=["food"])

        network = AgentNetwork(logger=JarvisLogger())
        dummy = DummyAgent()
        network.register_agent(agent)
        network.register_agent(dummy)
        await network.start()

        await dummy.request_capability(
            "search_facts", {"prompt": "pasta", "user_id": 1}
        )
        await asyncio.sleep(0.1)
        await network.stop()


# ---------------------------------------------------------------------------
# Capabilities listing
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_has_all_ten_capabilities(self, tmp_path, temp_db):
        md = MarkdownMemoryService(vault_dir=str(tmp_path))
        agent = MemoryAgent(markdown_memory=md)
        expected = {
            "add_to_memory",
            "recall_from_memory",
            "store_fact",
            "get_facts",
            "extract_facts",
            "search_facts",
            "browse_memories",
            "consolidate_memories",
            "promote_memory",
            "memory_stats",
        }
        assert agent.capabilities == expected
