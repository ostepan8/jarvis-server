from __future__ import annotations

from fastapi import APIRouter, Depends
from ..dependencies import (
    get_current_user,
    get_auth_db,
    get_user_allowed_agents,
    get_jarvis,
)
from ..database import (
    set_user_agent_permissions,
    get_user_agent_permissions,
    get_user_profile,
    set_user_profile,
    get_user_config,
    set_user_config,
)
from ..models import (
    UserProfile,
    UserProfileUpdate,
    UserConfig,
    UserConfigUpdate,
)
from jarvis import JarvisSystem

router = APIRouter()


@router.get("/me/agents")
async def get_my_agents(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
    jarvis: JarvisSystem = Depends(get_jarvis),
):
    perms = get_user_agent_permissions(db, current_user["id"])
    if not perms:
        agents = set(jarvis.list_agents().keys())
        return {"allowed": list(agents), "disallowed": []}
    allowed = [name for name, allowed in perms.items() if allowed]
    disallowed = [name for name, allowed in perms.items() if not allowed]
    return {"allowed": allowed, "disallowed": disallowed}


@router.post("/me/agents")
async def set_my_agents(
    body: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
):
    allowed = set(body.get("allowed", []))
    disallowed = set(body.get("disallowed", []))
    mapping = {name: True for name in allowed}
    mapping.update({name: False for name in disallowed})
    set_user_agent_permissions(db, current_user["id"], mapping)
    return {"success": True}


@router.get("/me/profile", response_model=UserProfile)
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
    jarvis: JarvisSystem = Depends(get_jarvis),
):
    profile = get_user_profile(db, current_user["id"])
    if profile:
        jarvis.user_profiles[current_user["id"]] = jarvis.user_profiles.get(
            current_user["id"],
            jarvis.chat_agent.profile.__class__(**profile),
        )
    return profile or {}


@router.post("/me/profile")
async def update_my_profile(
    body: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
    jarvis: JarvisSystem = Depends(get_jarvis),
):
    set_user_profile(db, current_user["id"], body.dict(exclude_unset=True))
    profile = get_user_profile(db, current_user["id"])
    jarvis.user_profiles[current_user["id"]] = jarvis.chat_agent.profile.__class__(
        **profile
    )
    return {"success": True}


@router.get("/me/config", response_model=UserConfig)
async def get_my_config(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
):
    config = get_user_config(db, current_user["id"])
    return config or {}


@router.post("/me/config")
async def update_my_config(
    body: UserConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_auth_db),
):
    set_user_config(db, current_user["id"], body.dict(exclude_unset=True))
    return {"success": True}
