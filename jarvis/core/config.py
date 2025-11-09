from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List
import os


@dataclass
class FeatureFlags:
    """Feature toggles controlling optional subsystems."""

    enable_weather: bool = True
    enable_lights: bool = True
    enable_canvas: bool = True
    enable_night_mode: bool = True
    enable_roku: bool = True


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
    weather_api_key: Optional[str] = None

    # Retry configuration for external service calls
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_exponential_base: float = 2.0

    # Circuit breaker configuration
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
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
    flags: FeatureFlags = field(default_factory=FeatureFlags)
    # perf_tracking: bool = os.getenv(
    #     "PERF_TRACE", os.getenv("PERF_TRACKING", "false")
    # ).lower() == "true"


@dataclass
class UserConfig:
    """Per-user configuration values stored in the database."""

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    calendar_api_url: Optional[str] = None
    weather_api_key: Optional[str] = None
    hue_bridge_ip: Optional[str] = None
    hue_username: Optional[str] = None
    roku_ip_address: Optional[str] = None
    roku_username: Optional[str] = None
    roku_password: Optional[str] = None
