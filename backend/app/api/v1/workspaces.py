"""Workspace APIs."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CurrentWorkspaceResponse(BaseModel):
    id: str
    label: str | None = None
    owner_type: str | None = None
    owner_id: str | None = None
    created_at: str | None = None
    last_seen_at: str | None = None


@router.get("/current", response_model=CurrentWorkspaceResponse)
async def get_current_workspace(request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    workspace = await session_store.get_workspace(workspace_id)
    if not workspace:
        # Fallback payload for defensive compatibility.
        return CurrentWorkspaceResponse(id=workspace_id)
    return CurrentWorkspaceResponse.model_validate(workspace)
