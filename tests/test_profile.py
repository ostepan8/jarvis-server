"""Tests for jarvis.core.profile — AgentProfile user profile management."""

import pytest

from jarvis.core.profile import AgentProfile


class TestAgentProfileDefaults:
    """Tests for AgentProfile default values and __post_init__."""

    def test_default_values(self):
        p = AgentProfile()
        assert p.name is None
        assert p.preferred_personality == "friendly"
        assert p.interests == []
        assert p.conversation_style == "casual"
        assert p.humor_preference == "witty"
        assert p.topics_of_interest == []
        assert p.language_preference == "english"
        assert p.interaction_count == 0
        assert p.favorite_games == []
        assert p.last_seen is None
        assert p.required_resources == []

    def test_none_lists_initialized_to_empty(self):
        """__post_init__ should convert None list fields to empty lists."""
        p = AgentProfile(
            interests=None,
            topics_of_interest=None,
            favorite_games=None,
            required_resources=None,
        )
        assert p.interests == []
        assert p.topics_of_interest == []
        assert p.favorite_games == []
        assert p.required_resources == []


class TestAgentProfileCustomValues:
    """Tests for AgentProfile with custom values."""

    def test_custom_name(self):
        p = AgentProfile(name="Alice")
        assert p.name == "Alice"

    def test_custom_personality(self):
        p = AgentProfile(preferred_personality="formal")
        assert p.preferred_personality == "formal"

    def test_custom_interests(self):
        p = AgentProfile(interests=["music", "coding"])
        assert p.interests == ["music", "coding"]

    def test_custom_conversation_style(self):
        p = AgentProfile(conversation_style="professional")
        assert p.conversation_style == "professional"

    def test_custom_humor_preference(self):
        p = AgentProfile(humor_preference="dry")
        assert p.humor_preference == "dry"

    def test_custom_topics_of_interest(self):
        p = AgentProfile(topics_of_interest=["AI", "robotics"])
        assert p.topics_of_interest == ["AI", "robotics"]

    def test_custom_language(self):
        p = AgentProfile(language_preference="spanish")
        assert p.language_preference == "spanish"

    def test_custom_interaction_count(self):
        p = AgentProfile(interaction_count=100)
        assert p.interaction_count == 100

    def test_custom_favorite_games(self):
        p = AgentProfile(favorite_games=["chess", "go"])
        assert p.favorite_games == ["chess", "go"]

    def test_custom_last_seen(self):
        p = AgentProfile(last_seen="2026-03-09T12:00:00")
        assert p.last_seen == "2026-03-09T12:00:00"

    def test_custom_required_resources(self):
        p = AgentProfile(required_resources=["gpu", "memory"])
        assert p.required_resources == ["gpu", "memory"]

    def test_all_custom_values(self):
        p = AgentProfile(
            name="Bob",
            preferred_personality="sarcastic",
            interests=["gaming"],
            conversation_style="formal",
            humor_preference="slapstick",
            topics_of_interest=["sports"],
            language_preference="french",
            interaction_count=50,
            favorite_games=["tetris"],
            last_seen="2025-01-01",
            required_resources=["api_key"],
        )
        assert p.name == "Bob"
        assert p.preferred_personality == "sarcastic"
        assert p.interests == ["gaming"]
        assert p.conversation_style == "formal"
        assert p.humor_preference == "slapstick"
        assert p.topics_of_interest == ["sports"]
        assert p.language_preference == "french"
        assert p.interaction_count == 50
        assert p.favorite_games == ["tetris"]
        assert p.last_seen == "2025-01-01"
        assert p.required_resources == ["api_key"]


class TestAgentProfileMutability:
    """Tests for modifying AgentProfile fields after creation."""

    def test_modify_interests(self):
        p = AgentProfile()
        p.interests.append("reading")
        assert "reading" in p.interests

    def test_modify_interaction_count(self):
        p = AgentProfile()
        p.interaction_count += 1
        assert p.interaction_count == 1

    def test_set_name_after_creation(self):
        p = AgentProfile()
        p.name = "Eve"
        assert p.name == "Eve"

    def test_set_last_seen(self):
        p = AgentProfile()
        p.last_seen = "2026-03-09"
        assert p.last_seen == "2026-03-09"


class TestAgentProfileEdgeCases:
    """Edge case tests for AgentProfile."""

    def test_empty_string_name(self):
        p = AgentProfile(name="")
        assert p.name == ""

    def test_zero_interaction_count(self):
        p = AgentProfile(interaction_count=0)
        assert p.interaction_count == 0

    def test_empty_lists_provided(self):
        """Providing empty lists explicitly should work the same as defaults."""
        p = AgentProfile(interests=[], topics_of_interest=[], favorite_games=[])
        assert p.interests == []
        assert p.topics_of_interest == []
        assert p.favorite_games == []

    def test_large_interaction_count(self):
        p = AgentProfile(interaction_count=999999)
        assert p.interaction_count == 999999

    def test_from_dict_kwargs(self):
        """AgentProfile can be constructed from unpacked dict kwargs."""
        data = {
            "name": "Test",
            "preferred_personality": "cheerful",
            "interaction_count": 5,
        }
        p = AgentProfile(**data)
        assert p.name == "Test"
        assert p.preferred_personality == "cheerful"
        assert p.interaction_count == 5
        # Non-provided fields get defaults
        assert p.interests == []
