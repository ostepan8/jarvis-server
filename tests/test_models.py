"""Tests for server.models — Pydantic request/response models."""

import pytest
from pydantic import ValidationError

from server.models import (
    JarvisRequest,
    AuthRequest,
    ProtocolRunRequest,
    UserProfile,
    UserProfileUpdate,
    UserConfig,
    UserConfigUpdate,
)


class TestJarvisRequest:
    """Tests for the JarvisRequest model."""

    def test_valid_command(self):
        req = JarvisRequest(command="turn on the lights")
        assert req.command == "turn on the lights"

    def test_empty_command(self):
        req = JarvisRequest(command="")
        assert req.command == ""

    def test_missing_command_raises(self):
        with pytest.raises(ValidationError):
            JarvisRequest()

    def test_command_int_coerced_to_string(self):
        """Pydantic v2 coerces int to str for str fields."""
        req = JarvisRequest(command=123)
        assert req.command == "123"

    def test_extra_fields_ignored(self):
        req = JarvisRequest(command="hello", extra="data")
        assert req.command == "hello"
        assert not hasattr(req, "extra") or "extra" not in req.model_fields


class TestAuthRequest:
    """Tests for the AuthRequest model."""

    def test_valid_auth_request(self):
        req = AuthRequest(email="user@test.com", password="secret")
        assert req.email == "user@test.com"
        assert req.password == "secret"

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            AuthRequest(password="secret")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            AuthRequest(email="user@test.com")

    def test_missing_both_raises(self):
        with pytest.raises(ValidationError):
            AuthRequest()


class TestProtocolRunRequest:
    """Tests for the ProtocolRunRequest model."""

    def test_empty_request_is_valid(self):
        req = ProtocolRunRequest()
        assert req.protocol is None
        assert req.protocol_name is None
        assert req.arguments is None

    def test_with_protocol_name(self):
        req = ProtocolRunRequest(protocol_name="wake_up")
        assert req.protocol_name == "wake_up"

    def test_with_protocol_dict(self):
        proto = {"name": "test", "steps": []}
        req = ProtocolRunRequest(protocol=proto)
        assert req.protocol == proto

    def test_with_arguments(self):
        req = ProtocolRunRequest(
            protocol_name="test", arguments={"key": "value"}
        )
        assert req.arguments == {"key": "value"}

    def test_all_fields_populated(self):
        req = ProtocolRunRequest(
            protocol={"name": "inline"},
            protocol_name="named",
            arguments={"x": 1},
        )
        assert req.protocol is not None
        assert req.protocol_name == "named"
        assert req.arguments == {"x": 1}


class TestUserProfile:
    """Tests for the UserProfile model."""

    def test_all_defaults_none(self):
        profile = UserProfile()
        assert profile.name is None
        assert profile.interests is None
        assert profile.interaction_count is None

    def test_full_profile(self):
        profile = UserProfile(
            name="Alice",
            preferred_personality="friendly",
            interests=["coding", "music"],
            conversation_style="casual",
            humor_preference="dry",
            topics_of_interest=["AI", "Python"],
            language_preference="en",
            interaction_count=42,
            favorite_games=["chess"],
            last_seen="2026-03-09",
            required_resources=["calendar"],
        )
        assert profile.name == "Alice"
        assert profile.interests == ["coding", "music"]
        assert profile.interaction_count == 42
        assert profile.required_resources == ["calendar"]

    def test_partial_profile(self):
        profile = UserProfile(name="Bob", interests=["hiking"])
        assert profile.name == "Bob"
        assert profile.interests == ["hiking"]
        assert profile.conversation_style is None


class TestUserProfileUpdate:
    """Tests for UserProfileUpdate (inherits from UserProfile)."""

    def test_inherits_user_profile(self):
        assert issubclass(UserProfileUpdate, UserProfile)

    def test_empty_update(self):
        update = UserProfileUpdate()
        assert update.name is None

    def test_partial_update(self):
        update = UserProfileUpdate(name="Changed")
        assert update.name == "Changed"


class TestUserConfig:
    """Tests for the UserConfig model."""

    def test_all_defaults_none(self):
        config = UserConfig()
        assert config.openai_api_key is None
        assert config.anthropic_api_key is None
        assert config.calendar_api_url is None
        assert config.hue_bridge_ip is None
        assert config.hue_username is None

    def test_full_config(self):
        config = UserConfig(
            openai_api_key="sk-test",
            anthropic_api_key="ak-test",
            calendar_api_url="http://cal.local",
            hue_bridge_ip="192.168.1.100",
            hue_username="hue-user",
        )
        assert config.openai_api_key == "sk-test"
        assert config.hue_bridge_ip == "192.168.1.100"


class TestUserConfigUpdate:
    """Tests for UserConfigUpdate (inherits from UserConfig)."""

    def test_inherits_user_config(self):
        assert issubclass(UserConfigUpdate, UserConfig)

    def test_empty_update(self):
        update = UserConfigUpdate()
        assert update.openai_api_key is None
