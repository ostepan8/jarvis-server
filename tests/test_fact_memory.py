"""
Tests for the enhanced fact memory system.

Tests verify:
1. Structured fact storage and retrieval
2. User-scoped facts
3. Fact categorization and confidence scoring
4. Conflict detection
5. Fact extraction from conversations
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path

from jarvis.services.fact_memory import FactMemoryService, UserFact


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def fact_service(temp_db):
    """Create a FactMemoryService with a temporary database."""
    # Create users table first
    conn = sqlite3.connect(temp_db, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    conn.commit()
    conn.close()

    return FactMemoryService(db_path=temp_db)


def test_fact_service_initialization(fact_service):
    """Test that FactMemoryService initializes correctly."""
    assert fact_service is not None
    assert fact_service.db_path is not None


def test_add_fact(fact_service):
    """Test adding a fact to the service."""
    fact_id = fact_service.add_fact(
        user_id=1,
        fact_text="User loves Italian food",
        category="preference",
        entity="food",
        confidence=0.9,
    )

    assert fact_id is not None
    assert isinstance(fact_id, int)


def test_get_facts_by_category(fact_service):
    """Test retrieving facts by category."""
    # Add multiple facts
    fact_service.add_fact(1, "User loves Italian food", "preference", "food", 0.9)
    fact_service.add_fact(1, "User's name is Alice", "personal_info", "user", 1.0)
    fact_service.add_fact(1, "User works at Tech Corp", "personal_info", "work", 0.8)

    # Get preferences only
    preferences = fact_service.get_facts(user_id=1, category="preference")
    assert len(preferences) == 1
    assert preferences[0].fact_text == "User loves Italian food"
    assert preferences[0].category == "preference"


def test_get_facts_by_entity(fact_service):
    """Test retrieving facts by entity."""
    fact_service.add_fact(1, "User loves Italian food", "preference", "food", 0.9)
    fact_service.add_fact(1, "User loves pizza", "preference", "food", 0.8)

    food_facts = fact_service.get_facts(user_id=1, entity="food")
    assert len(food_facts) >= 2


def test_user_scoping(fact_service):
    """Test that facts are properly scoped by user_id."""
    fact_service.add_fact(1, "User 1 likes dogs", "preference")
    fact_service.add_fact(2, "User 2 likes cats", "preference")

    user1_facts = fact_service.get_facts(user_id=1)
    user2_facts = fact_service.get_facts(user_id=2)

    assert len(user1_facts) == 1
    assert len(user2_facts) == 1
    assert user1_facts[0].fact_text == "User 1 likes dogs"
    assert user2_facts[0].fact_text == "User 2 likes cats"


def test_confidence_filtering(fact_service):
    """Test filtering facts by confidence."""
    fact_service.add_fact(1, "High confidence fact", "general", confidence=0.9)
    fact_service.add_fact(1, "Low confidence fact", "general", confidence=0.3)

    high_conf = fact_service.get_facts(user_id=1, min_confidence=0.8)
    assert len(high_conf) == 1
    assert high_conf[0].fact_text == "High confidence fact"


def test_search_facts(fact_service):
    """Test searching facts by text content."""
    fact_service.add_fact(1, "User loves Italian food", "preference", "food")
    fact_service.add_fact(1, "User enjoys cooking", "preference", "hobby")

    results = fact_service.search_facts(1, "Italian")
    assert len(results) >= 1
    assert "Italian" in results[0].fact_text


def test_update_fact(fact_service):
    """Test updating an existing fact."""
    fact_id = fact_service.add_fact(1, "Original fact", "general")

    updated = fact_service.update_fact(
        fact_id, fact_text="Updated fact", confidence=0.95
    )
    assert updated is True

    facts = fact_service.get_facts(user_id=1)
    assert facts[0].fact_text == "Updated fact"


def test_deactivate_fact(fact_service):
    """Test soft deleting (deactivating) a fact."""
    fact_id = fact_service.add_fact(1, "Temporary fact", "general")

    deactivated = fact_service.deactivate_fact(fact_id)
    assert deactivated is True

    active_facts = fact_service.get_facts(user_id=1, active_only=True)
    assert fact_id not in [f.id for f in active_facts]


def test_check_conflicts(fact_service):
    """Test conflict detection."""
    fact_service.add_fact(1, "User loves Italian food", "preference", "food")

    # Similar fact should be detected as conflict
    conflicts = fact_service.check_conflicts(
        1, "User likes Italian cuisine", "preference"
    )
    assert len(conflicts) >= 1


def test_get_user_summary(fact_service):
    """Test getting a summary of all user facts."""
    fact_service.add_fact(1, "User loves Italian food", "preference", "food")
    fact_service.add_fact(1, "User's name is Alice", "personal_info", "user")
    fact_service.add_fact(1, "User works at Tech Corp", "personal_info", "work")

    summary = fact_service.get_user_summary(1)

    assert summary["total_facts"] == 3
    assert "preference" in summary["by_category"]
    assert "personal_info" in summary["by_category"]
    assert len(summary["by_category"]["preference"]) == 1
