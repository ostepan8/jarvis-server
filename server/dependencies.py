from __future__ import annotations

import sqlite3
from fastapi import Request, HTTPException
from jarvis import JarvisSystem


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
