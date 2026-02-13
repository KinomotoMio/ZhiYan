"""Background job runner for generation v2."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from uuid import uuid4

from app.core.config import settings
from app.models.generation import EventType, GenerationEvent, GenerationJob, JobStatus, StageResult, StageStatus, now_iso
from app.models.slide import Presentation, Slide
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.pipeline.graph import (
    PipelineState,
    stage_fix_slides_once,
    stage_generate_outline,
    stage_generate_slides,
    stage_parse_document,
    stage_resolve_assets,
    stage_select_layouts,
    stage_verify_slides,
)

logger = logging.getLogger(__name__)


class GenerationRunner:
    def __init__(self, store: GenerationJobStore, event_bus: GenerationEventBus):
        self._store = store
        self._event_bus = event_bus
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._tasks_lock = asyncio.Lock()

    async def start_job(self, job_id: str, from_stage: StageStatus | None = None) -> bool:
        async with self._tasks_lock:
            current = self._tasks.get(job_id)
            if current and not current.done():
                return False

            task = asyncio.create_task(self._run_job(job_id, from_stage))
            self._tasks[job_id] = task
            task.add_done_callback(lambda _t, jid=job_id: asyncio.create_task(self._drop_task(jid)))
        return True

    async def _drop_task(self, job_id: str) -> None:
        async with self._tasks_lock:
            self._tasks.pop(job_id, None)

    async def cancel_job(self, job_id: str) -> None:
        job = await self._store.get_job(job_id)
        if job is None:
            return

        job.cancel_requested = True
        job.updated_at = now_iso()
        await self._store.save_job(job)

        async with self._tasks_lock:
            task = self._tasks.get(job_id)

        if task and not task.done():
            task.cancel()
            return

        if job.status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.status = JobStatus.CANCELLED
            job.current_stage = None
            await self._emit_event(job, EventType.JOB_CANCELLED, message="任务已取消")
            await self._store.save_job(job)

    async def _run_job(self, job_id: str, from_stage: StageStatus | None = None) -> None:
        job = await self._store.get_job(job_id)
        if job is None:
            return

        if from_stage is None and job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return

        start_stage = from_stage or self._infer_start_stage(job)

        job.status = JobStatus.RUNNING
        job.error = None
        job.cancel_requested = False
        job.updated_at = now_iso()
        await self._store.save_job(job)

        if job.events_seq == 0:
            await self._emit_event(
                job,
                EventType.JOB_STARTED,
                message="任务开始",
                payload={
                    "mode": job.mode.value,
                    "num_pages": job.request.num_pages,
                },
            )

        state = self._build_state(job)

        async def progress_hook(stage: str, step: int, total_steps: int, message: str) -> None:
            stage_enum = _parse_stage(stage)
            await self._emit_event(
                job,
                EventType.STAGE_PROGRESS,
                stage=stage_enum,
                message=message,
                payload={
                    "step": step,
                    "total_steps": total_steps,
                },
            )

        async def slide_hook(payload: dict) -> None:
            idx = payload.get("slide_index", 0)
            await self._emit_event(
                job,
                EventType.SLIDE_READY,
                stage=StageStatus.SLIDES,
                message=f"第 {idx + 1} 页已生成",
                payload=payload,
            )

        try:
            await self._ensure_not_cancelled(job)

            sequence = [
                StageStatus.PARSE,
                StageStatus.OUTLINE,
                StageStatus.LAYOUT,
                StageStatus.SLIDES,
                StageStatus.ASSETS,
                StageStatus.VERIFY,
            ]
            start_index = sequence.index(start_stage)

            for stage in sequence[start_index:]:
                await self._ensure_not_cancelled(job)

                if stage == StageStatus.PARSE:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.PARSE,
                        timeout=float(settings.job_timeout_seconds),
                        stage_coro=stage_parse_document(state, progress=progress_hook),
                    )
                elif stage == StageStatus.OUTLINE:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.OUTLINE,
                        timeout=float(settings.outline_timeout_seconds),
                        stage_coro=stage_generate_outline(state, progress=progress_hook),
                    )
                    await self._sync_state_to_job(job, state)
                    await self._emit_event(
                        job,
                        EventType.OUTLINE_READY,
                        stage=StageStatus.OUTLINE,
                        message="大纲生成完成",
                        payload={
                            "topic": job.request.title,
                            "items": [
                                {
                                    "slide_number": item.get("slide_number"),
                                    "title": item.get("title"),
                                    "suggested_layout_category": item.get(
                                        "suggested_layout_category", "bullets"
                                    ),
                                }
                                for item in state.outline.get("items", [])
                            ],
                            "requires_accept": job.mode.value == "review_outline" and not job.outline_accepted,
                        },
                    )
                    if job.mode.value == "review_outline" and not job.outline_accepted:
                        job.status = JobStatus.WAITING_OUTLINE_REVIEW
                        job.current_stage = StageStatus.OUTLINE
                        job.updated_at = now_iso()
                        await self._store.save_job(job)
                        return
                elif stage == StageStatus.LAYOUT:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.LAYOUT,
                        timeout=float(settings.layout_timeout_seconds),
                        stage_coro=stage_select_layouts(state, progress=progress_hook),
                    )
                    await self._sync_state_to_job(job, state)
                    await self._emit_event(
                        job,
                        EventType.LAYOUT_READY,
                        stage=StageStatus.LAYOUT,
                        message="布局选择完成",
                        payload={"layouts": state.layout_selections},
                    )
                elif stage == StageStatus.SLIDES:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.SLIDES,
                        timeout=float(settings.job_timeout_seconds),
                        stage_coro=stage_generate_slides(
                            state,
                            per_slide_timeout=float(settings.per_slide_timeout_seconds),
                            progress=progress_hook,
                            on_slide=slide_hook,
                        ),
                    )
                    await self._sync_state_to_job(job, state)
                elif stage == StageStatus.ASSETS:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.ASSETS,
                        timeout=float(settings.job_timeout_seconds),
                        stage_coro=stage_resolve_assets(state, progress=progress_hook),
                    )
                    await self._sync_state_to_job(job, state)
                elif stage == StageStatus.VERIFY:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.VERIFY,
                        timeout=float(settings.verify_timeout_seconds),
                        stage_coro=stage_verify_slides(
                            state,
                            progress=progress_hook,
                            enable_vision=settings.enable_vision_verification,
                        ),
                    )
                    await self._sync_state_to_job(job, state)

            # Optional single fix pass when errors exist
            error_count = sum(1 for issue in state.verification_issues if issue.get("severity") == "error")
            if error_count > 0 and job.fix_passes < settings.max_fix_passes:
                await self._run_stage(
                    job,
                    state,
                    stage=StageStatus.FIX,
                    timeout=float(settings.job_timeout_seconds),
                    stage_coro=stage_fix_slides_once(
                        state,
                        per_slide_timeout=float(settings.per_slide_timeout_seconds),
                        progress=progress_hook,
                        on_slide=slide_hook,
                    ),
                )
                job.fix_passes += 1
                await self._sync_state_to_job(job, state)

                await self._run_stage(
                    job,
                    state,
                    stage=StageStatus.VERIFY,
                    timeout=float(settings.verify_timeout_seconds),
                    stage_coro=stage_verify_slides(
                        state,
                        progress=progress_hook,
                        enable_vision=settings.enable_vision_verification,
                    ),
                )
                await self._sync_state_to_job(job, state)

            title = job.request.title or "新演示文稿"
            presentation = Presentation(
                presentationId=f"pres-{uuid4().hex[:8]}",
                title=title,
                slides=state.slides,
            )

            job.presentation = presentation.model_dump(mode="json", by_alias=True)
            job.status = JobStatus.COMPLETED
            job.current_stage = StageStatus.COMPLETE
            job.updated_at = now_iso()
            await self._store.save_job(job)
            if job.request.session_id:
                from app.services.sessions import session_store
                await session_store.save_presentation(
                    session_id=job.request.session_id,
                    payload=job.presentation,
                    is_snapshot=False,
                )
                await session_store.update_generation_job_status(
                    job.job_id,
                    JobStatus.COMPLETED.value,
                )

            await self._emit_event(
                job,
                EventType.JOB_COMPLETED,
                stage=StageStatus.COMPLETE,
                message="任务完成",
                payload={
                    "presentation": job.presentation,
                    "issues": job.issues,
                    "failed_slide_indices": job.failed_slide_indices,
                },
            )

        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.current_stage = None
            job.updated_at = now_iso()
            await self._store.save_job(job)
            if job.request.session_id:
                from app.services.sessions import session_store
                await session_store.update_generation_job_status(
                    job.job_id,
                    JobStatus.CANCELLED.value,
                )
            await self._emit_event(job, EventType.JOB_CANCELLED, message="任务已取消")
            return
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = f"{type(e).__name__}: {e}"
            job.current_stage = None
            job.updated_at = now_iso()
            await self._store.save_job(job)
            if job.request.session_id:
                from app.services.sessions import session_store
                await session_store.update_generation_job_status(
                    job.job_id,
                    JobStatus.FAILED.value,
                )
            await self._emit_event(
                job,
                EventType.JOB_FAILED,
                message="任务失败",
                payload={"error": job.error},
            )
            logger.exception(
                "generation job failed",
                extra={"job_id": job.job_id, "stage": job.current_stage, "error_type": type(e).__name__},
            )

    async def _run_stage(
        self,
        job: GenerationJob,
        state: PipelineState,
        stage: StageStatus,
        timeout: float,
        stage_coro,
    ) -> None:
        await self._ensure_not_cancelled(job)

        start_ts = now_iso()
        t0 = time.monotonic()

        job.current_stage = stage
        job.updated_at = now_iso()
        await self._store.save_job(job)

        await self._emit_event(job, EventType.STAGE_STARTED, stage=stage, message=f"{stage.value} 阶段开始")

        try:
            await asyncio.wait_for(stage_coro, timeout=timeout)
        except asyncio.TimeoutError as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            job.stage_results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=start_ts,
                    ended_at=now_iso(),
                    duration_ms=duration_ms,
                    error=f"timeout after {timeout}s",
                )
            )
            await self._store.save_job(job)
            await self._emit_event(
                job,
                EventType.STAGE_FAILED,
                stage=stage,
                message=f"{stage.value} 阶段超时",
                payload={"error": str(e), "timeout": timeout},
            )
            raise TimeoutError(f"Stage {stage.value} timed out after {timeout}s")
        except Exception as e:
            duration_ms = int((time.monotonic() - t0) * 1000)
            job.stage_results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=start_ts,
                    ended_at=now_iso(),
                    duration_ms=duration_ms,
                    error=str(e),
                )
            )
            await self._store.save_job(job)
            await self._emit_event(
                job,
                EventType.STAGE_FAILED,
                stage=stage,
                message=f"{stage.value} 阶段失败",
                payload={"error": f"{type(e).__name__}: {e}"},
            )
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)
        job.stage_results.append(
            StageResult(
                stage=stage,
                status="completed",
                started_at=start_ts,
                ended_at=now_iso(),
                duration_ms=duration_ms,
            )
        )
        await self._store.save_job(job)

        await self._emit_event(
            job,
            EventType.STAGE_PROGRESS,
            stage=stage,
            message=f"{stage.value} 阶段完成",
            payload={"duration_ms": duration_ms},
        )

    async def _sync_state_to_job(self, job: GenerationJob, state: PipelineState) -> None:
        job.document_metadata = state.document_metadata
        job.outline = state.outline
        job.layouts = state.layout_selections
        if state.slides:
            job.slides = [slide.model_dump(mode="json", by_alias=True) for slide in state.slides]
        elif state.slide_contents:
            job.slides = [
                {
                    "slideId": f"slide-{item['slide_number']}",
                    "layoutType": item.get("layout_id", "bullet-with-icons"),
                    "layoutId": item.get("layout_id", "bullet-with-icons"),
                    "contentData": item.get("content_data", {}),
                    "components": [],
                }
                for item in state.slide_contents
            ]
        job.issues = list(state.verification_issues)
        job.failed_slide_indices = list(state.failed_slide_indices)
        job.updated_at = now_iso()
        await self._store.save_job(job)

    async def _emit_event(
        self,
        job: GenerationJob,
        event_type: EventType,
        stage: StageStatus | None = None,
        message: str | None = None,
        payload: dict | None = None,
    ) -> None:
        job.events_seq += 1
        job.updated_at = now_iso()
        await self._store.save_job(job)

        event = GenerationEvent(
            seq=job.events_seq,
            type=event_type,
            job_id=job.job_id,
            stage=stage,
            message=message,
            payload=payload or {},
        )
        await self._store.append_event(event)
        await self._event_bus.publish(event)

    async def _ensure_not_cancelled(self, job: GenerationJob) -> None:
        refreshed = await self._store.get_job(job.job_id)
        if refreshed and refreshed.cancel_requested:
            raise asyncio.CancelledError()

    def _build_state(self, job: GenerationJob) -> PipelineState:
        state = PipelineState(
            raw_content=job.request.resolved_content or job.request.topic,
            source_ids=list(job.request.source_ids),
            topic=job.request.title,
            template_id=job.request.template_id,
            num_pages=max(3, min(job.request.num_pages, 50)),
            job_id=job.job_id,
        )
        state.document_metadata = dict(job.document_metadata)
        state.outline = dict(job.outline)
        state.layout_selections = list(job.layouts)
        state.verification_issues = list(job.issues)
        state.failed_slide_indices = list(job.failed_slide_indices)
        if job.slides:
            state.slides = [Slide.model_validate(slide) for slide in job.slides]
        return state

    @staticmethod
    def _infer_start_stage(job: GenerationJob) -> StageStatus:
        if not job.outline:
            return StageStatus.PARSE
        if not job.layouts:
            return StageStatus.LAYOUT
        if not job.slides:
            return StageStatus.SLIDES
        return StageStatus.VERIFY



def _parse_stage(raw: str) -> StageStatus | None:
    with suppress(ValueError):
        return StageStatus(raw)
    return None
