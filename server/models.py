from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Dict, Optional, List


class JarvisRequest(BaseModel):
    command: str


class AuthRequest(BaseModel):
    email: str
    password: str


class ProtocolRunRequest(BaseModel):
    protocol: Optional[Dict[str, Any]] = None
    protocol_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


class UserProfile(BaseModel):
    name: Optional[str] = None
    preferred_personality: Optional[str] = None
    interests: Optional[List[str]] = None
    conversation_style: Optional[str] = None
    humor_preference: Optional[str] = None
    topics_of_interest: Optional[List[str]] = None
    language_preference: Optional[str] = None
    interaction_count: Optional[int] = None
    favorite_games: Optional[List[str]] = None
    last_seen: Optional[str] = None
    required_resources: Optional[List[str]] = None


class UserProfileUpdate(UserProfile):
    pass


class UserConfig(BaseModel):
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    calendar_api_url: Optional[str] = None
    hue_bridge_ip: Optional[str] = None
    hue_username: Optional[str] = None


class UserConfigUpdate(UserConfig):
    pass


# ------------------------------------------------------------------
# Self-improvement models
# ------------------------------------------------------------------


class DiscoveryRequest(BaseModel):
    types: Optional[List[str]] = None
    lookback_hours: int = 24


class TestRunRequest(BaseModel):
    test_files: Optional[List[str]] = None
    working_directory: Optional[str] = None
    timeout: int = 120


class TaskSubmitRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    relevant_files: List[str] = []


class CycleRequest(BaseModel):
    max_tasks: Optional[int] = None
    dry_run: bool = False
