from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class FeatureFlags:
    """Feature toggles controlling optional subsystems."""

    enable_weather: bool = True
    enable_lights: bool = True
    enable_canvas: bool = True
    enable_night_mode: bool = True


@dataclass
class JarvisConfig:
    """Configuration options for :class:`~jarvis.core.system.JarvisSystem`."""

    ai_provider: str = "openai"
    api_key: Optional[str] = None
    calendar_api_url: str = "http://localhost:8080"
    repo_path: str = "."
    response_timeout: float = 15.0
    intent_timeout: float = 5.0
    perf_tracking: bool = True
    memory_dir: Optional[str] = None
    weather_api_key: Optional[str] = None
    hue_bridge_ip: Optional[str] = None
    hue_username: Optional[str] = None
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
