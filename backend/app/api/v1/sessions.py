"""Session APIs — workspace-scoped session management."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.models.generation import CreateJobRequest, JobStatus, StageStatus
from app.models.session import (
    ChatRecord,
    LatestPresentationWriteRequest,
    PlanningState,
    SessionDetail,
    SessionSummary,
    SnapshotMeta,
)
from app.models.source import SourceMeta
from app.services.generation.job_factory import create_generation_job_record
from app.services.planning import (
    handle_planning_turn,
    normalize_planning_outline,
)
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str = "未命名会话"


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None
    status: str | None = None
    archived: bool | None = None


class SnapshotRequest(BaseModel):
    snapshot_label: str = "手动快照"
    presentation: dict | None = None


class SessionChatWriteRequest(BaseModel):
    role: str
    content: str
    model_meta: dict = Field(default_factory=dict)


class PlanningTurnRequest(BaseModel):
    message: str


class PlanningOutlineWriteRequest(BaseModel):
    outline: dict = Field(default_factory=dict)


class SessionPlanningDetail(BaseModel):
    planning_state: PlanningState | None = None
    planning_messages: list[ChatRecord] = Field(default_factory=list)


class PlanningConfirmResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str | None = None
    planning_state: PlanningState


def _ensure_session_id(value: str) -> str:
    sid = value.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    return sid


async def _assert_session_access(workspace_id: str, session_id: str) -> None:
    try:
        await session_store.get_session(workspace_id, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _filter_planning_messages(records: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for item in records:
        meta = item.get("model_meta") or {}
        phase = str(meta.get("phase") or "").strip()
        if phase == "planning":
            filtered.append(item)
    return filtered


async def _resolve_planning_state(
    workspace_id: str,
    session_id: str,
    latest_generation_job: dict | None = None,
) -> dict | None:
    state = await session_store.get_planning_state(workspace_id, session_id)
    if not state:
        return None
    latest = latest_generation_job or await session_store.get_latest_generation_job(
        workspace_id,
        session_id,
    )
    active_job_id = str(state.get("active_job_id") or "").strip()
    if not active_job_id or not latest or latest.get("job_id") != active_job_id:
        return state
    latest_status = str(latest.get("status") or "").strip()
    current_status = str(state.get("status") or "").strip()
    if latest_status == "completed" and current_status == "generating":
        return await session_store.save_planning_state(
            workspace_id=workspace_id,
            session_id=session_id,
            status="completed",
            active_job_id=active_job_id,
        )
    if latest_status in {"failed", "cancelled"} and current_status == "generating":
        return await session_store.save_planning_state(
            workspace_id=workspace_id,
            session_id=session_id,
            status="outline_ready",
            active_job_id=active_job_id,
        )
    return state


async def _ready_source_ids_and_names(workspace_id: str, session_id: str) -> tuple[list[str], list[str]]:
    sources = await session_store.list_sources(workspace_id, session_id)
    ready_sources = [source for source in sources if source.get("status") == "ready"]
    return (
        [str(source["id"]) for source in ready_sources if source.get("id")],
        [str(source["name"]) for source in ready_sources if source.get("name")],
    )


@router.post("", response_model=SessionSummary)
async def create_session(req: CreateSessionRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    session = await session_store.create_session(workspace_id, req.title or "未命名会话")
    return SessionSummary.model_validate(session)


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)
    sessions = await session_store.list_sessions(workspace_id, q=q, limit=limit, offset=offset)
    return [SessionSummary.model_validate(item) for item in sessions]


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    try:
        session = await session_store.get_session(workspace_id, sid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await session_store.touch_session(workspace_id, sid)
    sources = await session_store.list_sources(workspace_id, sid)
    chats = await session_store.list_chat_messages(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
    latest_generation_job = await session_store.get_latest_generation_job(workspace_id, sid)
    planning_state = await _resolve_planning_state(workspace_id, sid, latest_generation_job)
    return SessionDetail(
        session=SessionSummary.model_validate(session),
        sources=[SourceMeta.model_validate(item) for item in sources],
        chat_messages=[ChatRecord.model_validate(item) for item in chats],
        latest_presentation=latest,
        latest_generation_job=latest_generation_job,
        planning_state=PlanningState.model_validate(planning_state) if planning_state else None,
    )


@router.patch("/{session_id}", response_model=SessionSummary)
async def patch_session(session_id: str, req: UpdateSessionRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    try:
        session = await session_store.update_session(
            workspace_id,
            sid,
            title=req.title,
            is_pinned=req.is_pinned,
            status=req.status,
            archived=req.archived,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SessionSummary.model_validate(session)


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await session_store.delete_session(workspace_id, sid)
    return {"ok": True}


@router.get("/{session_id}/sources", response_model=list[SourceMeta])
async def list_session_sources(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    sources = await session_store.list_sources(workspace_id, sid)
    return [SourceMeta.model_validate(item) for item in sources]


@router.get("/{session_id}/sources/{source_id}/content")
async def get_session_source_content(session_id: str, source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        content = await session_store.get_source_content(workspace_id, sid, source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"content": content}


class LinkSourcesRequest(BaseModel):
    source_ids: list[str]


@router.post("/{session_id}/sources/link")
async def link_sources_to_session(session_id: str, req: LinkSourcesRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    for source_id in req.source_ids:
        try:
            await session_store.link_source_to_session(
                session_id=sid,
                source_id=source_id,
                workspace_id=workspace_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except PermissionError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True}


@router.delete("/{session_id}/sources/{source_id}/link")
async def unlink_source_from_session(session_id: str, source_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    await session_store.unlink_source_from_session(sid, source_id)
    return {"ok": True}


@router.get("/{session_id}/chat", response_model=list[ChatRecord])
async def list_session_chat(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    records = await session_store.list_chat_messages(workspace_id, sid, limit=300)
    return [ChatRecord.model_validate(item) for item in records]


@router.post("/{session_id}/chat", response_model=ChatRecord)
async def add_session_chat(session_id: str, req: SessionChatWriteRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        await session_store.add_chat_message(
            workspace_id=workspace_id,
            session_id=sid,
            role=req.role,
            content=req.content,
            model_meta=req.model_meta,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    records = await session_store.list_chat_messages(
        workspace_id, sid, limit=1, newest_first=True
    )
    if not records:
        raise HTTPException(status_code=500, detail="消息保存失败")
    return ChatRecord.model_validate(records[0])


@router.get("/{session_id}/planning", response_model=SessionPlanningDetail)
async def get_session_planning(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    planning_state = await _resolve_planning_state(workspace_id, sid)
    chats = await session_store.list_chat_messages(workspace_id, sid, limit=300)
    planning_messages = _filter_planning_messages(chats)
    return SessionPlanningDetail(
        planning_state=PlanningState.model_validate(planning_state) if planning_state else None,
        planning_messages=[ChatRecord.model_validate(item) for item in planning_messages],
    )


@router.post("/{session_id}/planning/turns")
async def create_planning_turn(session_id: str, req: PlanningTurnRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="缺少 planning 输入")

    async def event_stream():
        try:
            current_state = await _resolve_planning_state(workspace_id, sid)
            chats = await session_store.list_chat_messages(workspace_id, sid, limit=300)
            planning_messages = _filter_planning_messages(chats)
            ready_source_ids, ready_source_names = await _ready_source_ids_and_names(workspace_id, sid)
            current_outline = (
                dict(current_state.get("outline") or {})
                if current_state and isinstance(current_state.get("outline"), dict)
                else {}
            )
            current_source_ids = list(current_state.get("source_ids") or []) if current_state else []
            outline_stale = (
                bool(current_state.get("outline_stale")) if current_state else False
                or (bool(current_outline.get("items")) and current_source_ids != ready_source_ids)
            )
            if current_state and outline_stale and not bool(current_state.get("outline_stale")):
                current_state = await session_store.save_planning_state(
                    workspace_id=workspace_id,
                    session_id=sid,
                    status=str(current_state.get("status") or "outline_ready"),
                    outline_stale=True,
                )

            await session_store.add_chat_message(
                workspace_id=workspace_id,
                session_id=sid,
                role="user",
                content=message,
                model_meta={
                    "phase": "planning",
                    "message_kind": "user_turn",
                    "outline_version": int(current_state.get("outline_version") or 0) if current_state else 0,
                },
            )

            if ready_source_ids:
                content = await session_store.get_combined_source_content(
                    workspace_id,
                    sid,
                    ready_source_ids,
                )
            else:
                content = ""
            recent_messages = [
                {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")}
                for item in planning_messages[-8:]
            ]
            outcome = await handle_planning_turn(
                current_brief=current_state.get("brief") if current_state else None,
                current_outline=None if outline_stale else current_outline,
                user_message=message,
                recent_messages=recent_messages,
                content=content or message,
                source_names=ready_source_names,
                source_ids=ready_source_ids,
            )
            next_outline = outcome.outline or current_outline or {}
            next_outline_version = (
                int(current_state.get("outline_version") or 0) if current_state else 0
            ) + int(outcome.outline_version_increment or 0)
            next_state = await session_store.save_planning_state(
                workspace_id=workspace_id,
                session_id=sid,
                status=outcome.status,
                brief=outcome.brief,
                outline=next_outline if next_outline else {},
                outline_version=next_outline_version,
                source_ids=ready_source_ids,
                outline_stale=False if outcome.outline else outline_stale,
                active_job_id=str(current_state.get("active_job_id") or "") if current_state else None,
            )
            await session_store.add_chat_message(
                workspace_id=workspace_id,
                session_id=sid,
                role="assistant",
                content=outcome.assistant_message,
                model_meta={
                    "phase": "planning",
                    "message_kind": "assistant_reply",
                    "outline_version": next_state.get("outline_version", 0),
                },
            )
            text_payload = json.dumps(
                {"type": "text", "content": outcome.assistant_message},
                ensure_ascii=False,
            )
            yield f"data: {text_payload}\n\n"
            for event in outcome.events or []:
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            state_payload = json.dumps(
                {"type": "planning_state", "planning_state": next_state},
                ensure_ascii=False,
            )
            yield f"data: {state_payload}\n\n"
        except Exception as exc:
            error_payload = json.dumps(
                {"type": "error", "content": f"planning 处理失败: {exc}"},
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{session_id}/planning/outline", response_model=PlanningState)
async def update_session_planning_outline(
    session_id: str,
    req: PlanningOutlineWriteRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    current_state = await _resolve_planning_state(workspace_id, sid)
    normalized_outline = normalize_planning_outline(req.outline)
    ready_source_ids, _ = await _ready_source_ids_and_names(workspace_id, sid)
    updated = await session_store.save_planning_state(
        workspace_id=workspace_id,
        session_id=sid,
        status="outline_ready",
        brief=current_state.get("brief") if current_state else {},
        outline=normalized_outline,
        outline_version=(int(current_state.get("outline_version") or 0) if current_state else 0) + 1,
        source_ids=ready_source_ids,
        outline_stale=False,
        active_job_id=str(current_state.get("active_job_id") or "") if current_state else None,
    )
    return PlanningState.model_validate(updated)


@router.post("/{session_id}/planning/confirm", response_model=PlanningConfirmResponse)
async def confirm_session_planning(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    current_state = await _resolve_planning_state(workspace_id, sid)
    if not current_state:
        raise HTTPException(status_code=409, detail="当前会话还没有可确认的大纲")
    ready_source_ids, _ = await _ready_source_ids_and_names(workspace_id, sid)
    if list(current_state.get("source_ids") or []) != ready_source_ids and current_state.get("outline"):
        current_state = await session_store.save_planning_state(
            workspace_id=workspace_id,
            session_id=sid,
            status="outline_ready",
            outline_stale=True,
        )
    if bool(current_state.get("outline_stale")):
        raise HTTPException(status_code=409, detail="素材已变化，请先刷新大纲后再确认")
    approved_outline = normalize_planning_outline(current_state.get("outline") or {})
    if not approved_outline.get("items"):
        raise HTTPException(status_code=409, detail="当前会话还没有可确认的大纲")
    brief = dict(current_state.get("brief") or {})
    topic = str(brief.get("topic") or "").strip()
    if not topic:
        session = await session_store.get_session(workspace_id, sid)
        topic = str(session.get("title") or "新演示文稿")
    try:
        job, _ = await create_generation_job_record(
            workspace_id=workspace_id,
            req=CreateJobRequest(
                topic=topic,
                content="",
                session_id=sid,
                source_ids=ready_source_ids,
                template_id=None,
                num_pages=len(approved_outline.get("items") or []),
                approved_outline=approved_outline,
            ),
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 422
        if "已有演示稿" in message:
            status_code = 409
        raise HTTPException(status_code=status_code, detail=message) from exc
    next_state = await session_store.save_planning_state(
        workspace_id=workspace_id,
        session_id=sid,
        status="generating",
        brief=brief,
        outline=approved_outline,
        outline_version=int(current_state.get("outline_version") or 0),
        source_ids=ready_source_ids,
        outline_stale=False,
        active_job_id=job.job_id,
    )
    await session_store.add_chat_message(
        workspace_id=workspace_id,
        session_id=sid,
        role="assistant",
        content="大纲已确认，我已经开始生成 PPT。你可以先留在这里，或点击生成卡片进入编辑页面查看进度。",
        model_meta={
            "phase": "planning",
            "message_kind": "generation_started",
            "outline_version": next_state.get("outline_version", 0),
            "job_id": job.job_id,
        },
    )
    return PlanningConfirmResponse(
        job_id=job.job_id,
        status=JobStatus.RUNNING.value,
        current_stage=StageStatus.LAYOUT.value,
        planning_state=PlanningState.model_validate(next_state),
    )


@router.get("/{session_id}/presentations/latest")
async def get_latest_presentation(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无演示稿")
    return latest


@router.put("/{session_id}/presentations/latest", response_model=SnapshotMeta)
async def save_latest_presentation(
    session_id: str,
    req: LatestPresentationWriteRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    saved = await session_store.save_presentation(
        session_id=sid,
        payload=req.presentation,
        is_snapshot=False,
        snapshot_label=None,
    )
    return SnapshotMeta.model_validate(saved)


@router.post("/{session_id}/snapshots", response_model=SnapshotMeta)
async def create_snapshot(session_id: str, req: SnapshotRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        snapshot = await session_store.create_snapshot(
            workspace_id=workspace_id,
            session_id=sid,
            snapshot_label=req.snapshot_label,
            payload=req.presentation,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SnapshotMeta.model_validate(snapshot)
