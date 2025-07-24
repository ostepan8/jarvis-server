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
