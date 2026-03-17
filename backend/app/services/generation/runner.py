"""Background job runner for generation v2."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models.generation import EventType, GenerationEvent, GenerationJob, JobStatus, StageResult, StageStatus, now_iso
from app.models.generation_shadow import EngineMetrics, ShadowABRecord, ShadowRoute
from app.models.slide import Presentation, Slide
from app.services.generation.engine_router import decide_engine_route, decide_shadow_route
from app.services.generation.engines import InternalV2Engine
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.pipeline.graph import (
    PipelineState,
)

logger = logging.getLogger(__name__)

ERROR_STAGE_TIMEOUT = "STAGE_TIMEOUT"
ERROR_PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
ERROR_PROVIDER_NETWORK = "PROVIDER_NETWORK"
ERROR_PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
ERROR_CANCELLED = "CANCELLED"
ERROR_UNKNOWN = "UNKNOWN"


class StageTimeoutError(TimeoutError):
    def __init__(self, stage: StageStatus, timeout_seconds: float):
        self.stage = stage
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{stage.value} timed out after {timeout_seconds:.1f}s")


@dataclass(frozen=True)
class ClassifiedError:
    error_code: str
    error_message: str
    retriable: bool


class GenerationRunner:
    def __init__(self, store: GenerationJobStore, event_bus: GenerationEventBus):
        self._store = store
        self._event_bus = event_bus
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._tasks_lock = asyncio.Lock()
        # Shadow tasks are best-effort background evaluations; they must not block the primary job.
        self._shadow_tasks: dict[str, asyncio.Task[None]] = {}
        self._shadow_tasks_lock = asyncio.Lock()

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

    async def _drop_shadow_task(self, job_id: str) -> None:
        async with self._shadow_tasks_lock:
            self._shadow_tasks.pop(job_id, None)

    async def _start_shadow_job(self, job_id: str) -> None:
        async with self._shadow_tasks_lock:
            current = self._shadow_tasks.get(job_id)
            if current and not current.done():
                return
            task = asyncio.create_task(self._run_shadow_job(job_id))
            self._shadow_tasks[job_id] = task

            def _on_done(t: asyncio.Task[None], jid: str = job_id) -> None:
                with suppress(Exception):
                    exc = t.exception()
                    if exc is not None:
                        logger.warning(
                            "shadow job failed",
                            extra={"event": "shadow_job_failed", "job_id": jid, "error_type": type(exc).__name__},
                            exc_info=exc,
                        )
                asyncio.create_task(self._drop_shadow_task(jid))

            task.add_done_callback(_on_done)

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

        if from_stage is None and job.status in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
            return

        start_stage = from_stage or self._infer_start_stage(job)

        job.status = JobStatus.RUNNING
        job.error = None
        job.cancel_requested = False
        job.updated_at = now_iso()

        # --- Engine routing (Phase 1 foundation) ---
        # Persist a single, auditable routing decision on the job metadata, so retries/resumes
        # keep the same engine unless explicitly overridden by a future governance layer.
        route = None
        if isinstance(job.document_metadata, dict):
            route = job.document_metadata.get("engine_route")
        if not isinstance(route, dict) or not str(route.get("primary_engine") or "").strip():
            decision = decide_engine_route(job)
            job.document_metadata.setdefault("engine_route", decision.to_metadata())
        primary_engine = str(job.document_metadata.get("engine_route", {}).get("primary_engine") or "internal_v2")
        primary_engine = primary_engine.strip().lower() or "internal_v2"

        # --- Shadow mode (Phase 2): determine whether to run a secondary engine in background ---
        shadow_route = None
        if isinstance(job.document_metadata, dict):
            shadow_route = job.document_metadata.get("shadow_route")
        if not isinstance(shadow_route, dict) or "decided_at" not in shadow_route:
            shadow_decision = decide_shadow_route(job)
            job.document_metadata.setdefault("shadow_route", shadow_decision.to_metadata())
            shadow_route = job.document_metadata.get("shadow_route")

        # Phase 1 supports internal engine only; external engines are introduced later behind the router.
        if primary_engine != "internal_v2":
            raise RuntimeError(f"Unsupported generation engine: {primary_engine}")
        engine = InternalV2Engine()

        await self._store.save_job(job)
        await self._ensure_shadow_record(job, primary_engine=primary_engine)
        shadow_route_saved = job.document_metadata.get("shadow_route") if isinstance(job.document_metadata, dict) else None
        if (
            isinstance(shadow_route_saved, dict)
            and bool(shadow_route_saved.get("enabled"))
            and bool(shadow_route_saved.get("sampled"))
        ):
            await self._start_shadow_job(job.job_id)
        if job.request.session_id:
            from app.services.sessions import session_store

            await session_store.update_generation_job_status(
                job.job_id,
                JobStatus.RUNNING.value,
            )

        if job.events_seq == 0:
            await self._emit_event(
                job,
                EventType.JOB_STARTED,
                message="任务开始",
                payload={
                    "mode": job.mode.value,
                    "num_pages": job.request.num_pages,
                    "engine": primary_engine,
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

        job_started_monotonic = time.monotonic()
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
                        stage_coro=engine.parse(state, progress=progress_hook),
                    )
                elif stage == StageStatus.OUTLINE:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.OUTLINE,
                        timeout=float(settings.outline_timeout_seconds),
                        stage_coro=engine.outline(state, progress=progress_hook),
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
                                    "suggested_slide_role": item.get(
                                        "suggested_slide_role", "narrative"
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
                        if job.request.session_id:
                            from app.services.sessions import session_store

                            await session_store.update_generation_job_status(
                                job.job_id,
                                JobStatus.WAITING_OUTLINE_REVIEW.value,
                            )
                        await self._sync_primary_metrics_to_shadow_record(job, primary_engine=primary_engine)
                        return
                elif stage == StageStatus.LAYOUT:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.LAYOUT,
                        timeout=float(settings.layout_timeout_seconds),
                        stage_coro=engine.layout(state, progress=progress_hook),
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
                        stage_coro=engine.slides(
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
                        stage_coro=engine.assets(state, progress=progress_hook),
                    )
                    await self._sync_state_to_job(job, state)
                elif stage == StageStatus.VERIFY:
                    await self._run_stage(
                        job,
                        state,
                        stage=StageStatus.VERIFY,
                        timeout=float(settings.verify_timeout_seconds),
                        stage_coro=engine.verify(
                            state,
                            progress=progress_hook,
                            enable_vision=settings.enable_vision_verification,
                        ),
                    )
                    await self._sync_state_to_job(job, state)

            hard_slide_ids, advisory_count = self._collect_fix_issue_summary(state.verification_issues)
            if hard_slide_ids:
                job.status = JobStatus.WAITING_FIX_REVIEW
                job.current_stage = StageStatus.VERIFY
                job.hard_issue_slide_ids = hard_slide_ids
                job.advisory_issue_count = advisory_count
                job.fix_preview_slides = []
                job.fix_preview_source_ids = []
                job.updated_at = now_iso()
                await self._store.save_job(job)
                if job.request.session_id:
                    from app.services.sessions import session_store
                    await session_store.update_generation_job_status(
                        job.job_id,
                        JobStatus.WAITING_FIX_REVIEW.value,
                    )
                await self._emit_event(
                    job,
                    EventType.JOB_WAITING_FIX_REVIEW,
                    stage=StageStatus.VERIFY,
                    message="发现硬错误，等待用户决策修复",
                    payload={
                        "issues": job.issues,
                        "hard_issue_slide_ids": hard_slide_ids,
                        "advisory_issue_count": advisory_count,
                        "failed_slide_indices": job.failed_slide_indices,
                    },
                )
                await self._sync_primary_metrics_to_shadow_record(job, primary_engine=primary_engine)
                return

            job.presentation = self._build_presentation_payload(job, state.slides)
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
            await self._sync_primary_metrics_to_shadow_record(job, primary_engine=primary_engine)

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
            await self._sync_primary_metrics_to_shadow_record(job, primary_engine=primary_engine)
            return
        except Exception as e:
            partial_saved = False
            partial_presentation: dict | None = None
            with suppress(Exception):
                await self._sync_state_to_job(job, state)
            try:
                partial_saved, partial_presentation = await self._persist_partial_presentation(job, state)
            except Exception:
                logger.warning(
                    "persist partial presentation failed",
                    extra={"job_id": job.job_id},
                    exc_info=True,
                )

            failed_stage = job.current_stage
            classified = self._classify_generation_error(
                e,
                stage=failed_stage,
                timeout_seconds=None,
            )
            elapsed_ms = int((time.monotonic() - job_started_monotonic) * 1000)
            job.status = JobStatus.FAILED
            job.error = f"[{classified.error_code}] {classified.error_message}"
            job.current_stage = None
            job.updated_at = now_iso()
            await self._store.save_job(job)
            if job.request.session_id:
                from app.services.sessions import session_store
                await session_store.update_generation_job_status(
                    job.job_id,
                    JobStatus.FAILED.value,
                )
            payload = self._build_error_payload(
                classified=classified,
                stage=failed_stage,
                timeout_seconds=e.timeout_seconds if isinstance(e, StageTimeoutError) else None,
            )
            payload["partial_saved"] = partial_saved
            if partial_presentation is not None:
                payload["presentation"] = partial_presentation
            await self._emit_event(
                job,
                EventType.JOB_FAILED,
                message="任务失败",
                payload=payload,
            )
            await self._sync_primary_metrics_to_shadow_record(job, primary_engine=primary_engine)
            logger.exception(
                "generation job failed",
                extra={
                    "job_id": job.job_id,
                    "stage": failed_stage.value if failed_stage else None,
                    "error_type": type(e).__name__,
                    "error_code": classified.error_code,
                    "retriable": classified.retriable,
                    "elapsed_ms": elapsed_ms,
                },
            )

    async def _run_shadow_job(self, job_id: str) -> None:
        job = await self._store.get_job(job_id)
        if job is None:
            return

        shadow_route_raw = job.document_metadata.get("shadow_route") if isinstance(job.document_metadata, dict) else None
        if not isinstance(shadow_route_raw, dict) or not bool(shadow_route_raw.get("enabled")):
            return
        if not bool(shadow_route_raw.get("sampled")):
            return

        engine_id = str(shadow_route_raw.get("shadow_engine") or "internal_v2").strip().lower() or "internal_v2"
        primary_engine = str(job.document_metadata.get("engine_route", {}).get("primary_engine") or "internal_v2")
        primary_engine = primary_engine.strip().lower() or "internal_v2"

        await self._ensure_shadow_record(job, primary_engine=primary_engine)

        metrics = EngineMetrics(engine_id=engine_id, status="running", started_at=now_iso())
        await self._set_shadow_metrics(job_id, metrics)

        if job.mode.value == "review_outline" and not job.outline_accepted:
            metrics.status = "skipped"
            metrics.ended_at = now_iso()
            metrics.duration_ms = 0
            metrics.error_code = "SKIPPED_OUTLINE_REVIEW"
            metrics.error_message = "job is waiting for outline acceptance; shadow run skipped"
            await self._set_shadow_metrics(job_id, metrics)
            return

        if engine_id != "internal_v2":
            metrics.status = "failed"
            metrics.ended_at = now_iso()
            metrics.duration_ms = 0
            metrics.error_code = "ENGINE_UNSUPPORTED"
            metrics.error_message = f"shadow engine not implemented: {engine_id}"
            await self._set_shadow_metrics(job_id, metrics)
            return

        state = self._build_state(job)
        engine = InternalV2Engine()

        started_monotonic = time.monotonic()
        first_slide_monotonic: float | None = None

        async def slide_hook(payload: dict) -> None:  # noqa: ARG001
            nonlocal first_slide_monotonic
            if first_slide_monotonic is None:
                first_slide_monotonic = time.monotonic()

        stage_durations: dict[str, int] = {}
        current_stage: StageStatus | None = None
        current_timeout: float | None = None
        try:
            sequence = [
                StageStatus.PARSE,
                StageStatus.OUTLINE,
                StageStatus.LAYOUT,
                StageStatus.SLIDES,
                StageStatus.ASSETS,
                StageStatus.VERIFY,
            ]
            for stage in sequence:
                current_stage = stage
                if stage == StageStatus.PARSE:
                    current_timeout = float(settings.job_timeout_seconds)
                    coro = engine.parse(state, progress=None)
                elif stage == StageStatus.OUTLINE:
                    current_timeout = float(settings.outline_timeout_seconds)
                    coro = engine.outline(state, progress=None)
                elif stage == StageStatus.LAYOUT:
                    current_timeout = float(settings.layout_timeout_seconds)
                    coro = engine.layout(state, progress=None)
                elif stage == StageStatus.SLIDES:
                    current_timeout = float(settings.job_timeout_seconds)
                    coro = engine.slides(
                        state,
                        per_slide_timeout=float(settings.per_slide_timeout_seconds),
                        progress=None,
                        on_slide=slide_hook,
                    )
                elif stage == StageStatus.ASSETS:
                    current_timeout = float(settings.job_timeout_seconds)
                    coro = engine.assets(state, progress=None)
                elif stage == StageStatus.VERIFY:
                    current_timeout = float(settings.verify_timeout_seconds)
                    coro = engine.verify(
                        state,
                        progress=None,
                        enable_vision=settings.enable_vision_verification,
                    )
                else:
                    continue

                t0 = time.monotonic()
                try:
                    await asyncio.wait_for(coro, timeout=current_timeout)
                except asyncio.TimeoutError as e:
                    raise StageTimeoutError(stage=stage, timeout_seconds=float(current_timeout)) from e
                stage_durations[stage.value] = int((time.monotonic() - t0) * 1000)

            metrics.status = "completed"
        except Exception as e:
            classified = self._classify_generation_error(
                e,
                stage=current_stage,
                timeout_seconds=current_timeout,
            )
            metrics.status = "failed"
            metrics.error_code = classified.error_code
            metrics.error_message = classified.error_message
            metrics.retriable = classified.retriable
        finally:
            elapsed_ms = int((time.monotonic() - started_monotonic) * 1000)
            metrics.ended_at = now_iso()
            metrics.duration_ms = elapsed_ms
            metrics.stage_durations_ms = stage_durations
            metrics.ttfs_ms = (
                int((first_slide_monotonic - started_monotonic) * 1000)
                if first_slide_monotonic is not None
                else None
            )
            metrics.llm_usage = self._extract_llm_usage(state.document_metadata)
            metrics.extra = {
                "failed_slide_indices": list(state.failed_slide_indices),
                "issue_count": len(state.verification_issues or []),
            }
            await self._set_shadow_metrics(job_id, metrics)

    async def preview_fix(
        self,
        job_id: str,
        *,
        slide_ids: list[str] | None = None,
    ) -> GenerationJob:
        job = await self._store.get_job(job_id)
        if job is None:
            raise ValueError("Job not found")
        if job.status != JobStatus.WAITING_FIX_REVIEW:
            raise RuntimeError(f"当前状态不支持生成修复建议: {job.status.value}")

        requested_ids = [sid for sid in (slide_ids or []) if sid]
        target_ids = requested_ids or list(job.hard_issue_slide_ids)
        if not target_ids:
            target_ids, _ = self._collect_fix_issue_summary(job.issues)
        if not target_ids:
            raise RuntimeError("当前任务没有可修复的硬错误页面")

        preview_state = self._build_state(job)
        from app.services.pipeline import graph as graph_mod

        await graph_mod.stage_fix_slides_once(
            preview_state,
            per_slide_timeout=float(settings.per_slide_timeout_seconds),
            target_slide_ids=set(target_ids),
        )

        base_slides: dict[str, dict] = {}
        for item in job.slides:
            if not isinstance(item, dict):
                continue
            try:
                normalized = Slide.model_validate(item).model_dump(mode="json", by_alias=True)
            except Exception:
                normalized = deepcopy(item)
            sid = str(normalized.get("slideId") or item.get("slideId") or "").strip()
            if sid:
                base_slides[sid] = normalized
        preview_slides: list[dict] = []
        preview_slide_ids: list[str] = []
        for slide in preview_state.slides:
            slide_payload = slide.model_dump(mode="json", by_alias=True)
            sid = slide.slide_id
            base = base_slides.get(sid)
            if base == slide_payload:
                continue
            preview_slides.append(slide_payload)
            preview_slide_ids.append(sid)

        job.fix_preview_slides = preview_slides
        job.fix_preview_source_ids = preview_slide_ids
        job.updated_at = now_iso()
        await self._store.save_job(job)

        await self._emit_event(
            job,
            EventType.FIX_PREVIEW_READY,
            stage=StageStatus.FIX,
            message="修复建议已生成，请按页选择是否应用",
            payload={
                "fix_preview_slides": job.fix_preview_slides,
                "fix_preview_source_ids": job.fix_preview_source_ids,
                "requested_slide_ids": target_ids,
            },
        )
        return job

    async def apply_fix(
        self,
        job_id: str,
        *,
        slide_ids: list[str],
    ) -> GenerationJob:
        job = await self._store.get_job(job_id)
        if job is None:
            raise ValueError("Job not found")
        if job.status != JobStatus.WAITING_FIX_REVIEW:
            raise RuntimeError(f"当前状态不支持应用修复: {job.status.value}")
        if not job.fix_preview_slides:
            raise RuntimeError("暂无修复候选，请先生成修复建议")

        selected = [sid for sid in slide_ids if sid]
        if not selected:
            raise RuntimeError("请至少选择一页进行应用")

        preview_by_id = {
            str(slide.get("slideId")): deepcopy(slide)
            for slide in job.fix_preview_slides
            if isinstance(slide, dict) and slide.get("slideId")
        }
        unknown = [sid for sid in selected if sid not in preview_by_id]
        if unknown:
            raise RuntimeError("存在无效候选页，请重新生成修复建议")

        next_slides: list[dict] = []
        selected_set = set(selected)
        for slide in job.slides:
            sid = str(slide.get("slideId")) if isinstance(slide, dict) else ""
            if sid in selected_set:
                next_slides.append(preview_by_id[sid])
            else:
                next_slides.append(slide)

        job.slides = next_slides
        job.fix_preview_slides = []
        job.fix_preview_source_ids = []
        job.presentation = self._build_presentation_payload(
            job,
            [Slide.model_validate(slide) for slide in job.slides],
        )
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
            message="已按选择应用修复并完成任务",
            payload={
                "presentation": job.presentation,
                "issues": job.issues,
                "failed_slide_indices": job.failed_slide_indices,
                "applied_slide_ids": selected,
            },
        )
        return job

    async def skip_fix(self, job_id: str) -> GenerationJob:
        job = await self._store.get_job(job_id)
        if job is None:
            raise ValueError("Job not found")
        if job.status != JobStatus.WAITING_FIX_REVIEW:
            raise RuntimeError(f"当前状态不支持跳过修复: {job.status.value}")

        slides = [Slide.model_validate(slide) for slide in job.slides]
        job.fix_preview_slides = []
        job.fix_preview_source_ids = []
        job.presentation = self._build_presentation_payload(job, slides)
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
            message="已跳过修复并完成任务",
            payload={
                "presentation": job.presentation,
                "issues": job.issues,
                "failed_slide_indices": job.failed_slide_indices,
                "fix_skipped": True,
            },
        )
        return job

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

        await self._emit_event(
            job,
            EventType.STAGE_STARTED,
            stage=stage,
            message=f"{stage.value} 阶段开始",
            payload={
                "stage_timeout_seconds": timeout,
                "started_at": start_ts,
            },
        )

        try:
            await asyncio.wait_for(stage_coro, timeout=timeout)
        except asyncio.TimeoutError as e:
            timeout_exc = StageTimeoutError(stage=stage, timeout_seconds=timeout)
            classified = self._classify_generation_error(timeout_exc, stage=stage, timeout_seconds=timeout)
            duration_ms = int((time.monotonic() - t0) * 1000)
            job.stage_results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=start_ts,
                    ended_at=now_iso(),
                    duration_ms=duration_ms,
                    error=classified.error_message,
                    error_code=classified.error_code,
                    retriable=classified.retriable,
                    timeout_seconds=timeout,
                    provider_model=self._model_for_stage(stage),
                    provider=self._provider_for_stage(stage),
                )
            )
            await self._store.save_job(job)
            await self._emit_event(
                job,
                EventType.STAGE_FAILED,
                stage=stage,
                message=f"{stage.value} 阶段超时",
                payload=self._build_error_payload(
                    classified=classified,
                    stage=stage,
                    timeout_seconds=timeout,
                ),
            )
            logger.warning(
                "generation stage failed",
                extra={
                    "job_id": job.job_id,
                    "stage": stage.value,
                    "error_type": type(e).__name__,
                    "error_code": classified.error_code,
                    "retriable": classified.retriable,
                    "elapsed_ms": duration_ms,
                },
            )
            raise timeout_exc from e
        except Exception as e:
            classified = self._classify_generation_error(e, stage=stage, timeout_seconds=timeout)
            duration_ms = int((time.monotonic() - t0) * 1000)
            job.stage_results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=start_ts,
                    ended_at=now_iso(),
                    duration_ms=duration_ms,
                    error=classified.error_message,
                    error_code=classified.error_code,
                    retriable=classified.retriable,
                    timeout_seconds=timeout if classified.error_code == ERROR_STAGE_TIMEOUT else None,
                    provider_model=self._model_for_stage(stage),
                    provider=self._provider_for_stage(stage),
                )
            )
            await self._store.save_job(job)
            await self._emit_event(
                job,
                EventType.STAGE_FAILED,
                stage=stage,
                message=f"{stage.value} 阶段失败",
                payload=self._build_error_payload(
                    classified=classified,
                    stage=stage,
                    timeout_seconds=timeout,
                ),
            )
            logger.warning(
                "generation stage failed",
                extra={
                    "job_id": job.job_id,
                    "stage": stage.value,
                    "error_type": type(e).__name__,
                    "error_code": classified.error_code,
                    "retriable": classified.retriable,
                    "elapsed_ms": duration_ms,
                },
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

    def _classify_generation_error(
        self,
        error: Exception,
        stage: StageStatus | None,
        timeout_seconds: float | None,
    ) -> ClassifiedError:
        if isinstance(error, StageTimeoutError):
            return ClassifiedError(
                error_code=ERROR_STAGE_TIMEOUT,
                error_message=f"{error.stage.value} timed out after {error.timeout_seconds:.1f}s",
                retriable=True,
            )

        if isinstance(error, asyncio.CancelledError):
            return ClassifiedError(
                error_code=ERROR_CANCELLED,
                error_message="generation cancelled by user",
                retriable=False,
            )

        if self._is_provider_rate_limited(error):
            return ClassifiedError(
                error_code=ERROR_PROVIDER_RATE_LIMIT,
                error_message="provider rate limited the request",
                retriable=True,
            )

        if isinstance(error, httpx.TimeoutException):
            return ClassifiedError(
                error_code=ERROR_PROVIDER_TIMEOUT,
                error_message="provider request timed out",
                retriable=True,
            )

        if isinstance(error, (httpx.ConnectError, httpx.NetworkError, httpx.ReadError, httpx.WriteError)):
            return ClassifiedError(
                error_code=ERROR_PROVIDER_NETWORK,
                error_message="provider network connection failed",
                retriable=True,
            )

        error_name = type(error).__name__.lower()
        error_text = str(error).lower()
        if "timeout" in error_name or "timed out" in error_text:
            if stage and timeout_seconds and "after" in error_text:
                return ClassifiedError(
                    error_code=ERROR_STAGE_TIMEOUT,
                    error_message=f"{stage.value} timed out after {timeout_seconds:.1f}s",
                    retriable=True,
                )
            return ClassifiedError(
                error_code=ERROR_PROVIDER_TIMEOUT,
                error_message="provider request timed out",
                retriable=True,
            )

        return ClassifiedError(
            error_code=ERROR_UNKNOWN,
            error_message=f"{type(error).__name__}: {error}",
            retriable=False,
        )

    def _build_error_payload(
        self,
        *,
        classified: ClassifiedError,
        stage: StageStatus | None,
        timeout_seconds: float | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "error": classified.error_message,
            "error_code": classified.error_code,
            "error_message": classified.error_message,
            "retriable": classified.retriable,
            "timeout_seconds": timeout_seconds if classified.error_code == ERROR_STAGE_TIMEOUT else None,
            "provider_model": self._model_for_stage(stage),
            "provider": self._provider_for_stage(stage),
            "stage": stage.value if stage else None,
        }
        return payload

    @staticmethod
    def _provider_for_stage(stage: StageStatus | None) -> str | None:
        model = GenerationRunner._model_for_stage(stage)
        if not model:
            return None
        provider, sep, _ = model.partition(":")
        return provider if sep else None

    @staticmethod
    def _model_for_stage(stage: StageStatus | None) -> str | None:
        if stage in {StageStatus.OUTLINE, StageStatus.SLIDES, StageStatus.FIX}:
            return settings.strong_model
        if stage == StageStatus.LAYOUT:
            return settings.fast_model or settings.default_model
        if stage == StageStatus.VERIFY:
            return settings.vision_model
        return None

    @staticmethod
    def _is_provider_rate_limited(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int) and status_code == 429:
            return True

        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int) and response_status == 429:
            return True

        msg = str(error).lower()
        return "rate limit" in msg or "status code: 429" in msg or "http 429" in msg

    async def _sync_state_to_job(self, job: GenerationJob, state: PipelineState) -> None:
        # Preserve router metadata stored on the job while syncing stage-produced metadata.
        # PipelineState may overwrite document_metadata entirely (tests do), so merge here.
        merged_metadata: dict = {}
        if isinstance(job.document_metadata, dict):
            merged_metadata.update(job.document_metadata)
        if isinstance(state.document_metadata, dict):
            merged_metadata.update(state.document_metadata)
        job.document_metadata = merged_metadata
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
        hard_slide_ids, advisory_count = self._collect_fix_issue_summary(job.issues)
        job.hard_issue_slide_ids = hard_slide_ids
        job.advisory_issue_count = advisory_count
        job.failed_slide_indices = list(state.failed_slide_indices)
        job.updated_at = now_iso()
        await self._store.save_job(job)

    @staticmethod
    def _collect_fix_issue_summary(issues: list[dict]) -> tuple[list[str], int]:
        hard_slide_ids: set[str] = set()
        advisory_count = 0
        for issue in issues:
            tier = str(issue.get("tier") or "").lower()
            severity = str(issue.get("severity") or "").lower()
            is_hard = tier == "hard" or (not tier and severity == "error")
            if is_hard:
                slide_id = str(issue.get("slide_id") or "").strip()
                if slide_id:
                    hard_slide_ids.add(slide_id)
                continue
            advisory_count += 1
        return sorted(hard_slide_ids), advisory_count

    @staticmethod
    def _build_presentation_payload(job: GenerationJob, slides: list[Slide]) -> dict:
        title = job.request.title or "新演示文稿"
        existing = job.presentation if isinstance(job.presentation, dict) else {}
        presentation_id = existing.get("presentationId")
        if not isinstance(presentation_id, str) or not presentation_id.strip():
            presentation_id = f"pres-{uuid4().hex[:8]}"
        return Presentation(
            presentationId=presentation_id,
            title=title,
            slides=slides,
        ).model_dump(mode="json", by_alias=True)

    async def _persist_partial_presentation(
        self,
        job: GenerationJob,
        state: PipelineState,
    ) -> tuple[bool, dict | None]:
        if not job.slides and not state.slides:
            return False, None

        if not job.slides:
            await self._sync_state_to_job(job, state)
        if not job.slides:
            return False, None

        current = job.presentation if isinstance(job.presentation, dict) else {}
        presentation_id = current.get("presentationId")
        if not isinstance(presentation_id, str) or not presentation_id.strip():
            presentation_id = f"pres-{uuid4().hex[:8]}"

        presentation_payload = {
            "presentationId": presentation_id,
            "title": job.request.title or "新演示文稿",
            "slides": list(job.slides),
        }
        job.presentation = presentation_payload
        job.updated_at = now_iso()
        await self._store.save_job(job)

        saved_to_session = False
        if job.request.session_id:
            from app.services.sessions import session_store

            await session_store.save_presentation(
                session_id=job.request.session_id,
                payload=presentation_payload,
                is_snapshot=False,
            )
            saved_to_session = True
        return saved_to_session, presentation_payload

    async def _load_shadow_record(self, job_id: str) -> ShadowABRecord | None:
        raw = await self._store.get_shadow_record(job_id)
        if not isinstance(raw, dict):
            return None
        try:
            return ShadowABRecord.model_validate(raw)
        except Exception:
            return None

    @staticmethod
    def _extract_llm_usage(metadata: dict | None) -> dict[str, int]:
        if not isinstance(metadata, dict):
            return {}
        raw = metadata.get("llm_usage_total")
        if not isinstance(raw, dict):
            return {}
        usage: dict[str, int] = {}
        for key, value in raw.items():
            if isinstance(value, int):
                usage[str(key)] = value
            else:
                with suppress(Exception):
                    usage[str(key)] = int(value)
        return usage

    async def _ensure_shadow_record(self, job: GenerationJob, *, primary_engine: str) -> None:
        """Create/update the persisted shadow record (only for sampled shadow jobs)."""
        shadow_route_raw = job.document_metadata.get("shadow_route") if isinstance(job.document_metadata, dict) else None
        if (
            not isinstance(shadow_route_raw, dict)
            or not bool(shadow_route_raw.get("enabled"))
            or not bool(shadow_route_raw.get("sampled"))
        ):
            return

        record = await self._load_shadow_record(job.job_id) or ShadowABRecord(job_id=job.job_id)
        record.primary_engine = primary_engine
        try:
            record.shadow_route = ShadowRoute.model_validate(shadow_route_raw)
        except Exception:
            record.shadow_route = ShadowRoute()
        record.updated_at = now_iso()
        await self._store.save_shadow_record(job.job_id, record.model_dump(mode="json"))

    async def _set_shadow_metrics(self, job_id: str, metrics: EngineMetrics) -> None:
        record = await self._load_shadow_record(job_id) or ShadowABRecord(job_id=job_id)
        record.shadow = metrics
        record.updated_at = now_iso()
        record.deltas = _compute_shadow_deltas(record.primary, record.shadow)
        await self._store.save_shadow_record(job_id, record.model_dump(mode="json"))

    async def _sync_primary_metrics_to_shadow_record(self, job: GenerationJob, *, primary_engine: str) -> None:
        shadow_route_raw = job.document_metadata.get("shadow_route") if isinstance(job.document_metadata, dict) else None
        if (
            not isinstance(shadow_route_raw, dict)
            or not bool(shadow_route_raw.get("enabled"))
            or not bool(shadow_route_raw.get("sampled"))
        ):
            return

        record = await self._load_shadow_record(job.job_id) or ShadowABRecord(job_id=job.job_id)
        record.primary_engine = primary_engine
        try:
            record.shadow_route = ShadowRoute.model_validate(shadow_route_raw)
        except Exception:
            record.shadow_route = ShadowRoute()

        events = await self._store.list_events(job.job_id)
        record.primary = _build_primary_engine_metrics(
            job,
            events,
            primary_engine=primary_engine,
        )
        record.updated_at = now_iso()
        record.deltas = _compute_shadow_deltas(record.primary, record.shadow)
        await self._store.save_shadow_record(job.job_id, record.model_dump(mode="json"))

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


def _parse_event_ts(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    # now_iso() uses datetime.isoformat() with timezone offset.
    with suppress(Exception):
        return datetime.fromisoformat(ts)
    with suppress(Exception):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


def _build_primary_engine_metrics(
    job: GenerationJob,
    events: list[GenerationEvent],
    *,
    primary_engine: str,
) -> EngineMetrics:
    job_started_ts = next((evt.ts for evt in events if evt.type == EventType.JOB_STARTED), None)
    first_slide_ts = next((evt.ts for evt in events if evt.type == EventType.SLIDE_READY), None)

    if job.status == JobStatus.COMPLETED:
        terminal_ts = next((evt.ts for evt in reversed(events) if evt.type == EventType.JOB_COMPLETED), None)
    elif job.status == JobStatus.FAILED:
        terminal_ts = next((evt.ts for evt in reversed(events) if evt.type == EventType.JOB_FAILED), None)
    elif job.status == JobStatus.CANCELLED:
        terminal_ts = next((evt.ts for evt in reversed(events) if evt.type == EventType.JOB_CANCELLED), None)
    else:
        terminal_ts = job.updated_at

    started_dt = _parse_event_ts(job_started_ts) or _parse_event_ts(job.created_at) or _parse_event_ts(job.updated_at)
    ended_dt = _parse_event_ts(terminal_ts) or _parse_event_ts(job.updated_at)

    duration_ms: int | None = None
    if started_dt and ended_dt:
        duration_ms = int((ended_dt - started_dt).total_seconds() * 1000)

    ttfs_ms: int | None = None
    first_dt = _parse_event_ts(first_slide_ts)
    if started_dt and first_dt:
        ttfs_ms = int((first_dt - started_dt).total_seconds() * 1000)

    stage_durations: dict[str, int] = {}
    for result in job.stage_results or []:
        if result.duration_ms is None:
            continue
        stage_durations[result.stage.value] = int(result.duration_ms)

    usage = {}
    if isinstance(job.document_metadata, dict):
        raw_usage = job.document_metadata.get("llm_usage_total")
        if isinstance(raw_usage, dict):
            for key, value in raw_usage.items():
                with suppress(Exception):
                    usage[str(key)] = int(value)

    return EngineMetrics(
        engine_id=primary_engine,
        status=job.status.value,
        started_at=job_started_ts or job.created_at,
        ended_at=terminal_ts,
        duration_ms=duration_ms,
        ttfs_ms=ttfs_ms,
        stage_durations_ms=stage_durations,
        llm_usage=usage,
        extra={
            "mode": job.mode.value,
            "failed_slide_indices": list(job.failed_slide_indices or []),
            "issue_count": len(job.issues or []),
        },
        error_code=None,
        error_message=job.error,
        retriable=None,
    )


def _compute_shadow_deltas(primary: EngineMetrics | None, shadow: EngineMetrics | None) -> dict[str, int | float | None]:
    if primary is None or shadow is None:
        return {}
    deltas: dict[str, int | float | None] = {}
    if isinstance(primary.ttfs_ms, int) and isinstance(shadow.ttfs_ms, int):
        deltas["ttfs_ms_delta"] = shadow.ttfs_ms - primary.ttfs_ms
    if isinstance(primary.duration_ms, int) and isinstance(shadow.duration_ms, int):
        deltas["duration_ms_delta"] = shadow.duration_ms - primary.duration_ms
    if isinstance(primary.llm_usage, dict) and isinstance(shadow.llm_usage, dict):
        p_req = primary.llm_usage.get("requests")
        s_req = shadow.llm_usage.get("requests")
        if isinstance(p_req, int) and isinstance(s_req, int):
            deltas["llm_requests_delta"] = s_req - p_req
        p_tok = primary.llm_usage.get("total_tokens")
        s_tok = shadow.llm_usage.get("total_tokens")
        if isinstance(p_tok, int) and isinstance(s_tok, int):
            deltas["llm_total_tokens_delta"] = s_tok - p_tok
    return deltas
