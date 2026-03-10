"""Tests for jarvis.core.config — JarvisConfig, FeatureFlags, ConfigProfile, and persistence."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from jarvis.core.config import (
    CONNECTION_KEYS,
    FLAG_NAMES,
    ConfigProfile,
    FeatureFlags,
    JarvisConfig,
    UserConfig,
    apply_profile,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# FeatureFlags
# ---------------------------------------------------------------------------
class TestFeatureFlags:
    """Tests for the FeatureFlags dataclass."""

    def test_default_values(self):
        flags = FeatureFlags()
        assert flags.enable_weather is True
        assert flags.enable_lights is False
        assert flags.enable_canvas is True
        assert flags.enable_night_mode is True
        assert flags.enable_roku is True

    def test_override_single_flag(self):
        flags = FeatureFlags(enable_weather=False)
        assert flags.enable_weather is False
        assert flags.enable_lights is False

    def test_all_flags_off(self):
        flags = FeatureFlags(
            enable_weather=False,
            enable_lights=False,
            enable_canvas=False,
            enable_night_mode=False,
            enable_roku=False,
        )
        assert flags.enable_weather is False
        assert flags.enable_lights is False
        assert flags.enable_canvas is False
        assert flags.enable_night_mode is False
        assert flags.enable_roku is False

    def test_flag_names_constant_matches_fields(self):
        flags = FeatureFlags()
        for name in FLAG_NAMES:
            assert hasattr(flags, name), f"FeatureFlags missing field: {name}"

    def test_flag_names_count(self):
        assert len(FLAG_NAMES) == len(FeatureFlags.__dataclass_fields__)


# ---------------------------------------------------------------------------
# JarvisConfig
# ---------------------------------------------------------------------------
class TestJarvisConfig:
    """Tests for the JarvisConfig dataclass."""

    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert cfg.ai_provider == "openai"
        assert cfg.api_key is None
        assert cfg.calendar_api_url == "http://localhost:8080"
        assert cfg.response_timeout == 15.0
        assert cfg.intent_timeout == 5.0
        assert cfg.perf_tracking is True
        assert cfg.memory_dir is None
        assert cfg.weather_api_key is None
        assert cfg.max_retries == 3
        assert cfg.retry_base_delay == 1.0
        assert cfg.retry_max_delay == 60.0
        assert cfg.retry_exponential_base == 2.0
        assert cfg.strong_model == "gpt-4o"
        assert cfg.weak_model == "gpt-4o-mini"
        assert cfg.worker_count == 3
        assert cfg.classification_cache_ttl == 120.0
        assert cfg.classification_cache_max_size == 500
        assert cfg.use_fast_classifier is True

    def test_custom_values(self):
        cfg = JarvisConfig(
            ai_provider="anthropic",
            api_key="sk-test",
            response_timeout=30.0,
            intent_timeout=10.0,
        )
        assert cfg.ai_provider == "anthropic"
        assert cfg.api_key == "sk-test"
        assert cfg.response_timeout == 30.0
        assert cfg.intent_timeout == 10.0

    def test_flags_default_to_feature_flags(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert isinstance(cfg.flags, FeatureFlags)
        assert cfg.flags.enable_weather is True

    def test_flags_custom(self):
        flags = FeatureFlags(enable_weather=False, enable_roku=False)
        cfg = JarvisConfig(flags=flags)
        assert cfg.flags.enable_weather is False
        assert cfg.flags.enable_roku is False

    def test_record_network_methods_default_false(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert cfg.record_network_methods is False

    def test_record_network_methods_from_env(self):
        with patch.dict(os.environ, {"RECORD_NETWORK_METHODS": "true"}, clear=True):
            cfg = JarvisConfig()
        assert cfg.record_network_methods is True

    def test_hue_bridge_ip_from_env(self):
        with patch.dict(os.environ, {"PHILLIPS_HUE_BRIDGE_IP": "192.168.1.10"}, clear=True):
            cfg = JarvisConfig()
        assert cfg.hue_bridge_ip == "192.168.1.10"

    def test_lighting_backend_default(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert cfg.lighting_backend == "phillips_hue"

    def test_lighting_backend_from_env(self):
        with patch.dict(os.environ, {"LIGHTING_BACKEND": "yeelight"}, clear=True):
            cfg = JarvisConfig()
        assert cfg.lighting_backend == "yeelight"

    def test_yeelight_bulb_ips_empty_env(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert cfg.yeelight_bulb_ips is None

    def test_yeelight_bulb_ips_from_env(self):
        with patch.dict(os.environ, {"YEELIGHT_BULB_IPS": "10.0.0.1, 10.0.0.2"}, clear=True):
            cfg = JarvisConfig()
        assert cfg.yeelight_bulb_ips == ["10.0.0.1", "10.0.0.2"]

    def test_roku_ip_from_env(self):
        with patch.dict(os.environ, {"ROKU_IP_ADDRESS": "192.168.1.50"}, clear=True):
            cfg = JarvisConfig()
        assert cfg.roku_ip_address == "192.168.1.50"

    def test_connection_keys_accessible(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        for key in CONNECTION_KEYS:
            assert hasattr(cfg, key), f"JarvisConfig missing connection key: {key}"


# ---------------------------------------------------------------------------
# UserConfig
# ---------------------------------------------------------------------------
class TestUserConfig:
    """Tests for the UserConfig dataclass."""

    def test_all_defaults_are_none(self):
        uc = UserConfig()
        assert uc.openai_api_key is None
        assert uc.anthropic_api_key is None
        assert uc.calendar_api_url is None
        assert uc.weather_api_key is None
        assert uc.hue_bridge_ip is None
        assert uc.hue_username is None
        assert uc.roku_ip_address is None
        assert uc.roku_username is None
        assert uc.roku_password is None

    def test_custom_values(self):
        uc = UserConfig(openai_api_key="sk-123", calendar_api_url="http://cal:9090")
        assert uc.openai_api_key == "sk-123"
        assert uc.calendar_api_url == "http://cal:9090"


# ---------------------------------------------------------------------------
# ConfigProfile
# ---------------------------------------------------------------------------
class TestConfigProfile:
    """Tests for the ConfigProfile dataclass."""

    def test_basic_construction(self):
        p = ConfigProfile(label="Home")
        assert p.label == "Home"
        assert p.feature_flags == {}
        assert p.connections == {}

    def test_construction_with_data(self):
        p = ConfigProfile(
            label="Office",
            feature_flags={"enable_weather": False},
            connections={"hue_bridge_ip": "10.0.0.1"},
        )
        assert p.feature_flags["enable_weather"] is False
        assert p.connections["hue_bridge_ip"] == "10.0.0.1"

    def test_to_dict(self):
        p = ConfigProfile(
            label="Lab",
            feature_flags={"enable_lights": True},
            connections={"roku_ip_address": "10.0.0.5"},
        )
        d = p.to_dict()
        assert d["label"] == "Lab"
        assert d["feature_flags"] == {"enable_lights": True}
        assert d["connections"] == {"roku_ip_address": "10.0.0.5"}

    def test_to_dict_returns_copies(self):
        """to_dict should return new dicts, not references."""
        p = ConfigProfile(label="X", feature_flags={"a": 1})
        d = p.to_dict()
        d["feature_flags"]["b"] = 2
        assert "b" not in p.feature_flags

    def test_from_dict(self):
        data = {
            "label": "Test",
            "feature_flags": {"enable_roku": False},
            "connections": {"hue_bridge_ip": "1.2.3.4"},
        }
        p = ConfigProfile.from_dict(data)
        assert p.label == "Test"
        assert p.feature_flags["enable_roku"] is False
        assert p.connections["hue_bridge_ip"] == "1.2.3.4"

    def test_from_dict_missing_label_defaults(self):
        p = ConfigProfile.from_dict({})
        assert p.label == "Unnamed"
        assert p.feature_flags == {}
        assert p.connections == {}

    def test_from_dict_partial_data(self):
        p = ConfigProfile.from_dict({"label": "Partial"})
        assert p.label == "Partial"
        assert p.feature_flags == {}
        assert p.connections == {}

    def test_roundtrip_to_dict_from_dict(self):
        original = ConfigProfile(
            label="Round",
            feature_flags={"enable_weather": True, "enable_lights": False},
            connections={"hue_bridge_ip": "192.168.1.1", "roku_ip_address": "10.0.0.1"},
        )
        restored = ConfigProfile.from_dict(original.to_dict())
        assert restored.label == original.label
        assert restored.feature_flags == original.feature_flags
        assert restored.connections == original.connections

    def test_from_config(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig(
                hue_bridge_ip="1.2.3.4",
                roku_ip_address="5.6.7.8",
            )
            cfg.flags.enable_weather = False
        p = ConfigProfile.from_config("snapshot", cfg)
        assert p.label == "snapshot"
        assert p.feature_flags["enable_weather"] is False
        assert p.connections["hue_bridge_ip"] == "1.2.3.4"
        assert p.connections["roku_ip_address"] == "5.6.7.8"

    def test_from_config_captures_all_flags(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        p = ConfigProfile.from_config("full", cfg)
        for flag_name in FLAG_NAMES:
            assert flag_name in p.feature_flags

    def test_from_config_captures_all_connection_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        p = ConfigProfile.from_config("full", cfg)
        for key in CONNECTION_KEYS:
            assert key in p.connections


# ---------------------------------------------------------------------------
# save_config / load_config
# ---------------------------------------------------------------------------
class TestConfigPersistence:
    """Tests for save_config and load_config."""

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".jarvis"
        config_file = config_dir / "config.json"
        monkeypatch.setattr("jarvis.core.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)

        profiles = {
            "home": ConfigProfile(
                label="Home",
                feature_flags={"enable_weather": True},
                connections={"hue_bridge_ip": "192.168.1.1"},
            ),
        }
        save_config("home", profiles)
        assert config_file.exists()

        active, loaded = load_config()
        assert active == "home"
        assert "home" in loaded
        assert loaded["home"].label == "Home"
        assert loaded["home"].feature_flags["enable_weather"] is True

    def test_load_config_no_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "nonexistent" / "config.json"
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)
        active, profiles = load_config()
        assert active is None
        assert profiles == {}

    def test_load_config_invalid_json(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("not valid json {{{")
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)
        active, profiles = load_config()
        assert active is None
        assert profiles == {}

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "new_dir" / ".jarvis"
        config_file = config_dir / "config.json"
        monkeypatch.setattr("jarvis.core.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)
        save_config("default", {})
        assert config_dir.exists()

    def test_save_multiple_profiles(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".jarvis"
        config_file = config_dir / "config.json"
        monkeypatch.setattr("jarvis.core.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)

        profiles = {
            "home": ConfigProfile(label="Home"),
            "office": ConfigProfile(label="Office"),
        }
        save_config("office", profiles)
        active, loaded = load_config()
        assert active == "office"
        assert len(loaded) == 2
        assert loaded["office"].label == "Office"

    def test_load_config_empty_profiles(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".jarvis"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"active_profile": None, "profiles": {}}))
        monkeypatch.setattr("jarvis.core.config.CONFIG_FILE", config_file)
        active, profiles = load_config()
        assert active is None
        assert profiles == {}


# ---------------------------------------------------------------------------
# apply_profile
# ---------------------------------------------------------------------------
class TestApplyProfile:
    """Tests for the apply_profile function."""

    def test_apply_feature_flags(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        assert cfg.flags.enable_weather is True

        profile = ConfigProfile(
            label="test",
            feature_flags={"enable_weather": False, "enable_roku": False},
        )
        apply_profile(cfg, profile)
        assert cfg.flags.enable_weather is False
        assert cfg.flags.enable_roku is False
        # Unchanged flags stay the same
        assert cfg.flags.enable_lights is False

    def test_apply_connections(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        profile = ConfigProfile(
            label="test",
            connections={"hue_bridge_ip": "10.0.0.1", "roku_ip_address": "10.0.0.2"},
        )
        apply_profile(cfg, profile)
        assert cfg.hue_bridge_ip == "10.0.0.1"
        assert cfg.roku_ip_address == "10.0.0.2"

    def test_apply_ignores_unknown_flags(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        profile = ConfigProfile(
            label="test",
            feature_flags={"nonexistent_flag": True},
        )
        # Should not raise
        apply_profile(cfg, profile)
        assert not hasattr(cfg.flags, "nonexistent_flag")

    def test_apply_ignores_unknown_connections(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        profile = ConfigProfile(
            label="test",
            connections={"unknown_connection": "value"},
        )
        apply_profile(cfg, profile)
        assert not hasattr(cfg, "unknown_connection")

    def test_apply_skips_none_connection_values(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig(hue_bridge_ip="original")
        profile = ConfigProfile(
            label="test",
            connections={"hue_bridge_ip": None},
        )
        apply_profile(cfg, profile)
        # None values should NOT overwrite existing values
        assert cfg.hue_bridge_ip == "original"

    def test_apply_empty_profile_no_change(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = JarvisConfig()
        original_weather = cfg.flags.enable_weather
        profile = ConfigProfile(label="empty")
        apply_profile(cfg, profile)
        assert cfg.flags.enable_weather == original_weather
