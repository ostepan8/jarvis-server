from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class AgentProfile:
    """Generic profile information shared by all agents."""

    name: Optional[str] = None
    preferred_personality: str = "friendly"
    interests: List[str] = None
    conversation_style: str = "casual"
    humor_preference: str = "witty"
    topics_of_interest: List[str] = None
    language_preference: str = "english"
    interaction_count: int = 0
    favorite_games: List[str] = None
    last_seen: Optional[str] = None

    def __post_init__(self) -> None:
        if self.interests is None:
            self.interests = []
        if self.topics_of_interest is None:
            self.topics_of_interest = []
        if self.favorite_games is None:
            self.favorite_games = []
