from __future__ import annotations

import sqlite3
from fastapi import Request, HTTPException, Depends
from jarvis import JarvisSystem
from .auth import decode_token
from .database import get_user_agent_permissions, get_user_config
from jarvis import JarvisConfig


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


async def get_user_jarvis(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_auth_db),
) -> JarvisSystem:
    """Return a JarvisSystem configured for the current user."""
    systems = getattr(request.app.state, "user_systems", None)
    if systems is None:
        systems = {}
        request.app.state.user_systems = systems

    jarvis = systems.get(current_user["id"])
    if jarvis is not None:
        return jarvis

    base: JarvisSystem | None = getattr(request.app.state, "jarvis_system", None)
    if base is None:
        raise HTTPException(status_code=500, detail="Jarvis system not initialized")

    user_conf = get_user_config(db, current_user["id"])
    config = JarvisConfig(
        ai_provider=base.config.ai_provider,
        api_key=(
            user_conf.get("openai_api_key")
            or user_conf.get("anthropic_api_key")
            or base.config.api_key
        ),
        calendar_api_url=user_conf.get("calendar_api_url") or base.config.calendar_api_url,
        repo_path=base.config.repo_path,
        response_timeout=base.config.response_timeout,
        intent_timeout=base.config.intent_timeout,
        perf_tracking=base.config.perf_tracking,
        memory_dir=base.config.memory_dir,
        weather_api_key=user_conf.get("weather_api_key") or base.config.weather_api_key,
        hue_bridge_ip=user_conf.get("hue_bridge_ip") or base.config.hue_bridge_ip,
        hue_username=user_conf.get("hue_username") or base.config.hue_username,
    )

    jarvis = JarvisSystem(config)
    await jarvis.initialize()
    systems[current_user["id"]] = jarvis
    return jarvis
