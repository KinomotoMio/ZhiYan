"""Background job runner for generation v2."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4
from typing import Any

import httpx

from app.core.config import settings
from app.models.generation import EventType, GenerationEvent, GenerationJob, JobStatus, StageResult, StageStatus, now_iso
from app.models.slide import Presentation, Slide
from app.services.generation.agentic.context import summarize_state
from app.services.generation.agentic.loop import agentic_loop
from app.services.generation.agentic.tools import ToolDef, ToolExecutionResult, ToolRegistry, dispatch_tool_calls
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.loop_planner import GenerationLoopPlanner, LoopHistoryItem
from app.services.generation.tool_registry import GenerationTool, GenerationToolRegistry
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
        self._loop_planner = GenerationLoopPlanner()

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

        if from_stage is None and job.status in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
            return

        start_stage = from_stage or self._infer_start_stage(job)

        job.status = JobStatus.RUNNING
        job.error = None
        job.cancel_requested = False
        job.updated_at = now_iso()
        await self._store.save_job(job)
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

            completed = await self._run_selected_runtime(
                job,
                state,
                start_stage=start_stage,
                progress_hook=progress_hook,
                slide_hook=slide_hook,
            )
            if not completed:
                return

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
                return

            elapsed_ms = int((time.monotonic() - job_started_monotonic) * 1000)
            stage_durations_ms = {
                sr.stage.value: sr.duration_ms for sr in job.stage_results if sr.duration_ms is not None
            }
            slowest_stage = None
            slowest_stage_ms = None
            for stage_name, duration in stage_durations_ms.items():
                if slowest_stage_ms is None or duration > slowest_stage_ms:
                    slowest_stage = stage_name
                    slowest_stage_ms = duration

            job.presentation = self._build_presentation_payload(job, state.slides)
            job.status = JobStatus.COMPLETED
            job.current_stage = StageStatus.COMPLETE
            # Keep this data on the job for easy offline inspection / support diagnostics.
            job.document_metadata.setdefault("timings", {})
            job.document_metadata["timings"].update(
                {
                    "job_elapsed_ms": elapsed_ms,
                    "stage_durations_ms": stage_durations_ms,
                    "slowest_stage": slowest_stage,
                    "slowest_stage_ms": slowest_stage_ms,
                }
            )
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
                    "elapsed_ms": elapsed_ms,
                    "stage_durations_ms": stage_durations_ms,
                    "slowest_stage": slowest_stage,
                    "slowest_stage_ms": slowest_stage_ms,
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

    def _build_tool_registry(self) -> GenerationToolRegistry:
        return GenerationToolRegistry(
            [
                GenerationTool(
                    name="parse_document",
                    stage=StageStatus.PARSE,
                    description="Parse the source document and derive structure signals for later tools.",
                    timeout_seconds=lambda: float(settings.job_timeout_seconds),
                    runner=lambda state, progress, _on_slide: stage_parse_document(state, progress=progress),
                ),
                GenerationTool(
                    name="generate_outline",
                    stage=StageStatus.OUTLINE,
                    description="Generate the presentation outline and slide role plan.",
                    timeout_seconds=lambda: float(settings.outline_timeout_seconds),
                    runner=lambda state, progress, _on_slide: stage_generate_outline(state, progress=progress),
                ),
                GenerationTool(
                    name="select_layouts",
                    stage=StageStatus.LAYOUT,
                    description="Select layout variants for each outline item.",
                    timeout_seconds=lambda: float(settings.layout_timeout_seconds),
                    runner=lambda state, progress, _on_slide: stage_select_layouts(state, progress=progress),
                ),
                GenerationTool(
                    name="generate_slides",
                    stage=StageStatus.SLIDES,
                    description="Generate slide content for each selected layout.",
                    timeout_seconds=lambda: float(settings.job_timeout_seconds),
                    runner=lambda state, progress, on_slide: stage_generate_slides(
                        state,
                        per_slide_timeout=float(settings.per_slide_timeout_seconds),
                        progress=progress,
                        on_slide=on_slide,
                    ),
                ),
                GenerationTool(
                    name="resolve_assets",
                    stage=StageStatus.ASSETS,
                    description="Materialize slide payloads and normalize assets.",
                    timeout_seconds=lambda: float(settings.job_timeout_seconds),
                    runner=lambda state, progress, _on_slide: stage_resolve_assets(state, progress=progress),
                ),
                GenerationTool(
                    name="verify_slides",
                    stage=StageStatus.VERIFY,
                    description="Run programmatic and aesthetic verification on the generated slides.",
                    timeout_seconds=lambda: float(settings.verify_timeout_seconds),
                    runner=lambda state, progress, _on_slide: stage_verify_slides(
                        state,
                        progress=progress,
                        enable_vision=settings.enable_vision_verification,
                    ),
                ),
            ]
        )

    @staticmethod
    def _bootstrap_history_for_start_stage(
        registry: GenerationToolRegistry,
        start_stage: StageStatus,
    ) -> list[LoopHistoryItem]:
        history: list[LoopHistoryItem] = []
        for tool in registry.list_tools():
            if tool.stage == start_stage:
                break
            history.append(LoopHistoryItem(tool_name=tool.name, stage=tool.stage, outcome="skipped"))
        return history

    async def _after_tool_completed(
        self,
        job: GenerationJob,
        state: PipelineState,
        stage: StageStatus,
    ) -> bool:
        await self._sync_state_to_job(job, state)

        if stage == StageStatus.OUTLINE:
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
                            "suggested_slide_role": item.get("suggested_slide_role", "narrative"),
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
                return True

        if stage == StageStatus.LAYOUT:
            await self._emit_event(
                job,
                EventType.LAYOUT_READY,
                stage=StageStatus.LAYOUT,
                message="布局选择完成",
                payload={"layouts": state.layout_selections},
            )

        return False

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
        await stage_fix_slides_once(
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

        provider_model = self._model_for_stage(stage)
        provider = self._provider_for_stage(stage)
        await self._emit_event(
            job,
            EventType.STAGE_STARTED,
            stage=stage,
            message=f"{stage.value} 阶段开始",
            payload={
                "stage_timeout_seconds": timeout,
                "started_at": start_ts,
                "provider_model": provider_model,
                "provider": provider,
            },
        )
        logger.info(
            "generation_stage_start",
            extra={
                "event": "generation_stage_start",
                "job_id": job.job_id,
                "stage": stage.value,
                "timeout_seconds": timeout,
                "provider_model": provider_model,
                "provider": provider,
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
            ended_at = now_iso()
            job.stage_results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=start_ts,
                    ended_at=ended_at,
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
        ended_at = now_iso()
        job.stage_results.append(
            StageResult(
                stage=stage,
                status="completed",
                started_at=start_ts,
                ended_at=ended_at,
                duration_ms=duration_ms,
                timeout_seconds=timeout,
                provider_model=provider_model,
                provider=provider,
            )
        )
        await self._store.save_job(job)

        await self._emit_event(
            job,
            EventType.STAGE_PROGRESS,
            stage=stage,
            message=f"{stage.value} 阶段完成",
            payload={
                "duration_ms": duration_ms,
                "started_at": start_ts,
                "ended_at": ended_at,
                "provider_model": provider_model,
                "provider": provider,
            },
        )
        logger.info(
            "generation_stage_done",
            extra={
                "event": "generation_stage_done",
                "job_id": job.job_id,
                "stage": stage.value,
                "duration_ms": duration_ms,
                "started_at": start_ts,
                "ended_at": ended_at,
                "timeout_seconds": timeout,
                "provider_model": provider_model,
                "provider": provider,
            },
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

    @staticmethod
    def _should_use_agentic_loop() -> bool:
        if not settings.enable_agentic_loop:
            return False
        model_name = str(settings.strong_model or "").strip().lower()
        if model_name.startswith("openai:"):
            return bool(str(settings.openai_api_key or "").strip())
        return False

    async def _run_selected_runtime(
        self,
        job: GenerationJob,
        state: PipelineState,
        *,
        start_stage: StageStatus,
        progress_hook,
        slide_hook,
    ) -> bool:
        if self._should_use_agentic_loop():
            return await self._run_agentic_job(
                job,
                state,
                start_stage=start_stage,
                progress_hook=progress_hook,
                slide_hook=slide_hook,
            )
        return await self._run_pipeline_job(
            job,
            state,
            start_stage=start_stage,
            progress_hook=progress_hook,
            slide_hook=slide_hook,
        )

    async def _run_agentic_job(
        self,
        job: GenerationJob,
        state: PipelineState,
        *,
        start_stage: StageStatus,
        progress_hook,
        slide_hook,
    ) -> bool:
        registry = self._build_tool_registry()
        agentic_registry = self._build_agentic_tool_registry(
            registry=registry,
            job=job,
            state=state,
            progress_hook=progress_hook,
            slide_hook=slide_hook,
        )
        try:
            loop_result = await agentic_loop(
                user_prompt=self._build_agentic_runtime_prompt(
                    job=job,
                    state=state,
                    start_stage=start_stage,
                    registry=registry,
                ),
                state=state,
                tool_definitions=agentic_registry.to_model_tools(),
                dispatch_tools=lambda calls: dispatch_tool_calls(calls, agentic_registry),
                max_turns=settings.agentic_max_turns,
            )
        except Exception:
            logger.warning(
                "agentic runtime failed; falling back to pipeline",
                extra={
                    "job_id": job.job_id,
                    "start_stage": start_stage.value,
                },
                exc_info=True,
            )
        else:
            if self._agentic_runtime_completed(job):
                logger.info(
                    "agentic runtime completed",
                    extra={
                        "job_id": job.job_id,
                        "turns": loop_result.turns,
                        "stop_reason": loop_result.stop_reason,
                    },
                )
                return True

            logger.warning(
                "agentic runtime incomplete; falling back to pipeline",
                extra={
                    "job_id": job.job_id,
                    "start_stage": start_stage.value,
                    "turns": loop_result.turns,
                    "stop_reason": loop_result.stop_reason,
                },
            )
        return await self._run_pipeline_job(
            job,
            state,
            start_stage=start_stage,
            progress_hook=progress_hook,
            slide_hook=slide_hook,
        )

    def _build_agentic_tool_registry(
        self,
        *,
        registry: GenerationToolRegistry,
        job: GenerationJob,
        state: PipelineState,
        progress_hook,
        slide_hook,
    ) -> ToolRegistry:
        tool_registry = ToolRegistry()

        for tool in registry.list_tools():
            async def _handler(_args: dict[str, Any], *, generation_tool: GenerationTool = tool) -> Any:
                await self._ensure_not_cancelled(job)
                is_verify_stage = generation_tool.stage == StageStatus.VERIFY

                if self._stage_already_completed(job, generation_tool.stage):
                    result: dict[str, Any] = {
                        "stage": generation_tool.stage.value,
                        "status": "skipped",
                        "reason": "stage already completed",
                    }
                else:
                    await self._run_stage(
                        job,
                        state,
                        stage=generation_tool.stage,
                        timeout=generation_tool.timeout_seconds(),
                        stage_coro=generation_tool.runner(state, progress_hook, slide_hook),
                    )
                    result = {"stage": generation_tool.stage.value, "status": "completed"}

                if is_verify_stage:
                    return ToolExecutionResult(
                        content=result,
                        stop_loop=True,
                        metadata={"stop_reason": "verification-complete"},
                    )
                return result

            tool_registry.register(
                ToolDef(
                    name=tool.name,
                    description=tool.description,
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=_handler,
                )
            )

        return tool_registry

    def _build_agentic_runtime_prompt(
        self,
        *,
        job: GenerationJob,
        state: PipelineState,
        start_stage: StageStatus,
        registry: GenerationToolRegistry,
    ) -> str:
        completed_stages = [
            sr.stage.value
            for sr in job.stage_results
            if sr.status == "completed"
        ]
        tool_order = ", ".join(tool.name for tool in registry.list_tools())
        return (
            "你正在控制 generation/jobs 的主运行时，需要尽量直接把当前任务推进到验证完成。\n\n"
            f"当前 start_stage：{start_stage.value}\n"
            f"已完成阶段：{', '.join(completed_stages) or 'none'}\n"
            f"可用工具顺序：{tool_order}\n"
            f"state summary：{summarize_state(state)}\n\n"
            "操作原则：\n"
            "- 优先调用尚未完成的阶段工具，避免重复执行已经完成的阶段。\n"
            "- 只要 verify_slides 完成，就停止并让控制器接管收尾。\n"
            "- 如果当前状态不足以继续，仍然尽量推进到下一个合理阶段；系统会在必要时回退到 pipeline。\n"
        )

    @staticmethod
    def _stage_already_completed(job: GenerationJob, stage: StageStatus) -> bool:
        return any(result.stage == stage and result.status == "completed" for result in job.stage_results)

    def _agentic_runtime_completed(self, job: GenerationJob) -> bool:
        return self._stage_already_completed(job, StageStatus.VERIFY)

    async def _run_pipeline_job(
        self,
        job: GenerationJob,
        state: PipelineState,
        *,
        start_stage: StageStatus,
        progress_hook,
        slide_hook,
    ) -> bool:
        registry = self._build_tool_registry()
        history: list[LoopHistoryItem] = self._bootstrap_history_for_start_stage(registry, start_stage)
        forced_stage: StageStatus | None = start_stage

        while True:
            await self._ensure_not_cancelled(job)
            if len(history) >= self._loop_planner.max_iterations():
                raise RuntimeError("generation loop exceeded max iterations")

            decision = await self._loop_planner.decide(
                state=state,
                registry=registry,
                history=history,
                forced_stage=forced_stage,
            )
            forced_stage = None

            if decision.action == "complete":
                return True

            tool = registry.get(decision.tool_name or "")
            await self._run_stage(
                job,
                state,
                stage=tool.stage,
                timeout=tool.timeout_seconds(),
                stage_coro=tool.runner(state, progress_hook, slide_hook),
            )
            history.append(LoopHistoryItem(tool_name=tool.name, stage=tool.stage))
            should_stop = await self._after_tool_completed(job, state, tool.stage)
            if should_stop:
                return False

    def _build_state(self, job: GenerationJob) -> PipelineState:
        state = PipelineState(
            raw_content=job.request.resolved_content or job.request.topic,
            source_ids=list(job.request.source_ids),
            topic=job.request.topic or job.request.title,
            template_id=job.request.template_id,
            num_pages=max(3, min(job.request.num_pages, 50)),
            job_id=job.job_id,
        )
        state.document_metadata = dict(job.document_metadata)
        # Keep source hints in metadata so downstream stages can consume them even
        # if parse stage overwrites other parse-only fields.
        try:
            source_hints = getattr(job.request, "source_hints", None)
            if source_hints:
                dump = source_hints.model_dump(mode="json") if hasattr(source_hints, "model_dump") else source_hints
                state.document_metadata.setdefault("source_hints", dump)
        except Exception:
            # Any issues with hints should never break the job.
            pass
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
