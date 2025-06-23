from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class JarvisConfig:
    """Configuration options for :class:`~jarvis.main_jarvis.JarvisSystem`."""

    ai_provider: str = "openai"
    api_key: Optional[str] = None
    calendar_api_url: str = "http://localhost:8080"
    repo_path: str = "."
    response_timeout: float = 15.0
