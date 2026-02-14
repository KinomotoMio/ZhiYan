"""匿名工作区标识处理。"""

from __future__ import annotations

import re

from fastapi import HTTPException, Request

WORKSPACE_HEADER = "X-Workspace-Id"
DEFAULT_WORKSPACE_ID = "workspace-local-default"
_WORKSPACE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def normalize_workspace_id(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_WORKSPACE_ID
    if not _WORKSPACE_RE.match(value):
        raise HTTPException(status_code=400, detail="无效的 workspace_id")
    return value


def get_workspace_id_from_request(request: Request) -> str:
    # Future-friendly resolution order:
    # 1) auth-bound workspace from request.state (if available)
    # 2) explicit workspace header for local/dev mode
    from_state = _extract_workspace_id_from_state(request)
    if from_state:
        return normalize_workspace_id(from_state)

    raw = request.headers.get(WORKSPACE_HEADER) or request.headers.get(
        WORKSPACE_HEADER.lower()
    )
    return normalize_workspace_id(raw)


def _extract_workspace_id_from_state(request: Request) -> str | None:
    state = getattr(request, "state", None)
    if state is None:
        return None

    for key in ("workspace_id", "workspaceId"):
        value = getattr(state, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()

    auth_like = (
        getattr(state, "auth", None)
        or getattr(state, "auth_context", None)
        or getattr(state, "user", None)
        or getattr(state, "claims", None)
    )
    if auth_like is None:
        return None

    if isinstance(auth_like, dict):
        for key in ("workspace_id", "workspaceId", "ws_id"):
            value = auth_like.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    for key in ("workspace_id", "workspaceId", "ws_id"):
        value = getattr(auth_like, key, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
