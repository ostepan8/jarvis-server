"""Tests for AI model management: ModelPreset, BUILTIN_PRESETS, ConfigProfile AI settings,
apply_profile AI settings, and models_dashboard helpers."""

import pytest

from jarvis.core.config import (
    BUILTIN_PRESETS,
    AI_SETTINGS_KEYS,
    ConfigProfile,
    JarvisConfig,
    ModelPreset,
    apply_profile,
)
from jarvis.cli.models_dashboard import (
    KNOWN_MODELS,
    _get_all_presets,
)


class TestModelPreset:
    """Tests for the ModelPreset dataclass."""

    def test_basic_construction(self):
        preset = ModelPreset(
            label="Test",
            provider="openai",
            strong_model="gpt-4o",
            weak_model="gpt-4o-mini",
        )
        assert preset.label == "Test"
        assert preset.provider == "openai"
        assert preset.strong_model == "gpt-4o"
        assert preset.weak_model == "gpt-4o-mini"

    def test_to_dict(self):
        preset = ModelPreset(
            label="Test",
            provider="anthropic",
            strong_model="claude-sonnet-4-6",
            weak_model="claude-haiku-4-5-20251001",
        )
        d = preset.to_dict()
        assert d == {
            "label": "Test",
            "provider": "anthropic",
            "strong_model": "claude-sonnet-4-6",
            "weak_model": "claude-haiku-4-5-20251001",
        }

    def test_from_dict(self):
        data = {
            "label": "Custom",
            "provider": "openai",
            "strong_model": "o1",
            "weak_model": "gpt-4o-mini",
        }
        preset = ModelPreset.from_dict(data)
        assert preset.label == "Custom"
        assert preset.provider == "openai"
        assert preset.strong_model == "o1"
        assert preset.weak_model == "gpt-4o-mini"

    def test_from_dict_defaults(self):
        preset = ModelPreset.from_dict({})
        assert preset.label == "Unnamed"
        assert preset.provider == "openai"
        assert preset.strong_model == "gpt-4o"
        assert preset.weak_model == "gpt-4o-mini"

    def test_roundtrip(self):
        original = ModelPreset(
            label="Roundtrip",
            provider="anthropic",
            strong_model="claude-opus-4-6",
            weak_model="claude-haiku-4-5-20251001",
        )
        restored = ModelPreset.from_dict(original.to_dict())
        assert restored.label == original.label
        assert restored.provider == original.provider
        assert restored.strong_model == original.strong_model
        assert restored.weak_model == original.weak_model


class TestBuiltinPresets:
    """Tests for the BUILTIN_PRESETS constant."""

    def test_builtin_presets_exist(self):
        assert len(BUILTIN_PRESETS) >= 5

    def test_builtin_preset_keys(self):
        expected = {"balanced", "full_power", "economy", "claude", "claude_haiku"}
        assert expected.issubset(set(BUILTIN_PRESETS.keys()))

    def test_each_preset_has_required_fields(self):
        for key, preset in BUILTIN_PRESETS.items():
            assert preset.label, f"{key} missing label"
            assert preset.provider, f"{key} missing provider"
            assert preset.strong_model, f"{key} missing strong_model"
            assert preset.weak_model, f"{key} missing weak_model"

    def test_provider_values_valid(self):
        valid_providers = {"openai", "anthropic"}
        for key, preset in BUILTIN_PRESETS.items():
            assert preset.provider in valid_providers, f"{key} has invalid provider '{preset.provider}'"

    def test_balanced_preset_defaults(self):
        p = BUILTIN_PRESETS["balanced"]
        assert p.provider == "openai"
        assert p.strong_model == "gpt-4o"
        assert p.weak_model == "gpt-4o-mini"

    def test_economy_uses_same_model(self):
        p = BUILTIN_PRESETS["economy"]
        assert p.strong_model == p.weak_model == "gpt-4o-mini"

    def test_full_power_uses_same_model(self):
        p = BUILTIN_PRESETS["full_power"]
        assert p.strong_model == p.weak_model == "gpt-4o"


class TestConfigProfileAISettings:
    """Tests for ai_settings, model_presets, and active_preset in ConfigProfile."""

    def test_default_ai_settings_empty(self):
        profile = ConfigProfile(label="Test")
        assert profile.ai_settings == {}

    def test_default_model_presets_empty(self):
        profile = ConfigProfile(label="Test")
        assert profile.model_presets == {}

    def test_default_active_preset_none(self):
        profile = ConfigProfile(label="Test")
        assert profile.active_preset is None

    def test_to_dict_includes_ai_settings(self):
        profile = ConfigProfile(
            label="Test",
            ai_settings={"ai_provider": "anthropic", "strong_model": "claude-sonnet-4-6", "weak_model": "claude-haiku-4-5-20251001"},
            model_presets={"custom": {"label": "Custom", "provider": "openai", "strong_model": "o1", "weak_model": "gpt-4o-mini"}},
            active_preset="custom",
        )
        d = profile.to_dict()
        assert d["ai_settings"] == {"ai_provider": "anthropic", "strong_model": "claude-sonnet-4-6", "weak_model": "claude-haiku-4-5-20251001"}
        assert d["model_presets"] == {"custom": {"label": "Custom", "provider": "openai", "strong_model": "o1", "weak_model": "gpt-4o-mini"}}
        assert d["active_preset"] == "custom"

    def test_from_dict_with_ai_settings(self):
        data = {
            "label": "Test",
            "feature_flags": {},
            "connections": {},
            "ai_settings": {"ai_provider": "anthropic", "strong_model": "claude-opus-4-6"},
            "model_presets": {"fast": {"label": "Fast", "provider": "openai", "strong_model": "gpt-4o-mini", "weak_model": "gpt-4o-mini"}},
            "active_preset": "fast",
        }
        profile = ConfigProfile.from_dict(data)
        assert profile.ai_settings == {"ai_provider": "anthropic", "strong_model": "claude-opus-4-6"}
        assert "fast" in profile.model_presets
        assert profile.active_preset == "fast"

    def test_from_dict_without_ai_settings_backwards_compat(self):
        data = {"label": "Old", "feature_flags": {"enable_lights": True}, "connections": {}}
        profile = ConfigProfile.from_dict(data)
        assert profile.ai_settings == {}
        assert profile.model_presets == {}
        assert profile.active_preset is None

    def test_from_config_captures_ai_settings(self):
        config = JarvisConfig(
            ai_provider="anthropic",
            strong_model="claude-sonnet-4-6",
            weak_model="claude-haiku-4-5-20251001",
        )
        profile = ConfigProfile.from_config("Test", config)
        assert profile.ai_settings == {
            "ai_provider": "anthropic",
            "strong_model": "claude-sonnet-4-6",
            "weak_model": "claude-haiku-4-5-20251001",
        }

    def test_roundtrip_with_ai_settings(self):
        original = ConfigProfile(
            label="Roundtrip",
            ai_settings={"ai_provider": "openai", "strong_model": "o1", "weak_model": "gpt-4o-mini"},
            model_presets={"mine": {"label": "Mine", "provider": "openai", "strong_model": "o1", "weak_model": "gpt-4o-mini"}},
            active_preset="mine",
        )
        restored = ConfigProfile.from_dict(original.to_dict())
        assert restored.ai_settings == original.ai_settings
        assert restored.model_presets == original.model_presets
        assert restored.active_preset == original.active_preset


class TestApplyProfileAISettings:
    """Tests for apply_profile with ai_settings."""

    def test_apply_sets_ai_provider(self):
        config = JarvisConfig()
        profile = ConfigProfile(label="Test", ai_settings={"ai_provider": "anthropic"})
        apply_profile(config, profile)
        assert config.ai_provider == "anthropic"

    def test_apply_sets_strong_model(self):
        config = JarvisConfig()
        profile = ConfigProfile(label="Test", ai_settings={"strong_model": "o1"})
        apply_profile(config, profile)
        assert config.strong_model == "o1"

    def test_apply_sets_weak_model(self):
        config = JarvisConfig()
        profile = ConfigProfile(label="Test", ai_settings={"weak_model": "gpt-3.5-turbo"})
        apply_profile(config, profile)
        assert config.weak_model == "gpt-3.5-turbo"

    def test_apply_empty_ai_settings_no_change(self):
        config = JarvisConfig()
        original_provider = config.ai_provider
        original_strong = config.strong_model
        original_weak = config.weak_model
        profile = ConfigProfile(label="Test", ai_settings={})
        apply_profile(config, profile)
        assert config.ai_provider == original_provider
        assert config.strong_model == original_strong
        assert config.weak_model == original_weak

    def test_apply_all_ai_settings(self):
        config = JarvisConfig()
        profile = ConfigProfile(
            label="Test",
            ai_settings={
                "ai_provider": "anthropic",
                "strong_model": "claude-opus-4-6",
                "weak_model": "claude-haiku-4-5-20251001",
            },
        )
        apply_profile(config, profile)
        assert config.ai_provider == "anthropic"
        assert config.strong_model == "claude-opus-4-6"
        assert config.weak_model == "claude-haiku-4-5-20251001"


class TestModelsDashboardHelpers:
    """Tests for models_dashboard helper functions."""

    def test_known_models_has_openai(self):
        assert "openai" in KNOWN_MODELS
        assert len(KNOWN_MODELS["openai"]) > 0

    def test_known_models_has_anthropic(self):
        assert "anthropic" in KNOWN_MODELS
        assert len(KNOWN_MODELS["anthropic"]) > 0

    def test_known_models_entries_are_tuples(self):
        for provider, models in KNOWN_MODELS.items():
            for entry in models:
                assert isinstance(entry, tuple), f"{provider} has non-tuple entry"
                assert len(entry) == 2, f"{provider} entry has wrong length"

    def test_get_all_presets_includes_builtins(self):
        profile = ConfigProfile(label="Test")
        presets = _get_all_presets(profile)
        builtin_keys = {key for key, _, is_custom in presets if not is_custom}
        assert builtin_keys == set(BUILTIN_PRESETS.keys())

    def test_get_all_presets_includes_custom(self):
        profile = ConfigProfile(
            label="Test",
            model_presets={
                "my_preset": {"label": "My Preset", "provider": "openai", "strong_model": "o1", "weak_model": "gpt-4o-mini"},
            },
        )
        presets = _get_all_presets(profile)
        custom = [(key, p, c) for key, p, c in presets if c]
        assert len(custom) == 1
        assert custom[0][0] == "my_preset"
        assert custom[0][1].label == "My Preset"

    def test_get_all_presets_empty_custom(self):
        profile = ConfigProfile(label="Test")
        presets = _get_all_presets(profile)
        assert len(presets) == len(BUILTIN_PRESETS)
        assert all(not is_custom for _, _, is_custom in presets)

    def test_ai_settings_keys_constant(self):
        assert AI_SETTINGS_KEYS == ["ai_provider", "strong_model", "weak_model"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
