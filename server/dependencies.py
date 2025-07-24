from __future__ import annotations

import sqlite3
from fastapi import Request, HTTPException, Depends
from jarvis import JarvisSystem
from .auth import decode_token
from .database import get_user_agent_permissions


async def get_jarvis(request: Request) -> JarvisSystem:
    """Dependency to get the Jarvis system instance."""
    jarvis_system: JarvisSystem | None = getattr(
        request.app.state, "jarvis_system", None
    )
    if jarvis_system is None:
        raise HTTPException(status_code=500, detail="Jarvis system not initialized")
    return jarvis_system


def get_auth_db(request: Request) -> sqlite3.Connection:
    """Dependency to get the authentication database connection."""
    return request.app.state.auth_db


async def get_current_user(request: Request, db: sqlite3.Connection = Depends(get_auth_db)) -> dict:
    """Return the authenticated user from the Authorization header."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    email = decode_token(auth.split()[1])
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    cur = db.execute("SELECT id FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": row[0], "email": email}


async def get_user_allowed_agents(
    current_user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_auth_db),
    jarvis: JarvisSystem = Depends(get_jarvis),
) -> set[str]:
    mapping = get_user_agent_permissions(db, current_user["id"])
    if not mapping:
        # default allow all agents
        return set(jarvis.list_agents().keys())
    return {name for name, allowed in mapping.items() if allowed}
