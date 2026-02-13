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
    raw = request.headers.get(WORKSPACE_HEADER) or request.headers.get(
        WORKSPACE_HEADER.lower()
    )
    return normalize_workspace_id(raw)
