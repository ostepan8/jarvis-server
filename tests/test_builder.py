"""Tests for jarvis.core.builder — JarvisBuilder fluent API and BuilderOptions."""

import os
import pytest
from unittest.mock import patch

from jarvis.core.builder import BuilderOptions, JarvisBuilder
from jarvis.core.config import JarvisConfig, FeatureFlags


# ---------------------------------------------------------------------------
# BuilderOptions
# ---------------------------------------------------------------------------
class TestBuilderOptions:
    """Tests for the BuilderOptions dataclass."""

    def test_default_values(self):
        opts = BuilderOptions()
        assert opts.load_protocol_directory is True
        assert opts.with_memory is True
        assert opts.with_nlu is True
        assert opts.with_calendar is True
        assert opts.with_chat is True
        assert opts.with_search is True

        assert opts.with_protocols is True
        assert opts.with_lights is True
        assert opts.with_roku is True
        assert opts.with_software is False  # Default off
        assert opts.with_night_agents is True

    def test_override_values(self):
        opts = BuilderOptions(
            with_memory=False,
            with_nlu=False,
            with_software=True,
        )
        assert opts.with_memory is False
        assert opts.with_nlu is False
        assert opts.with_software is True

    def test_all_off(self):
        opts = BuilderOptions(
            load_protocol_directory=False,
            with_memory=False,
            with_nlu=False,
            with_calendar=False,
            with_chat=False,
            with_search=False,

            with_protocols=False,
            with_lights=False,
            with_roku=False,
            with_software=False,
            with_night_agents=False,
        )
        for field_name in BuilderOptions.__dataclass_fields__:
            assert getattr(opts, field_name) is False


# ---------------------------------------------------------------------------
# JarvisBuilder — init / config handling
# ---------------------------------------------------------------------------
class TestJarvisBuilderInit:
    """Tests for JarvisBuilder initialization."""

    def test_init_with_config_object(self):
        cfg = JarvisConfig(ai_provider="anthropic", api_key="sk-test")
        builder = JarvisBuilder(cfg)
        assert builder._config is cfg
        assert builder._config.ai_provider == "anthropic"

    def test_init_with_dict(self):
        builder = JarvisBuilder({"ai_provider": "openai", "api_key": "sk-dict"})
        assert isinstance(builder._config, JarvisConfig)
        assert builder._config.ai_key_or_default() if hasattr(builder._config, 'api_key_or_default') else builder._config.api_key == "sk-dict"

    def test_init_creates_default_options(self):
        cfg = JarvisConfig()
        builder = JarvisBuilder(cfg)
        assert isinstance(builder._opts, BuilderOptions)
        # All defaults should be applied
        assert builder._opts.with_memory is True

    def test_dotenv_not_loaded_by_default(self):
        cfg = JarvisConfig()
        builder = JarvisBuilder(cfg)
        assert builder._dotenv_loaded is False


# ---------------------------------------------------------------------------
# JarvisBuilder — fluent toggles
# ---------------------------------------------------------------------------
class TestJarvisBuilderFluentAPI:
    """Tests for the fluent toggle methods on JarvisBuilder."""

    def _builder(self):
        return JarvisBuilder(JarvisConfig(api_key="test"))

    def test_protocols_enable(self):
        b = self._builder().protocols(True)
        assert b._opts.with_protocols is True
        assert isinstance(b, JarvisBuilder)

    def test_protocols_disable(self):
        b = self._builder().protocols(False)
        assert b._opts.with_protocols is False

    def test_protocol_directory_toggle(self):
        b = self._builder().protocol_directory(False)
        assert b._opts.load_protocol_directory is False

    def test_memory_toggle(self):
        b = self._builder().memory(False)
        assert b._opts.with_memory is False

    def test_nlu_toggle(self):
        b = self._builder().nlu(False)
        assert b._opts.with_nlu is False

    def test_calendar_toggle(self):
        b = self._builder().calendar(False)
        assert b._opts.with_calendar is False

    def test_chat_toggle(self):
        b = self._builder().chat(False)
        assert b._opts.with_chat is False

    def test_search_toggle(self):
        b = self._builder().search(False)
        assert b._opts.with_search is False

    def test_lights_toggle(self):
        b = self._builder().lights(False)
        assert b._opts.with_lights is False

    def test_roku_toggle(self):
        b = self._builder().roku(False)
        assert b._opts.with_roku is False

    def test_software_agent_toggle(self):
        b = self._builder().software_agent(True)
        assert b._opts.with_software is True

    def test_night_agents_toggle(self):
        b = self._builder().night_agents(False)
        assert b._opts.with_night_agents is False

    def test_chaining_multiple_toggles(self):
        b = (
            self._builder()
            .memory(False)
            .nlu(False)
            .calendar(False)
            .chat(False)
            .search(False)
            .protocols(False)
            .lights(False)
            .roku(False)
            .software_agent(True)
            .night_agents(False)
            .protocol_directory(False)
        )
        assert isinstance(b, JarvisBuilder)
        assert b._opts.with_memory is False
        assert b._opts.with_nlu is False
        assert b._opts.with_calendar is False
        assert b._opts.with_chat is False
        assert b._opts.with_search is False

        assert b._opts.with_protocols is False
        assert b._opts.with_lights is False
        assert b._opts.with_roku is False
        assert b._opts.with_software is True
        assert b._opts.with_night_agents is False
        assert b._opts.load_protocol_directory is False

    def test_toggle_default_param_is_true(self):
        """All toggles default to enabled=True when called without args."""
        b = self._builder()
        b._opts.with_memory = False
        b.memory()
        assert b._opts.with_memory is True

    def test_each_toggle_returns_same_instance(self):
        b = self._builder()
        assert b.memory(True) is b
        assert b.nlu(True) is b
        assert b.calendar(True) is b
        assert b.chat(True) is b
        assert b.search(True) is b

        assert b.protocols(True) is b
        assert b.lights(True) is b
        assert b.roku(True) is b
        assert b.software_agent(True) is b
        assert b.night_agents(True) is b
        assert b.protocol_directory(True) is b


# ---------------------------------------------------------------------------
# JarvisBuilder.from_env
# ---------------------------------------------------------------------------
_mock_dotenv = patch("jarvis.core.builder.load_dotenv")


class TestJarvisBuilderFromEnv:
    """Tests for the from_env static method.

    Note: from_env calls load_dotenv() which would read the project .env file
    and repopulate os.environ.  We mock load_dotenv in every test to isolate
    the environment to only what we explicitly set.
    """

    def test_from_env_with_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert isinstance(b, JarvisBuilder)
        assert b._config.api_key == "sk-env-test"
        assert b._dotenv_loaded is True

    def test_from_env_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True), \
             _mock_dotenv:
            with pytest.raises(ValueError, match="Missing API key"):
                JarvisBuilder.from_env()

    def test_from_env_custom_provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env(ai_provider="anthropic")
        assert b._config.ai_provider == "anthropic"

    def test_from_env_custom_api_key_env(self):
        with patch.dict(os.environ, {"MY_CUSTOM_KEY": "sk-custom"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env(api_key_env="MY_CUSTOM_KEY")
        assert b._config.api_key == "sk-custom"

    def test_from_env_custom_timeouts(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env(response_timeout=120.0, intent_timeout=10.0)
        assert b._config.response_timeout == 120.0
        assert b._config.intent_timeout == 10.0

    def test_from_env_with_hue_bridge_ip(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "PHILLIPS_HUE_BRIDGE_IP": "10.0.0.1"},
            clear=True,
        ), _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.hue_bridge_ip == "10.0.0.1"

    def test_from_env_without_hue_bridge_ip(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.hue_bridge_ip is None

    def test_from_env_with_lighting_backend(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "sk-test", "LIGHTING_BACKEND": "yeelight"},
            clear=True,
        ), _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.lighting_backend == "yeelight"

    def test_from_env_default_lighting_backend(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.lighting_backend == "phillips_hue"

    def test_from_env_with_yeelight_ips(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "YEELIGHT_BULB_IPS": "10.0.0.1, 10.0.0.2",
            },
            clear=True,
        ), _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.yeelight_bulb_ips == ["10.0.0.1", "10.0.0.2"]

    def test_from_env_empty_yeelight_ips(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.yeelight_bulb_ips is None

    def test_from_env_with_roku_config(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "ROKU_IP_ADDRESS": "192.168.1.50",
                "ROKU_USERNAME": "user",
                "ROKU_PASSWORD": "pass",
            },
            clear=True,
        ), _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.roku_ip_address == "192.168.1.50"
        assert b._config.roku_username == "user"
        assert b._config.roku_password == "pass"

    def test_from_env_with_hue_username(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "PHILLIPS_HUE_USERNAME": "hue-user",
            },
            clear=True,
        ), _mock_dotenv:
            b = JarvisBuilder.from_env()
        assert b._config.hue_username == "hue-user"

    def test_from_env_calendar_api_url(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), \
             _mock_dotenv:
            b = JarvisBuilder.from_env(calendar_api_url="http://cal:9090")
        assert b._config.calendar_api_url == "http://cal:9090"
