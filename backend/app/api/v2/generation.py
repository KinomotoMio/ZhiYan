"""Generation v2 API - job based pipeline orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

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
    GenerationMode,
    GenerationRequestData,
    JobActionResponse,
    JobStatus,
    StageStatus,
    now_iso,
)
from app.models.generation_shadow import ShadowABRecord
from app.services.generation import event_bus, generation_runner, job_store
from app.services.generation.engine_guard import guard as engine_guard
from app.services.sessions import session_store
from app.services.sessions.workspace import get_workspace_id_from_request

router = APIRouter(prefix="/generation", tags=["generation-v2"])
logger = logging.getLogger(__name__)


@router.post("/jobs", response_model=CreateJobResponse)
async def create_generation_job(req: CreateJobRequest, request: Request):
    workspace_id = get_workspace_id_from_request(request)
    await session_store.ensure_workspace(workspace_id)

    combined = req.content
    session_id = req.session_id
    if not session_id:
        title_seed = req.topic[:30] if req.topic else "未命名会话"
        created_session = await session_store.create_session(workspace_id, title_seed)
        session_id = created_session["id"]

    try:
        session = await session_store.get_session(workspace_id, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if session.get("has_presentation"):
        raise HTTPException(status_code=409, detail="当前会话已有演示稿，请新建会话生成")

    if req.source_ids:
        source_content = await session_store.get_combined_source_content(
            workspace_id,
            session_id,
            req.source_ids,
        )
        combined = f"{source_content}\n\n{combined}".strip() if combined else source_content

    if not combined and not req.topic:
        raise HTTPException(status_code=422, detail="请提供来源文档或主题描述")

    title = req.topic[:50] if req.topic else (combined[:50] if combined else "新演示文稿")
    job_id = f"job-{uuid4().hex[:12]}"

    job = GenerationJob(
        job_id=job_id,
        mode=req.mode,
        status=JobStatus.PENDING,
        request=GenerationRequestData(
            topic=req.topic,
            content=req.content,
            session_id=session_id,
            source_ids=req.source_ids,
            template_id=req.template_id,
            num_pages=max(3, min(req.num_pages, settings.max_slide_pages)),
            title=title,
            resolved_content=combined or req.topic,
        ),
        outline_accepted=req.mode == GenerationMode.AUTO,
    )

    await job_store.create_job(job)
    await session_store.save_generation_job(job.job_id, session_id, job.status.value)
    await generation_runner.start_job(job_id)

    return CreateJobResponse(
        job_id=job.job_id,
        session_id=session_id,
        status=job.status,
        created_at=job.created_at,
        event_stream_url=f"/api/v2/generation/jobs/{job.job_id}/events",
    )


@router.get("/jobs/{job_id}", response_model=GenerationJob)
async def get_generation_job(job_id: str):
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/shadow", response_model=ShadowABRecord)
async def get_generation_shadow_record(job_id: str):
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    record = await job_store.get_shadow_record(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Shadow record not found")

    try:
        return ShadowABRecord.model_validate(record)
    except ValidationError as e:
        logger.warning(
            "shadow record parse failed",
            extra={"job_id": job_id, "error_type": type(e).__name__},
        )
        # Return a minimal wrapper so clients can still see that the record exists.
        return ShadowABRecord(job_id=job_id, notes={"parse_error": str(e)})


@router.get("/guard")
async def get_generation_guard_state():
    """Return current circuit breaker state for generation engines."""
    return await engine_guard.dump_state()


@router.post("/jobs/{job_id}/outline/accept", response_model=JobActionResponse)
async def accept_outline(job_id: str, req: AcceptOutlineRequest):
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in {JobStatus.WAITING_OUTLINE_REVIEW, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail=f"当前状态不允许确认大纲: {job.status}")

    if req.outline is not None:
        job.outline = req.outline
    job.outline_accepted = True
    job.updated_at = now_iso()
    await job_store.save_job(job)

    await generation_runner.start_job(job_id, from_stage=StageStatus.LAYOUT)

    return JobActionResponse(job_id=job.job_id, status=job.status, current_stage=job.current_stage)


@router.post("/jobs/{job_id}/run", response_model=JobActionResponse)
async def run_job(job_id: str):
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.mode == GenerationMode.REVIEW_OUTLINE and not job.outline_accepted:
        raise HTTPException(status_code=409, detail="请先确认大纲后再继续")
    if job.status == JobStatus.WAITING_FIX_REVIEW:
        raise HTTPException(status_code=409, detail="当前任务正在等待修复决策，请先完成 fix 决策")

    started = await generation_runner.start_job(job_id)
    if not started and job.status == JobStatus.RUNNING:
        return JobActionResponse(job_id=job.job_id, status=job.status, current_stage=job.current_stage)

    refreshed = await job_store.get_job(job_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobActionResponse(job_id=refreshed.job_id, status=refreshed.status, current_stage=refreshed.current_stage)


@router.post("/jobs/{job_id}/fix/preview", response_model=GenerationJob)
async def preview_fix(job_id: str, req: FixPreviewRequest):
    try:
        job = await generation_runner.preview_fix(job_id, slide_ids=req.slide_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job


@router.post("/jobs/{job_id}/fix/apply", response_model=GenerationJob)
async def apply_fix(job_id: str, req: FixApplyRequest):
    try:
        job = await generation_runner.apply_fix(job_id, slide_ids=req.slide_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job


@router.post("/jobs/{job_id}/fix/skip", response_model=GenerationJob)
async def skip_fix(job_id: str):
    try:
        job = await generation_runner.skip_fix(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobActionResponse)
async def cancel_job(job_id: str):
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await generation_runner.cancel_job(job_id)
    refreshed = await job_store.get_job(job_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobActionResponse(job_id=refreshed.job_id, status=refreshed.status, current_stage=refreshed.current_stage)


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    after_seq: Annotated[int, Query(ge=0)] = 0,
):
    heartbeat = max(0.1, settings.sse_heartbeat_seconds)
    terminal_events = {
        EventType.JOB_COMPLETED,
        EventType.JOB_FAILED,
        EventType.JOB_CANCELLED,
        EventType.JOB_WAITING_FIX_REVIEW,
    }

    async def event_generator():
        job = await job_store.get_job(job_id)
        if not job:
            payload = {"type": "error", "message": "Job not found"}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        queue = await event_bus.subscribe(job_id)
        try:
            # Subscribe first to avoid missing terminal event between replay and live subscribe.
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

    logger.info("stream_open", extra={"event": "stream_open", "job_id": job_id})
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
