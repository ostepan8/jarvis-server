from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import os


@dataclass
class FeatureFlags:
    """Feature toggles controlling optional subsystems."""

    enable_lights: bool = False
    enable_canvas: bool = True
    enable_night_mode: bool = True
    enable_roku: bool = True
    enable_todo: bool = True
    enable_coordinator: bool = True


@dataclass
class JarvisConfig:
    """Configuration options for :class:`~jarvis.core.system.JarvisSystem`."""

    ai_provider: str = "openai"
    api_key: Optional[str] = None
    calendar_api_url: str = "http://localhost:8080"
    response_timeout: float = 15.0
    intent_timeout: float = 5.0
    perf_tracking: bool = True
    record_network_methods: bool = field(
        default_factory=lambda: os.getenv("RECORD_NETWORK_METHODS", "false").lower()
        == "true"
    )
    memory_dir: Optional[str] = None

    # Retry configuration for external service calls
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_exponential_base: float = 2.0

    hue_bridge_ip: Optional[str] = field(
        default_factory=lambda: os.getenv("PHILLIPS_HUE_BRIDGE_IP")
    )
    hue_username: Optional[str] = field(
        default_factory=lambda: os.getenv("PHILLIPS_HUE_USERNAME")
    )
    lighting_backend: str = field(
        default_factory=lambda: os.getenv("LIGHTING_BACKEND", "phillips_hue")
    )
    yeelight_bulb_ips: Optional[List[str]] = field(
        default_factory=lambda: (
            [ip.strip() for ip in os.getenv("YEELIGHT_BULB_IPS", "").split(",")]
            if os.getenv("YEELIGHT_BULB_IPS", "").strip()
            else None
        )
    )
    roku_ip_address: Optional[str] = field(
        default_factory=lambda: os.getenv("ROKU_IP_ADDRESS")
    )
    roku_username: Optional[str] = field(
        default_factory=lambda: os.getenv("ROKU_USERNAME")
    )
    roku_password: Optional[str] = field(
        default_factory=lambda: os.getenv("ROKU_PASSWORD")
    )
    google_search_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GOOGLE_SEARCH_API_KEY")
    )
    google_search_engine_id: Optional[str] = field(
        default_factory=lambda: os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    )
    # Model configuration
    strong_model: str = "gpt-4o"
    weak_model: str = "gpt-4o-mini"

    # Network worker count
    worker_count: int = 3

    # Classification cache
    classification_cache_ttl: float = 120.0
    classification_cache_max_size: int = 500

    # Fast-path embedding classifier
    use_fast_classifier: bool = True

    flags: FeatureFlags = field(default_factory=FeatureFlags)


@dataclass
class UserConfig:
    """Per-user configuration values stored in the database."""

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    calendar_api_url: Optional[str] = None
    hue_bridge_ip: Optional[str] = None
    hue_username: Optional[str] = None
    roku_ip_address: Optional[str] = None
    roku_username: Optional[str] = None
    roku_password: Optional[str] = None


# ---------------------------------------------------------------------------
# Config persistence & profiles
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".jarvis"
CONFIG_FILE = CONFIG_DIR / "config.json"

FLAG_NAMES = [f.name for f in FeatureFlags.__dataclass_fields__.values()]

CONNECTION_KEYS = [
    "lighting_backend",
    "hue_bridge_ip",
    "hue_username",
    "roku_ip_address",
    "yeelight_bulb_ips",
]


@dataclass
class ConfigProfile:
    """A named configuration profile (e.g. 'Boston House')."""

    label: str
    feature_flags: dict = field(default_factory=dict)
    connections: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "feature_flags": dict(self.feature_flags),
            "connections": dict(self.connections),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConfigProfile:
        return cls(
            label=data.get("label", "Unnamed"),
            feature_flags=data.get("feature_flags", {}),
            connections=data.get("connections", {}),
        )

    @classmethod
    def from_config(cls, label: str, config: JarvisConfig) -> ConfigProfile:
        """Snapshot current JarvisConfig into a profile."""
        flags = {name: getattr(config.flags, name) for name in FLAG_NAMES}
        conns = {key: getattr(config, key, None) for key in CONNECTION_KEYS}
        return cls(label=label, feature_flags=flags, connections=conns)


def save_config(active_profile: str, profiles: dict[str, ConfigProfile]) -> None:
    """Persist config to ~/.jarvis/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "active_profile": active_profile,
        "profiles": {k: v.to_dict() for k, v in profiles.items()},
    }
    CONFIG_FILE.write_text(json.dumps(data, indent=2, default=str))


def load_config() -> tuple[str | None, dict[str, ConfigProfile]]:
    """Load config from disk. Returns (active_profile_key, profiles_dict)."""
    if not CONFIG_FILE.exists():
        return None, {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
        active = data.get("active_profile")
        profiles = {
            k: ConfigProfile.from_dict(v)
            for k, v in data.get("profiles", {}).items()
        }
        return active, profiles
    except (json.JSONDecodeError, KeyError):
        return None, {}


def apply_profile(config: JarvisConfig, profile: ConfigProfile) -> None:
    """Mutate a JarvisConfig with values from a ConfigProfile."""
    for flag_name, value in profile.feature_flags.items():
        if hasattr(config.flags, flag_name):
            setattr(config.flags, flag_name, value)
    for conn_key, value in profile.connections.items():
        if hasattr(config, conn_key) and value is not None:
            setattr(config, conn_key, value)
