from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Dict, Optional


class JarvisRequest(BaseModel):
    command: str


class AuthRequest(BaseModel):
    email: str
    password: str


class ProtocolRunRequest(BaseModel):
    protocol: Optional[Dict[str, Any]] = None
    protocol_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
