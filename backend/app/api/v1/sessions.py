"""Session APIs — workspace-scoped session management."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.generation import (
    AcceptOutlineRequest,
    CreateJobRequest,
    CreateJobResponse,
    EventType,
    FixApplyRequest,
    FixPreviewRequest,
    GenerationEvent,
    GenerationJob,
    JobActionResponse,
    JobStatus,
    PresentationOutputMode,
    StageStatus,
    now_iso,
)
from app.models.session import (
    ChatRecord,
    LatestPresentationWriteRequest,
    PlanningState,
    SessionDetail,
    SessionSummary,
    SnapshotMeta,
)
from app.models.source import SourceMeta
from app.services.generation import event_bus, generation_runner, job_store
from app.services.generation.job_factory import create_generation_job_record
from app.services.planning import (
    ensure_planning_opening,
    handle_planning_turn,
    normalize_planning_outline,
)
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request
from app.services.slidev import build_slidev_spa, prepare_slidev_deck_artifact

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


def _slidev_outline_items_from_payload(
    slidev_deck: dict[str, object] | None,
    presentation: dict[str, object],
) -> list[dict[str, object]]:
    if isinstance(slidev_deck, dict):
        raw_meta = slidev_deck.get("meta")
        if isinstance(raw_meta, dict):
            raw_slides = raw_meta.get("slides")
            if isinstance(raw_slides, list):
                items: list[dict[str, object]] = []
                for index, slide in enumerate(raw_slides, start=1):
                    if not isinstance(slide, dict):
                        continue
                    items.append(
                        {
                            "slide_number": index,
                            "title": str(slide.get("title") or f"第 {index} 页"),
                            "suggested_slide_role": str(slide.get("role") or "narrative"),
                            "objective": "",
                        }
                    )
                if items:
                    return items
    raw_slides = presentation.get("slides")
    if not isinstance(raw_slides, list):
        return []
    items = []
    for index, slide in enumerate(raw_slides, start=1):
        if not isinstance(slide, dict):
            continue
        content_data = slide.get("contentData")
        title = ""
        if isinstance(content_data, dict):
            title = str(content_data.get("title") or "")
        items.append(
            {
                "slide_number": index,
                "title": title or f"第 {index} 页",
                "suggested_slide_role": str(
                    (content_data or {}).get("role") if isinstance(content_data, dict) else "narrative"
                )
                or "narrative",
                "objective": "",
            }
        )
    return items


def _resolve_slidev_build_asset(build_root: str, asset_path: str) -> Path:
    root = Path(build_root).resolve()
    candidate = (root / asset_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=404, detail="Slidev 构建资源不存在")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Slidev 构建资源不存在")
    return candidate


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


class PlanningConfirmRequest(BaseModel):
    output_mode: PresentationOutputMode | None = None
    skill_id: str | None = None


class SessionShareLinkResponse(BaseModel):
    token: str
    share_path: str
    share_url: str
    created_at: str


def _ensure_session_id(value: str) -> str:
    sid = value.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    return sid


def _build_share_path(token: str) -> str:
    return f"/share/{quote(token, safe='')}"


def _build_share_url(token: str) -> str:
    base = settings.public_app_url.rstrip("/")
    return f"{base}{_build_share_path(token)}"


async def _get_generation_job_for_session(
    workspace_id: str,
    session_id: str,
    job_id: str,
) -> GenerationJob:
    await _assert_session_access(workspace_id, session_id)
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.request.session_id != session_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
        state = await ensure_planning_opening(workspace_id=workspace_id, session_id=session_id)
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
    if latest_status in {"artifact_ready", "completed", "render_failed"} and current_status == "generating":
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
    latest_generation_job = await session_store.get_latest_generation_job(workspace_id, sid)
    planning_state = await _resolve_planning_state(workspace_id, sid, latest_generation_job)
    chats = await session_store.list_chat_messages(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
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
            ready_source_ids, _ = await _ready_source_ids_and_names(workspace_id, sid)
            current_outline = (
                dict(current_state.get("outline") or {})
                if current_state and isinstance(current_state.get("outline"), dict)
                else {}
            )
            outcome = await handle_planning_turn(
                workspace_id=workspace_id,
                session_id=sid,
                user_message=message,
            )
            refreshed_state = await _resolve_planning_state(workspace_id, sid)
            next_outline = outcome.outline or current_outline or {}
            expected_outline_version = (
                int(current_state.get("outline_version") or 0) if current_state else 0
            ) + int(outcome.outline_version_increment or 0)
            expected_output_mode = str(outcome.output_mode or current_state.get("output_mode") or "slidev")
            expected_mode_selection_source = str(
                outcome.mode_selection_source or current_state.get("mode_selection_source") or "default"
            )
            needs_fallback_save = (
                refreshed_state is None
                or str(refreshed_state.get("status") or "") != str(outcome.status or "")
                or int(refreshed_state.get("outline_version") or 0) < expected_outline_version
                or str(refreshed_state.get("output_mode") or "slidev") != expected_output_mode
                or str(refreshed_state.get("mode_selection_source") or "default")
                != expected_mode_selection_source
            )
            if needs_fallback_save:
                await session_store.add_chat_message(
                    workspace_id=workspace_id,
                    session_id=sid,
                    role="user",
                    content=message,
                    model_meta={
                        "phase": "planning",
                        "message_kind": "user_turn",
                        "outline_version": int(current_state.get("outline_version") or 0)
                        if current_state
                        else 0,
                    },
                )
                next_state = await session_store.save_planning_state(
                    workspace_id=workspace_id,
                    session_id=sid,
                    status=outcome.status,
                    output_mode=outcome.output_mode,
                    mode_selection_source=outcome.mode_selection_source,
                    brief=outcome.brief,
                    outline=next_outline if next_outline else {},
                    outline_version=expected_outline_version,
                    source_ids=ready_source_ids,
                    outline_stale=False if outcome.outline else None,
                    assistant_status=outcome.assistant_status,
                    topic_suggestions=outcome.topic_suggestions or None,
                )
                if outcome.assistant_message:
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
            else:
                next_state = refreshed_state
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
async def confirm_session_planning(
    session_id: str,
    request: Request,
    req: PlanningConfirmRequest | None = None,
):
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
    confirm_req = req or PlanningConfirmRequest()
    effective_output_mode_raw = (
        confirm_req.output_mode.value
        if confirm_req.output_mode is not None
        else str(current_state.get("output_mode") or PresentationOutputMode.SLIDEV.value)
    )
    try:
        effective_output_mode = PresentationOutputMode(effective_output_mode_raw)
    except ValueError:
        effective_output_mode = PresentationOutputMode.SLIDEV
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
                content=str(brief.get("extra_requirements") or ""),
                session_id=sid,
                source_ids=ready_source_ids,
                template_id=None,
                num_pages=len(approved_outline.get("items") or []),
                approved_outline=approved_outline,
                output_mode=effective_output_mode,
                skill_id=confirm_req.skill_id,
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


@router.post("/{session_id}/generation/jobs", response_model=CreateJobResponse)
async def create_session_generation_job(
    session_id: str,
    req: CreateJobRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    try:
        job, _ = await create_generation_job_record(
            workspace_id=workspace_id,
            req=req.model_copy(update={"session_id": sid}),
            session_store_override=session_store,
            job_store_override=job_store,
            generation_runner_override=generation_runner,
        )
    except ValueError as e:
        message = str(e)
        status_code = 422
        if "已有演示稿" in message:
            status_code = 409
        elif "不存在" in message:
            status_code = 404
        raise HTTPException(status_code=status_code, detail=message) from e

    return CreateJobResponse(
        job_id=job.job_id,
        session_id=sid,
        status=job.status,
        created_at=job.created_at,
        event_stream_url=f"/api/v1/sessions/{sid}/generation/jobs/{job.job_id}/events",
        skill_id=job.request.skill_id,
        run_id=job.run_metadata.run_id if job.run_metadata else None,
        run_metadata=job.run_metadata,
    )


@router.get("/{session_id}/generation/jobs/{job_id}", response_model=GenerationJob)
async def get_session_generation_job(
    session_id: str,
    job_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    return await _get_generation_job_for_session(workspace_id, sid, job_id)


@router.post("/{session_id}/generation/jobs/{job_id}/outline/accept", response_model=JobActionResponse)
async def accept_session_generation_outline(
    session_id: str,
    job_id: str,
    req: AcceptOutlineRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    job = await _get_generation_job_for_session(workspace_id, sid, job_id)

    if job.status not in {JobStatus.WAITING_OUTLINE_REVIEW, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail=f"当前状态不允许确认大纲: {job.status}")

    if req.outline is not None:
        job.outline = req.outline
    if req.output_mode is not None:
        job.output_mode = req.output_mode
        job.request.output_mode = req.output_mode
    job.outline_accepted = True
    job.updated_at = now_iso()
    await job_store.save_job(job)

    await generation_runner.start_job(job_id, from_stage=StageStatus.LAYOUT)

    return JobActionResponse(job_id=job.job_id, status=job.status, current_stage=job.current_stage)


@router.post("/{session_id}/generation/jobs/{job_id}/run", response_model=JobActionResponse)
async def run_session_generation_job(
    session_id: str,
    job_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    job = await _get_generation_job_for_session(workspace_id, sid, job_id)

    if job.mode.value == "review_outline" and not job.outline_accepted:
        raise HTTPException(status_code=409, detail="请先确认大纲后再继续")
    if job.status == JobStatus.WAITING_FIX_REVIEW:
        raise HTTPException(status_code=409, detail="当前任务正在等待修复决策，请先完成 fix 决策")

    started = await generation_runner.start_job(job_id)
    if not started and job.status == JobStatus.RUNNING:
        return JobActionResponse(job_id=job.job_id, status=job.status, current_stage=job.current_stage)

    refreshed = await _get_generation_job_for_session(workspace_id, sid, job_id)
    return JobActionResponse(
        job_id=refreshed.job_id,
        status=refreshed.status,
        current_stage=refreshed.current_stage,
    )


@router.post("/{session_id}/generation/jobs/{job_id}/fix/preview", response_model=GenerationJob)
async def preview_session_generation_fix(
    session_id: str,
    job_id: str,
    req: FixPreviewRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _get_generation_job_for_session(workspace_id, sid, job_id)
    try:
        return await generation_runner.preview_fix(job_id, slide_ids=req.slide_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{session_id}/generation/jobs/{job_id}/fix/apply", response_model=GenerationJob)
async def apply_session_generation_fix(
    session_id: str,
    job_id: str,
    req: FixApplyRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _get_generation_job_for_session(workspace_id, sid, job_id)
    try:
        return await generation_runner.apply_fix(job_id, slide_ids=req.slide_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{session_id}/generation/jobs/{job_id}/fix/skip", response_model=GenerationJob)
async def skip_session_generation_fix(
    session_id: str,
    job_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _get_generation_job_for_session(workspace_id, sid, job_id)
    try:
        return await generation_runner.skip_fix(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/{session_id}/generation/jobs/{job_id}/cancel", response_model=JobActionResponse)
async def cancel_session_generation_job(
    session_id: str,
    job_id: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _get_generation_job_for_session(workspace_id, sid, job_id)

    await generation_runner.cancel_job(job_id)
    refreshed = await _get_generation_job_for_session(workspace_id, sid, job_id)
    return JobActionResponse(
        job_id=refreshed.job_id,
        status=refreshed.status,
        current_stage=refreshed.current_stage,
    )


@router.get("/{session_id}/generation/jobs/{job_id}/events")
async def stream_session_generation_job_events(
    session_id: str,
    job_id: str,
    request: Request,
    after_seq: int = Query(default=0, ge=0),
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _get_generation_job_for_session(workspace_id, sid, job_id)

    heartbeat = max(0.1, settings.sse_heartbeat_seconds)
    terminal_events = {
        EventType.JOB_COMPLETED,
        EventType.JOB_FAILED,
        EventType.JOB_CANCELLED,
        EventType.JOB_WAITING_FIX_REVIEW,
    }

    async def event_generator():
        queue = await event_bus.subscribe(job_id)
        try:
            replay = await job_store.list_events(job_id)
            last_seq = max(0, after_seq)
            terminal_seen = False

            for event in replay:
                if event.seq <= after_seq:
                    continue
                last_seq = max(last_seq, event.seq)
                yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
                if event.type in terminal_events:
                    terminal_seen = True

            if terminal_seen:
                yield "data: [DONE]\n\n"
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    hb = GenerationEvent(
                        seq=last_seq,
                        type=EventType.HEARTBEAT,
                        job_id=job_id,
                        message="heartbeat",
                    )
                    yield f"data: {json.dumps(hb.model_dump(mode='json'), ensure_ascii=False)}\n\n"
                    continue

                if event.seq <= last_seq:
                    continue

                last_seq = max(last_seq, event.seq)
                yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

                if event.type in terminal_events:
                    yield "data: [DONE]\n\n"
                    break
        except asyncio.CancelledError:
            raise
        finally:
            with suppress(Exception):
                await event_bus.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@router.get("/{session_id}/presentations/latest/html")
async def get_latest_presentation_html(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_html_deck(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无 HTML 演示稿")
    html, _meta = latest
    return PlainTextResponse(content=html, media_type="text/html")


@router.get("/{session_id}/presentations/latest/html/meta")
async def get_latest_presentation_html_meta(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_html_deck(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无 HTML 演示稿")
    _html, meta = latest
    return JSONResponse(content=meta)

@router.get("/{session_id}/presentations/latest/slidev")
async def get_latest_presentation_slidev(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_presentation(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无演示稿")
    if latest.get("output_mode") != "slidev":
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 演示稿")
    deck = await session_store.get_latest_slidev_deck(workspace_id, sid)
    build = await session_store.get_latest_slidev_build(workspace_id, sid)
    if not deck:
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 演示稿")
    markdown, meta = deck
    return {
        "markdown": markdown,
        "meta": meta,
        "build_url": f"/api/v1/sessions/{sid}/presentations/latest/slidev/build" if build else None,
        "artifact_status": latest.get("artifact_status"),
        "render_status": latest.get("render_status"),
        "render_error": latest.get("render_error"),
        "artifact_available": latest.get("artifact_available"),
        "render_available": latest.get("render_available"),
        "assets": latest.get("artifacts", {}),
    }


@router.get("/{session_id}/presentations/latest/slidev/markdown")
async def get_latest_presentation_slidev_markdown(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_slidev_deck(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 演示稿")
    markdown, _meta = latest
    return PlainTextResponse(content=markdown, media_type="text/markdown")


@router.get("/{session_id}/presentations/latest/slidev/meta")
async def get_latest_presentation_slidev_meta(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    latest = await session_store.get_latest_slidev_deck(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 演示稿")
    _markdown, meta = latest
    return JSONResponse(content=meta)


@router.get("/{session_id}/presentations/latest/slidev/build")
async def get_latest_presentation_slidev_build(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    build = await session_store.get_latest_slidev_build(workspace_id, sid)
    if not build:
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 构建产物")
    entry_path = _resolve_slidev_build_asset(str(build.get("build_root") or ""), "index.html")
    return FileResponse(entry_path, media_type="text/html")


@router.get("/{session_id}/presentations/latest/slidev/build/{asset_path:path}")
async def get_latest_presentation_slidev_build_asset(
    session_id: str,
    asset_path: str,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    build = await session_store.get_latest_slidev_build(workspace_id, sid)
    if not build:
        raise HTTPException(status_code=404, detail="当前会话暂无 Slidev 构建产物")
    target = _resolve_slidev_build_asset(str(build.get("build_root") or ""), asset_path)
    return FileResponse(target)


@router.post("/{session_id}/share-link", response_model=SessionShareLinkResponse)
async def create_or_get_session_share_link(session_id: str, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)

    latest = await session_store.get_latest_presentation(workspace_id, sid)
    if not latest:
        raise HTTPException(status_code=404, detail="当前会话暂无可分享的演示稿")

    output_mode = str(latest.get("output_mode") or "structured")
    if output_mode == "slidev":
        raise HTTPException(status_code=422, detail="当前暂不支持分享 Slidev 演示稿")
    if output_mode == "html":
        html_deck = await session_store.get_latest_html_deck(workspace_id, sid)
        if not html_deck:
            raise HTTPException(status_code=404, detail="当前会话暂无可分享的 HTML 演示稿")

    share = await session_store.create_or_get_share_link(workspace_id, sid)
    token = str(share["token"])
    return SessionShareLinkResponse(
        token=token,
        share_path=_build_share_path(token),
        share_url=_build_share_url(token),
        created_at=str(share["created_at"]),
    )


@router.put("/{session_id}/presentations/latest", response_model=SnapshotMeta)
async def save_latest_presentation(
    session_id: str,
    req: LatestPresentationWriteRequest,
    request: Request,
):
    workspace_id = get_workspace_id_from_request(request)
    sid = _ensure_session_id(session_id)
    await _assert_session_access(workspace_id, sid)
    slidev_deck = req.slidev_deck
    slidev_build = None
    presentation_payload = req.presentation
    temp_root: Path | None = None
    render_status = "ready"
    render_error = None
    try:
        if (req.output_mode or "").strip() == "slidev":
            if not isinstance(slidev_deck, dict):
                raise HTTPException(status_code=422, detail="保存 Slidev 演示稿时缺少 slidev_deck")
            markdown = str(slidev_deck.get("markdown") or "").strip()
            if not markdown:
                raise HTTPException(status_code=422, detail="保存 Slidev 演示稿时缺少 markdown")
            outline_items = _slidev_outline_items_from_payload(slidev_deck, presentation_payload)
            settings.uploads_dir.mkdir(parents=True, exist_ok=True)
            temp_root = Path(tempfile.mkdtemp(prefix="zhiyan-slidev-save-", dir=settings.uploads_dir))
            temp_build_root = temp_root / "dist"
            try:
                finalized = await prepare_slidev_deck_artifact(
                    markdown=markdown,
                    fallback_title=str(presentation_payload.get("title") or "新演示文稿"),
                    selected_style_id=str(slidev_deck.get("selected_style_id") or "").strip() or None,
                    topic=str(presentation_payload.get("title") or ""),
                    outline_items=outline_items,
                    expected_pages=max(
                        1, len(outline_items) or int(slidev_deck.get("expected_slide_count") or 0) or 1
                    ),
                )
                presentation_payload = finalized["presentation"]
                slidev_deck = {
                    "markdown": finalized["markdown"],
                    "meta": finalized["meta"],
                    "selected_style_id": finalized["selected_style_id"],
                }
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            try:
                await build_slidev_spa(
                    markdown=finalized["markdown"],
                    base_path=f"/api/v1/sessions/{sid}/presentations/latest/slidev/build/",
                    out_dir=temp_build_root,
                )
                slidev_build = {
                    "build_root": str(temp_build_root.resolve()),
                    "entry_path": str((temp_build_root / "index.html").resolve()),
                    "slide_count": finalized["meta"]["slide_count"],
                }
            except RuntimeError as exc:
                render_status = "failed"
                render_error = str(exc)
        presentation_payload = dict(presentation_payload or {})
        presentation_payload["artifactStatus"] = "ready"
        presentation_payload["renderStatus"] = render_status
        presentation_payload["renderError"] = render_error
        presentation_payload["artifactAvailable"] = True
        presentation_payload["renderAvailable"] = slidev_build is not None or (req.output_mode or "").strip() != "slidev"
        saved = await session_store.save_presentation(
            session_id=sid,
            payload=presentation_payload,
            is_snapshot=False,
            snapshot_label=None,
            output_mode=req.output_mode,
            html_deck=req.html_deck,
            slidev_deck=slidev_deck,
            slidev_build=slidev_build,
        )
        return SnapshotMeta.model_validate(saved)
    finally:
        if temp_root is not None:
            with suppress(Exception):
                shutil.rmtree(temp_root)


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
