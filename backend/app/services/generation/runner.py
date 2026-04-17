"""Background job runner for generation v2."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.model_status import parse_provider
from app.models.generation import EventType, GenerationEvent, GenerationJob, JobStatus, RunMetadata, StageResult, StageStatus, now_iso
from app.models.slide import Presentation, Slide, Theme
from app.services.html_deck import normalize_html_deck
from app.services.generation.agentic import (
    AgentBuilder,
    LiteLLMModelClient,
    Message,
    Tool,
    ToolContext,
    ToolMessage,
    ToolRegistry,
    create_builtin_registry,
)
from app.services.generation.agentic.models import ModelClient, ModelResponse, normalize_litellm_model
from app.services.generation.agent_adapter import AgentOutline, outline_to_job_outline
from app.services.generation.event_bus import GenerationEventBus
from app.services.generation.job_store import GenerationJobStore
from app.services.generation.runtime_state import GenerationRuntimeState
from app.services.generation.verifier import stage_fix_slides_once, stage_verify_slides
from app.services.presentations import normalize_presentation_payload
from app.services.skill_runtime.contracts import (
    build_skill_activation_record,
    build_skill_catalog_context,
)
from app.services.skill_runtime.registry import build_skill_catalog
from app.services.slidev import (
    build_slidev_role_reference_bundle,
    finalize_slidev_deck,
)

logger = logging.getLogger(__name__)

ERROR_PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
ERROR_PROVIDER_NETWORK = "PROVIDER_NETWORK"
ERROR_PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
ERROR_CANCELLED = "CANCELLED"
ERROR_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ClassifiedError:
    error_code: str
    error_message: str
    retriable: bool


class _SubmitOutlineArgs(BaseModel):
    title: str = ""
    subtitle: str = ""
    storyline: str = ""
    items: list[dict[str, Any]]


class _SubmitPresentationArgs(BaseModel):
    presentation_id: str | None = Field(None, alias="presentationId")
    title: str = ""
    theme: dict[str, Any] | None = None
    slides: list[dict[str, Any]]

    model_config = {"populate_by_name": True}


class _SubmitHtmlDeckArgs(BaseModel):
    title: str = ""
    html: str


class _SubmitSlidevDeckArgs(BaseModel):
    title: str = ""
    markdown: str
    selected_style_id: str | None = Field(None, alias="selectedStyleId")

    model_config = {"populate_by_name": True}


AUTO_PRESENTATION_ALLOWED_BUILTIN_TOOLS: tuple[str, ...] = (
    "read_file",
    "load_skill",
)

REVIEW_OUTLINE_ALLOWED_BUILTIN_TOOLS: tuple[str, ...] = (
    "read_file",
    "load_skill",
)

TEXT_FRIENDLY_LAYOUTS: tuple[str, ...] = (
    "intro-slide",
    "intro-slide-left",
    "outline-slide",
    "outline-slide-rail",
    "section-header",
    "section-header-side",
    "bullet-with-icons",
    "bullet-with-icons-cards",
    "bullet-icons-only",
    "numbered-bullets",
    "numbered-bullets-track",
    "metrics-slide",
    "metrics-slide-band",
    "timeline",
    "two-column-compare",
    "challenge-outcome",
    "quote-slide",
    "quote-banner",
    "thank-you",
    "thank-you-contact",
)

VISUAL_LAYOUTS: tuple[str, ...] = (
    "metrics-with-image",
    "image-and-description",
)

DATA_LAYOUTS: tuple[str, ...] = (
)

# These repair types indicate the generator lost too much structure and the
# normalizer had to materially flatten or reshape the slide. Benign schema
# normalization such as outline/closing field coercion should not fail the run.
HARD_FAIL_REPAIR_TYPES: frozenset[str] = frozenset(
    {
        "bullet-with-icons-fallback-state",
    }
)


@dataclass(slots=True)
class _TracingModelCall:
    index: int
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    error: str | None = None


@dataclass(slots=True)
class _TracingModelClient:
    delegate: ModelClient
    calls: list[_TracingModelCall]

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        call = _TracingModelCall(
            index=len(self.calls) + 1,
            request=_summarize_model_request(self.delegate, messages, tools),
        )
        self.calls.append(call)
        try:
            response = await self.delegate.complete(messages, tools)
        except Exception as exc:
            call.error = f"{type(exc).__name__}: {exc}"
            raise
        call.response = _summarize_model_response(response)
        return response


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
            self._sync_run_metadata(job)
            await self._emit_event(
                job,
                EventType.JOB_STARTED,
                message="任务开始",
                payload={
                    "run_id": job.run_metadata.run_id if job.run_metadata else None,
                    "skill_id": job.request.skill_id,
                    "mode": job.mode.value,
                    "num_pages": job.request.num_pages,
                    "output_mode": job.output_mode.value,
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

            if not self._job_has_agent_workspace(job):
                raise ValueError("Agent workspace is not initialized for this job.")

            completed = await self._run_agentic_job(
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
                self._write_runner_trace(job, state)
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
            self._sync_run_metadata(job, state=state, latency_ms=elapsed_ms)
            self._write_runner_trace(job, state)
            job.updated_at = now_iso()
            if job.request.session_id:
                from app.services.sessions import session_store
                html_output = state.document_metadata.get("agent_outputs", {}).get("html_deck")
                slidev_output = state.document_metadata.get("agent_outputs", {}).get("slidev_deck")
                slidev_build_output = state.document_metadata.get("agent_outputs", {}).get("slidev_build")
                saved = await session_store.save_presentation(
                    session_id=job.request.session_id,
                    payload=job.presentation,
                    is_snapshot=False,
                    output_mode=job.output_mode.value,
                    html_deck=(
                        {
                            "html": html_output.get("html"),
                            "expected_slide_count": len(state.slides),
                        }
                        if job.output_mode.value == "html" and isinstance(html_output, dict)
                        else None
                    ),
                    slidev_deck=(
                        {
                            "markdown": slidev_output.get("markdown"),
                            "meta": slidev_output.get("meta"),
                            "selected_style_id": slidev_output.get("selected_style_id"),
                        }
                        if job.output_mode.value == "slidev" and isinstance(slidev_output, dict)
                        else None
                    ),
                    slidev_build=(
                        {
                            "build_root": slidev_build_output.get("build_root"),
                            "entry_path": slidev_build_output.get("entry_path"),
                            "slide_count": slidev_build_output.get("slide_count"),
                        }
                        if job.output_mode.value == "slidev" and isinstance(slidev_build_output, dict)
                        else None
                    ),
                )
                if isinstance(saved.get("presentation"), dict):
                    job.presentation = saved["presentation"]
            await self._store.save_job(job)
            if job.request.session_id:
                from app.services.sessions import session_store

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
                    "run_id": job.run_metadata.run_id if job.run_metadata else None,
                    "skill_id": job.request.skill_id,
                    "presentation": job.presentation,
                    "output_mode": job.output_mode.value,
                    "artifacts": job.presentation.get("artifacts") if isinstance(job.presentation, dict) else {},
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
            self._sync_run_metadata(job, state=state, error_class=ERROR_CANCELLED)
            self._write_runner_trace(job, state)
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
            )
            elapsed_ms = int((time.monotonic() - job_started_monotonic) * 1000)
            job.status = JobStatus.FAILED
            job.error = f"[{classified.error_code}] {classified.error_message}"
            job.current_stage = None
            self._sync_run_metadata(
                job,
                state=state,
                latency_ms=elapsed_ms,
                error_class=classified.error_code,
            )
            self._write_runner_trace(job, state)
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

    async def _after_tool_completed(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
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
                self._write_runner_trace(job, state)
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
            per_slide_timeout=0.0,
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
        self._write_runner_trace(job, self._build_state(job))
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
        self._write_runner_trace(job, self._build_state(job))
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
        state: GenerationRuntimeState,
        stage: StageStatus,
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
                "provider_model": provider_model,
                "provider": provider,
            },
        )

        try:
            await stage_coro
        except Exception as e:
            classified = self._classify_generation_error(e, stage=stage)
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
                "provider_model": provider_model,
                "provider": provider,
            },
        )

    def _classify_generation_error(
        self,
        error: Exception,
        stage: StageStatus | None,
    ) -> ClassifiedError:
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
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "error": classified.error_message,
            "error_code": classified.error_code,
            "error_message": classified.error_message,
            "retriable": classified.retriable,
            "timeout_seconds": None,
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

    async def _sync_state_to_job(self, job: GenerationJob, state: GenerationRuntimeState) -> None:
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
        self._write_runner_trace(job, state)
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
        existing = job.presentation if isinstance(job.presentation, dict) else {}
        agent_outputs = job.document_metadata.get("agent_outputs") if isinstance(job.document_metadata, dict) else {}
        generated = agent_outputs.get("presentation") if isinstance(agent_outputs, dict) else {}

        title = str(existing.get("title") or generated.get("title") or job.request.title or "新演示文稿")
        presentation_id = existing.get("presentationId") or generated.get("presentationId")
        if not isinstance(presentation_id, str) or not presentation_id.strip():
            presentation_id = f"pres-{uuid4().hex[:8]}"
        theme_payload = existing.get("theme") or generated.get("theme")
        theme = Theme.model_validate(theme_payload) if isinstance(theme_payload, dict) else None
        payload = Presentation(
            presentationId=presentation_id,
            title=title,
            theme=theme,
            slides=slides,
        ).model_dump(mode="json", by_alias=True, exclude_none=True)
        output_mode = str(existing.get("outputMode") or job.output_mode.value).strip()
        if output_mode:
            payload["outputMode"] = output_mode
        artifacts = existing.get("artifacts")
        if isinstance(artifacts, dict) and artifacts:
            payload["artifacts"] = deepcopy(artifacts)
        return payload

    async def _persist_partial_presentation(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
    ) -> tuple[bool, dict | None]:
        if not job.slides and not state.slides:
            return False, None

        if not job.slides:
            await self._sync_state_to_job(job, state)
        if not job.slides:
            return False, None

        presentation_payload = self._build_presentation_payload(
            job,
            [Slide.model_validate(slide) for slide in job.slides],
        )
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
    def _job_has_agent_workspace(job: GenerationJob) -> bool:
        root = (job.document_metadata.get("agent_workspace") or {}).get("root")
        return isinstance(root, str) and bool(root.strip())

    async def _run_agentic_job(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        start_stage: StageStatus,
        progress_hook,
        slide_hook,
    ) -> bool:
        if start_stage in {StageStatus.PARSE}:
            await self._run_stage(
                job,
                state,
                stage=StageStatus.PARSE,
                stage_coro=self._stage_prepare_agent_workspace(job, state, progress_hook=progress_hook),
            )

        if (
            job.mode.value == "review_outline"
            and start_stage in {StageStatus.PARSE, StageStatus.OUTLINE}
        ):
            await self._run_stage(
                job,
                state,
                stage=StageStatus.OUTLINE,
                stage_coro=self._stage_generate_agent_outline(job, state, progress_hook=progress_hook),
            )
            should_stop = await self._after_tool_completed(job, state, StageStatus.OUTLINE)
            if should_stop:
                return False

        if start_stage in {
            StageStatus.PARSE,
            StageStatus.OUTLINE,
            StageStatus.LAYOUT,
            StageStatus.SLIDES,
            StageStatus.ASSETS,
            StageStatus.VERIFY,
        }:
            await self._run_stage(
                job,
                state,
                stage=StageStatus.SLIDES,
                stage_coro=self._stage_generate_agent_slides(
                    job,
                    state,
                    progress_hook=progress_hook,
                    slide_hook=slide_hook,
                ),
            )
            await self._sync_state_to_job(job, state)

        await self._run_stage(
            job,
            state,
            stage=StageStatus.VERIFY,
            stage_coro=stage_verify_slides(
                state,
                progress=progress_hook,
                enable_vision=settings.enable_vision_verification,
            ),
        )
        await self._sync_state_to_job(job, state)
        return True

    async def _stage_prepare_agent_workspace(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        progress_hook,
    ) -> None:
        workspace_meta = dict(job.document_metadata.get("agent_workspace") or {})
        state.document_metadata.setdefault("agent_workspace", workspace_meta)
        if progress_hook:
            await progress_hook("parse", 1, 3, "准备 Agent 工作区与素材清单...")
        brief = self._build_local_source_brief(job)
        state.document_metadata["source_brief"] = brief
        if progress_hook:
            await progress_hook("parse", 2, 3, "整理本地素材摘要与结构线索...")
            await progress_hook("parse", 3, 3, "工作区已准备完成。")

    async def _stage_generate_agent_outline(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        progress_hook,
    ) -> None:
        if progress_hook:
            await progress_hook("outline", 1, 3, "Agent 正在阅读素材并规划演示结构...")
        outline = await self._generate_outline_with_agent(job, state)
        state.outline = outline_to_job_outline(outline)
        state.document_metadata.setdefault("agent_outputs", {})
        state.document_metadata["agent_outputs"]["outline"] = outline.model_dump(mode="json", by_alias=True)
        if progress_hook:
            await progress_hook("outline", 3, 3, "Agent 大纲已提交。")

    async def _stage_generate_agent_slides(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        progress_hook,
        slide_hook,
    ) -> None:
        if progress_hook:
            await progress_hook("slides", 1, 3, "Agent 正在生成完整演示内容...")
        if job.output_mode.value == "html":
            html_payload, presentation = await self._generate_html_deck_with_agent(job, state)
            state.layout_selections = [
                {
                    "slide_number": index + 1,
                    "layout_id": slide.layout_id or slide.layout_type,
                }
                for index, slide in enumerate(presentation.slides)
            ]
            state.slides = list(presentation.slides)
            state.slide_contents = [
                {
                    "slide_number": index + 1,
                    "layout_id": slide.layout_id or slide.layout_type,
                    "content_data": slide.content_data or {},
                }
                for index, slide in enumerate(presentation.slides)
            ]
            state.document_metadata.setdefault("agent_outputs", {})
            state.document_metadata["agent_outputs"]["html_deck"] = {
                "title": html_payload["title"],
                "html": html_payload["html"],
                "meta": html_payload["meta"],
            }
            state.document_metadata["agent_outputs"]["presentation"] = presentation.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            for index, slide in enumerate(presentation.slides):
                if slide_hook:
                    await slide_hook({"slide_index": index, "slide": slide.model_dump(mode="json", by_alias=True)})
        elif job.output_mode.value == "slidev":
            slidev_payload, presentation = await self._generate_slidev_deck_with_agent(job, state)
            state.layout_selections = [
                {
                    "slide_number": index + 1,
                    "layout_id": "slidev",
                }
                for index, _slide in enumerate(presentation.slides)
            ]
            state.slides = list(presentation.slides)
            state.slide_contents = [
                {
                    "slide_number": index + 1,
                    "layout_id": "slidev",
                    "content_data": slide.content_data or {},
                }
                for index, slide in enumerate(presentation.slides)
            ]
            state.document_metadata.setdefault("agent_outputs", {})
            state.document_metadata["agent_outputs"]["slidev_deck"] = {
                "title": slidev_payload["title"],
                "markdown": slidev_payload["markdown"],
                "meta": slidev_payload["meta"],
                "selected_style_id": slidev_payload["selected_style_id"],
                "selected_style": slidev_payload["selected_style"],
                "selected_theme": slidev_payload["selected_theme"],
            }
            state.document_metadata["agent_outputs"]["slidev_build"] = {
                "build_root": slidev_payload["build_root"],
                "entry_path": slidev_payload["entry_path"],
                "slide_count": slidev_payload["meta"]["slide_count"],
            }
            state.document_metadata["agent_outputs"]["presentation"] = presentation.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            for index, slide in enumerate(presentation.slides):
                if slide_hook:
                    await slide_hook({"slide_index": index, "slide": slide.model_dump(mode="json", by_alias=True)})
        else:
            submitted_payload, presentation = await self._generate_presentation_with_agent(job, state)
            audit = self._audit_generated_presentation(job, submitted_payload, presentation)
            if audit["issues"]:
                raise ValueError("Presentation audit failed: " + " | ".join(audit["issues"]))
            expected = max(3, min(job.request.num_pages, settings.max_slide_pages))
            if len(presentation.slides) != expected:
                raise ValueError(
                    f"Presentation slide count mismatch after correction: expected {expected}, got {len(presentation.slides)}"
                )
            state.layout_selections = [
                {
                    "slide_number": index + 1,
                    "layout_id": slide.layout_id or slide.layout_type,
                }
                for index, slide in enumerate(presentation.slides)
            ]
            state.slides = list(presentation.slides)
            state.slide_contents = [
                {
                    "slide_number": int(str(slide.slide_id).replace("slide-", "") or "0"),
                    "layout_id": slide.layout_id or slide.layout_type,
                    "content_data": slide.content_data or {},
                }
                for slide in presentation.slides
            ]
            state.document_metadata.setdefault("agent_outputs", {})
            state.document_metadata["agent_outputs"]["presentation"] = presentation.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            state.document_metadata["agent_outputs"]["presentation_audit"] = audit
            for key in ("deck", "deck_audit", "deck_metadata"):
                state.document_metadata["agent_outputs"].pop(key, None)
            for index, slide in enumerate(presentation.slides):
                if slide_hook:
                    await slide_hook({"slide_index": index, "slide": slide.model_dump(mode="json", by_alias=True)})
        if progress_hook:
            await progress_hook("slides", 3, 3, "Agent 已直接提交当前编辑器可用的演示结果。")

    def _build_state(self, job: GenerationJob) -> GenerationRuntimeState:
        state = GenerationRuntimeState(
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

    def _debug_dir_for_job(self, job: GenerationJob) -> Path:
        return self._workspace_root_for_job(job) / "artifacts" / "debug"

    def _ensure_debug_index(self, state: GenerationRuntimeState, job: GenerationJob) -> dict[str, Any]:
        debug_dir = self._debug_dir_for_job(job)
        debug_dir.mkdir(parents=True, exist_ok=True)
        index = state.document_metadata.setdefault("agent_debug", {})
        index["root"] = str(debug_dir)
        index.setdefault("files", [])
        index.setdefault("runs", {})
        return index

    def _register_debug_file(self, state: GenerationRuntimeState, job: GenerationJob, file_name: str) -> Path:
        debug_dir = self._debug_dir_for_job(job)
        index = self._ensure_debug_index(state, job)
        files = index.setdefault("files", [])
        if file_name not in files:
            files.append(file_name)
            files.sort()
        return debug_dir / file_name

    def _write_debug_json(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        file_name: str,
        payload: dict[str, Any] | list[Any],
    ) -> Path:
        path = self._register_debug_file(state, job, file_name)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def _append_debug_ndjson(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        file_name: str,
        payloads: list[dict[str, Any]],
    ) -> Path:
        path = self._register_debug_file(state, job, file_name)
        with path.open("a", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        return path

    def _write_agent_run_debug(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        stage_name: str,
        prompt: str,
        session,
        result,
        traced_model: _TracingModelClient,
        submitted_payload: dict[str, Any] | None,
        attempt: int,
    ) -> None:
        calls = traced_model.calls
        request_payload = {
            "stage": stage_name,
            "attempt": attempt,
            "model": _summarize_model_identity(traced_model.delegate),
            "call_count": len(calls),
            "calls": [{"index": call.index, **call.request} for call in calls],
        }
        response_payload = {
            "stage": stage_name,
            "attempt": attempt,
            "model": _summarize_model_identity(traced_model.delegate),
            "call_count": len(calls),
            "calls": [
                {
                    "index": call.index,
                    "response": call.response,
                    "error": call.error,
                }
                for call in calls
            ],
        }
        session_payload = {
            "stage": stage_name,
            "attempt": attempt,
            "prompt": prompt,
            "turns": result.turns,
            "stop_reason": result.stop_reason,
            "error": result.error,
            "submitted_payload": submitted_payload,
            "messages": [_serialize_message(message) for message in result.messages],
            "tool_results": [_serialize_tool_result(item) for item in result.tool_results],
            "context_markers": list(result.context_markers),
            "compact_events": list(result.compact_events),
            "active_skills": list(getattr(session, "active_skills", []) or []),
            "todo_items": list(getattr(session, "todo_items", []) or []),
            "tasks": list(getattr(session, "tasks", []) or []),
            "current_task": getattr(session, "current_task", None),
        }
        self._write_debug_json(job, state, f"model-{stage_name}-request.json", request_payload)
        self._write_debug_json(job, state, f"model-{stage_name}-response.json", response_payload)
        self._write_debug_json(job, state, f"session-{stage_name}.json", session_payload)

        tool_trace_rows = [
            {
                "ts": now_iso(),
                "stage": stage_name,
                "attempt": attempt,
                "result": _serialize_tool_result(item),
            }
            for item in result.tool_results
        ]
        if tool_trace_rows:
            self._append_debug_ndjson(job, state, "tool-trace.ndjson", tool_trace_rows)

        index = self._ensure_debug_index(state, job)
        runs = index.setdefault("runs", {})
        runs[stage_name] = {
            "attempt": attempt,
            "turns": result.turns,
            "stop_reason": result.stop_reason,
            "error": result.error,
            "call_count": len(calls),
            "submitted": bool(submitted_payload),
            "calls": [
                {
                    "index": call.index,
                    "response": call.response,
                    "error": call.error,
                }
                for call in calls
            ],
        }
        if tool_trace_rows:
            tool_trace = index.setdefault("tool_trace", [])
            tool_trace.extend(tool_trace_rows)

    def _record_activated_skill(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        *,
        skill_name: str | None,
        source: str,
        reason: str,
    ) -> None:
        activation = build_skill_activation_record(
            skill_name,
            source=source,
            reason=reason,
        )
        if activation is None:
            return
        activated = state.document_metadata.setdefault("activated_skills", [])
        if any(
            item.get("skill_id") == activation["skill_id"]
            and item.get("source") == activation["source"]
            and item.get("reason") == activation["reason"]
            for item in activated
            if isinstance(item, dict)
        ):
            return
        activated.append(activation)

    async def _activate_base_skill(
        self,
        *,
        job: GenerationJob,
        state: GenerationRuntimeState,
        session,
    ) -> list[Any]:
        skill_name = job.request.skill_id
        if not skill_name:
            return []
        result = await session.load_skill(skill_name)
        if result.stop_reason != "completed":
            raise RuntimeError(result.error or f"Failed to activate base skill: {skill_name}")
        self._record_activated_skill(
            job,
            state,
            skill_name=skill_name,
            source="harness",
            reason="output_mode_default",
        )
        return list(result.tool_results)

    def _write_runner_trace(self, job: GenerationJob, state: GenerationRuntimeState) -> None:
        if not self._job_has_agent_workspace(job):
            return
        trace_payload = {
            "job_id": job.job_id,
            "status": job.status.value,
            "current_stage": job.current_stage.value if job.current_stage else None,
            "stage_results": [result.model_dump(mode="json") for result in job.stage_results],
            "outline_ready": bool(state.outline),
            "slide_count": len(state.slides) if state.slides else len(job.slides),
            "issue_count": len(state.verification_issues),
            "failed_slide_indices": list(state.failed_slide_indices),
            "run_metadata": job.run_metadata.model_dump(mode="json") if job.run_metadata else None,
            "agent_debug": deepcopy(state.document_metadata.get("agent_debug") or {}),
        }
        self._write_debug_json(job, state, "runner-trace.json", trace_payload)

    def _sync_run_metadata(
        self,
        job: GenerationJob,
        *,
        state: GenerationRuntimeState | None = None,
        latency_ms: int | None = None,
        error_class: str | None = None,
    ) -> None:
        payload = job.run_metadata.model_dump(mode="json") if job.run_metadata else {}
        payload["run_id"] = payload.get("run_id") or f"run-{job.job_id}"
        payload["skill_id"] = job.request.skill_id
        payload["base_skill_id"] = job.request.skill_id
        payload["output_mode"] = job.output_mode.value
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if error_class:
            payload["error_class"] = error_class
        if state is not None:
            payload["artifact_refs"] = deepcopy(state.document_metadata.get("agent_outputs") or {})
            payload["token_usage"] = _aggregate_model_usage(
                (state.document_metadata.get("agent_debug") or {}).get("runs") or {}
            )
            payload["tool_events"] = list((state.document_metadata.get("agent_debug") or {}).get("tool_trace") or [])
            activated = list(state.document_metadata.get("activated_skills") or [])
            for event in payload["tool_events"]:
                result = event.get("result") if isinstance(event, dict) else None
                if not isinstance(result, dict):
                    continue
                if str(result.get("tool_name") or "") != "load_skill" or bool(result.get("is_error")):
                    continue
                content = result.get("content")
                if not isinstance(content, dict):
                    continue
                activation = build_skill_activation_record(
                    str(content.get("name") or "").strip() or None,
                    source="agent",
                    reason="task_request",
                )
                if activation is None:
                    continue
                if any(
                    item.get("skill_id") == activation["skill_id"] and item.get("source") == activation["source"]
                    for item in activated
                    if isinstance(item, dict)
                ):
                    continue
                activated.append(activation)
            payload["activated_skills"] = activated
        job.run_metadata = RunMetadata.model_validate(payload)
        job.document_metadata["run"] = deepcopy(payload)

    def _build_tool_registry(self, workspace_root: Path, allowed_builtin_tools: tuple[str, ...]) -> ToolRegistry:
        registry = create_builtin_registry(workspace_root, permissive_mode=False)
        selected = {name: registry.tools[name] for name in allowed_builtin_tools if name in registry.tools}
        return ToolRegistry(tools=selected)

    def _build_local_source_brief(self, job: GenerationJob) -> dict[str, Any]:
        workspace_root = self._workspace_root_for_job(job)
        artifacts_dir = workspace_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = workspace_root / "sources" / "manifest.json"
        manifest_payload: dict[str, Any] = {}
        if manifest_path.exists():
            with suppress(Exception):
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        source_cards: list[dict[str, Any]] = []
        for source in list(manifest_payload.get("sources") or [])[:6]:
            relative_path = str(source.get("workspace_text_path") or "").strip()
            source_path = workspace_root / relative_path if relative_path else None
            text = ""
            if source_path and source_path.exists():
                with suppress(Exception):
                    text = source_path.read_text(encoding="utf-8")
            source_cards.append(
                {
                    "id": source.get("id"),
                    "name": source.get("name"),
                    "fileCategory": source.get("fileCategory"),
                    "workspace_text_path": relative_path or None,
                    "headings": _extract_source_headings(text),
                    "key_passages": _extract_source_passages(text),
                }
            )

        recommended_layouts = self._allowed_layout_palette(job)
        brief_payload = {
            "topic": job.request.topic or job.request.title,
            "num_pages": job.request.num_pages,
            "source_count": len(source_cards),
            "recommended_layouts": recommended_layouts,
            "sources": source_cards,
        }
        markdown = _render_source_brief_markdown(brief_payload)
        json_path = artifacts_dir / "source-brief.json"
        md_path = artifacts_dir / "source-brief.md"
        json_path.write_text(json.dumps(brief_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        return {
            "json_path": str(json_path),
            "markdown_path": str(md_path),
            "recommended_layouts": recommended_layouts,
            "summary_markdown": markdown,
            "sources": source_cards,
        }

    def _allowed_layout_palette(self, job: GenerationJob, *, include_visual: bool = False) -> list[str]:
        palette = list(TEXT_FRIENDLY_LAYOUTS)
        hints = job.document_metadata.get("agent_workspace", {}).get("source_hints") or {}
        images = int(hints.get("images") or 0)
        data = int(hints.get("data") or 0)
        if include_visual or images > 0:
            palette.extend(VISUAL_LAYOUTS)
        if data > 0:
            palette.extend(DATA_LAYOUTS)
        return sorted(set(palette))

    def _audit_generated_presentation(
        self,
        job: GenerationJob,
        presentation_payload: dict[str, Any],
        presentation: Presentation,
    ) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []
        slides = presentation.slides
        raw_slides = list(presentation_payload.get("slides") or []) if isinstance(
            presentation_payload.get("slides"),
            list,
        ) else []
        layout_ids = [slide.layout_id or slide.layout_type for slide in slides]
        layout_counts: dict[str, int] = {}
        for layout_id in layout_ids:
            layout_counts[layout_id] = layout_counts.get(layout_id, 0) + 1
        dominant_layout = max(layout_counts.values(), default=0)
        if job.request.num_pages >= 6 and dominant_layout > max(2, job.request.num_pages // 2):
            warnings.append("布局重复过多：请增加版式变化，不要让大多数页面都使用同一类 layout。")
        if job.request.num_pages >= 5 and len(set(layout_ids)) < 3:
            warnings.append("布局种类过少：至少使用 3 种不同 layout。")

        title_counts: dict[str, int] = {}
        subtitle_counts: dict[str, int] = {}
        for index, slide in enumerate(slides):
            raw_slide = raw_slides[index] if index < len(raw_slides) and isinstance(raw_slides[index], dict) else {}
            content = raw_slide.get("contentData") if isinstance(raw_slide.get("contentData"), dict) else {}
            title = _text_field(content, "title")
            subtitle = _text_field(content, "subtitle")
            if title:
                title_counts[title] = title_counts.get(title, 0) + 1
            if subtitle:
                subtitle_counts[subtitle] = subtitle_counts.get(subtitle, 0) + 1
            layout_id = slide.layout_id or slide.layout_type
            if layout_id in {"bullet-with-icons", "bullet-with-icons-cards"}:
                bullet_items = _list_field(content, "items")
                if len(bullet_items) < 3:
                    warnings.append(f"{title or slide.slide_id}: bullet 类页面最好提供 3-4 个 items。")
                if any(not _text_field(item, "description") for item in bullet_items if isinstance(item, dict)):
                    warnings.append(f"{title or slide.slide_id}: bullet 类页面的 items.description 为空。")
            if layout_id in {"outline-slide", "outline-slide-rail"}:
                sections = _list_field(content, "sections")
                if any(not _text_field(section, "description") for section in sections if isinstance(section, dict)):
                    warnings.append(f"{title or slide.slide_id}: outline 类页面的 sections.description 为空。")
            if layout_id in {"numbered-bullets", "numbered-bullets-track"}:
                items = _list_field(content, "items")
                if len(items) < 3:
                    warnings.append(f"{title or slide.slide_id}: process 类页面最好至少有 3 个 items。")
                if any(not _text_field(item, "description") for item in items if isinstance(item, dict)):
                    warnings.append(f"{title or slide.slide_id}: process 类页面的 items.description 为空。")
            if layout_id in {"thank-you", "thank-you-contact"} and not (
                _text_field(content, "subtitle") or _text_field(content, "contact")
            ):
                warnings.append(f"{title or slide.slide_id}: closing 页面目前只有标题。")
            if layout_id in {"quote-slide", "quote-banner"} and not _text_field(content, "quote"):
                warnings.append(f"{title or slide.slide_id}: highlight 页面缺少 quote。")
            if layout_id == "two-column-compare" and not (
                isinstance(content.get("left"), dict) and isinstance(content.get("right"), dict)
            ):
                warnings.append(f"{title or slide.slide_id}: comparison 页面缺少 left/right。")
            if layout_id == "challenge-outcome":
                entries = _list_field(content, "items")
                if len(entries) < 2:
                    warnings.append(f"{title or slide.slide_id}: challenge-outcome 页面最好有 2 组以上 challenge/outcome。")

        repeated_titles = sorted(title for title, count in title_counts.items() if count > 1)
        if repeated_titles:
            warnings.append("标题重复过多：" + " / ".join(repeated_titles[:4]))
        repeated_subtitles = sorted(title for title, count in subtitle_counts.items() if count > 1)
        if repeated_subtitles:
            warnings.append("副标题重复过多：" + " / ".join(repeated_subtitles[:4]))

        _normalized, _changed, report = normalize_presentation_payload(presentation_payload)
        repair_types = sorted(set(report.get("repair_types") or []))
        invalid_slide_count = int(report.get("invalid_slide_count") or 0)
        if invalid_slide_count > 0:
            issues.append(f"存在 {invalid_slide_count} 页结构无效，无法安全落盘。")
        noisy = sorted(HARD_FAIL_REPAIR_TYPES.intersection(repair_types))
        if noisy:
            warnings.append("模板修复噪声偏高：" + " / ".join(noisy))

        return {
            "issues": issues,
            "warnings": warnings,
            "layout_ids": layout_ids,
            "repair_types": repair_types,
            "invalid_slide_count": invalid_slide_count,
            "repaired_slide_count": int(report.get("repaired_slide_count") or 0),
        }

    async def _generate_outline_with_agent(self, job: GenerationJob, state: GenerationRuntimeState) -> AgentOutline:
        payload_holder: dict[str, Any] = {}
        agent, traced_model = self._build_generation_agent(
            job=job,
            extra_tools=[self._make_outline_submit_tool(payload_holder)],
            system_prompt=self._build_agent_outline_prompt(job, state),
            allowed_builtin_tools=REVIEW_OUTLINE_ALLOWED_BUILTIN_TOOLS,
        )
        session = agent.start_session()
        preload_tool_results = await self._activate_base_skill(job=job, state=state, session=session)
        expected = max(3, min(job.request.num_pages, settings.max_slide_pages))
        for attempt in range(2):
            prompt = (
                self._build_agent_outline_user_prompt(job)
                if attempt == 0
                else (
                    f"上一次提交的大纲不满足要求。请重新提交，必须严格输出 {expected} 页，"
                    "并为每页补齐 role / objective / keyPoints / contentHints，再次调用 submit_outline。"
                )
            )
            result = await session.send(prompt)
            if attempt == 0 and preload_tool_results:
                result.tool_results = [*preload_tool_results, *result.tool_results]
            self._write_agent_run_debug(
                job,
                state,
                stage_name="outline",
                prompt=prompt,
                session=session,
                result=result,
                traced_model=traced_model,
                submitted_payload=payload_holder.get("outline"),
                attempt=attempt + 1,
            )
            outline = self._extract_outline_submission(payload_holder)
            if outline is None:
                raise RuntimeError(result.error or "Agent did not submit an outline.")
            if len(outline.items) == expected:
                return outline
            payload_holder.clear()
        raise ValueError(f"Outline item count mismatch: expected {expected}")

    async def _generate_presentation_with_agent(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
    ) -> tuple[dict[str, Any], Presentation]:
        payload_holder: dict[str, Any] = {}
        agent, traced_model = self._build_generation_agent(
            job=job,
            extra_tools=[self._make_presentation_submit_tool(payload_holder)],
            system_prompt=self._build_agent_presentation_prompt(job, state),
            allowed_builtin_tools=AUTO_PRESENTATION_ALLOWED_BUILTIN_TOOLS,
        )
        session = agent.start_session()
        preload_tool_results = await self._activate_base_skill(job=job, state=state, session=session)
        expected = max(3, min(job.request.num_pages, settings.max_slide_pages))
        last_issues: list[str] = []
        for attempt in range(3):
            prompt = (
                self._build_agent_presentation_user_prompt(job, state)
                if attempt == 0
                else self._build_agent_presentation_retry_prompt(expected, last_issues, output_mode="structured")
            )
            result = await session.send(prompt)
            if attempt == 0 and preload_tool_results:
                result.tool_results = [*preload_tool_results, *result.tool_results]
            self._write_agent_run_debug(
                job,
                state,
                stage_name="presentation",
                prompt=prompt,
                session=session,
                result=result,
                traced_model=traced_model,
                submitted_payload=payload_holder.get("presentation"),
                attempt=attempt + 1,
            )
            extracted = self._extract_presentation_submission(job, payload_holder)
            if extracted is None:
                raise RuntimeError(result.error or "Agent did not submit a presentation.")
            presentation_payload, presentation = extracted
            audit = self._audit_generated_presentation(job, presentation_payload, presentation)
            if len(presentation.slides) == expected and not audit["issues"]:
                return presentation_payload, presentation
            last_issues = list(audit["issues"])
            if len(presentation.slides) != expected:
                last_issues.insert(
                    0,
                    f"页数错误：必须严格输出 {expected} 页，当前是 {len(presentation.slides)} 页。",
                )
            payload_holder.clear()
        if last_issues:
            raise ValueError("Presentation audit failed: " + " | ".join(last_issues))
        raise ValueError(f"Presentation slide count mismatch: expected {expected}")

    async def _generate_html_deck_with_agent(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
    ) -> tuple[dict[str, Any], Presentation]:
        payload_holder: dict[str, Any] = {}
        agent, traced_model = self._build_generation_agent(
            job=job,
            extra_tools=[self._make_html_deck_submit_tool(payload_holder)],
            system_prompt=self._build_agent_presentation_prompt(job, state),
            allowed_builtin_tools=AUTO_PRESENTATION_ALLOWED_BUILTIN_TOOLS,
        )
        session = agent.start_session()
        preload_tool_results = await self._activate_base_skill(job=job, state=state, session=session)
        expected = max(3, min(job.request.num_pages, settings.max_slide_pages))
        for attempt in range(3):
            prompt = (
                self._build_agent_presentation_user_prompt(job, state)
                if attempt == 0
                else self._build_agent_presentation_retry_prompt(
                    expected,
                    [
                        "必须输出可直接播放的 Reveal HTML 文件。",
                        f"必须严格包含 {expected} 个 <section> 页面。",
                        "每个页面都要有稳定的 data-slide-id 和 data-slide-title。",
                    ],
                    output_mode="html",
                )
            )
            result = await session.send(prompt)
            if attempt == 0 and preload_tool_results:
                result.tool_results = [*preload_tool_results, *result.tool_results]
            self._write_agent_run_debug(
                job,
                state,
                stage_name="presentation",
                prompt=prompt,
                session=session,
                result=result,
                traced_model=traced_model,
                submitted_payload=payload_holder.get("html_deck"),
                attempt=attempt + 1,
            )
            extracted = self._extract_html_deck_submission(job, payload_holder)
            if extracted is not None and len(extracted[1].slides) == expected:
                return extracted
            payload_holder.clear()
        raise RuntimeError("Agent did not submit a valid HTML deck.")

    async def _generate_slidev_deck_with_agent(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
    ) -> tuple[dict[str, Any], Presentation]:
        payload_holder: dict[str, Any] = {}
        agent, traced_model = self._build_generation_agent(
            job=job,
            extra_tools=[self._make_slidev_deck_submit_tool(payload_holder)],
            system_prompt=self._build_agent_presentation_prompt(job, state),
            allowed_builtin_tools=AUTO_PRESENTATION_ALLOWED_BUILTIN_TOOLS,
        )
        session = agent.start_session()
        preload_tool_results = await self._activate_base_skill(job=job, state=state, session=session)
        expected = max(3, min(job.request.num_pages, settings.max_slide_pages))
        for attempt in range(3):
            prompt = (
                self._build_agent_presentation_user_prompt(job, state)
                if attempt == 0
                else self._build_agent_presentation_retry_prompt(
                    expected,
                    [
                        "必须输出可被 slidev build 编译的完整 Slidev markdown deck。",
                        f"必须严格包含 {expected} 页，且由全局 frontmatter + Slidev 页面分隔组成。",
                        "必须只通过 submit_slidev_deck 提交 markdown 和 selected_style_id。",
                    ],
                    output_mode="slidev",
                )
            )
            result = await session.send(prompt)
            if attempt == 0 and preload_tool_results:
                result.tool_results = [*preload_tool_results, *result.tool_results]
            self._write_agent_run_debug(
                job,
                state,
                stage_name="presentation",
                prompt=prompt,
                session=session,
                result=result,
                traced_model=traced_model,
                submitted_payload=payload_holder.get("slidev_deck"),
                attempt=attempt + 1,
            )
            extracted = await self._extract_slidev_deck_submission(job, state, payload_holder)
            if extracted is not None and len(extracted[1].slides) == expected:
                return extracted
            payload_holder.clear()
        raise RuntimeError("Agent did not submit a valid Slidev deck.")

    def _build_generation_agent(
        self,
        *,
        job: GenerationJob,
        extra_tools: list[Tool],
        system_prompt: str,
        allowed_builtin_tools: tuple[str, ...],
    ) -> tuple[Any, _TracingModelClient]:
        workspace_root = self._workspace_root_for_job(job)
        builder = AgentBuilder.from_project(workspace_root)
        traced_model = _TracingModelClient(delegate=self._create_agent_model_client(), calls=[])
        builder.with_model_client(traced_model)
        builder.with_system_prompt(system_prompt)
        builder.with_max_turns(settings.agentic_max_turns)
        builder.with_auto_compact(True)
        builder.with_compact_token_threshold(6000)
        builder.with_compact_tail_turns(2)
        builder.with_permissive_tools(False)
        builder.skill_catalog = build_skill_catalog(settings.project_root)
        builder.tool_registry = self._build_tool_registry(workspace_root, allowed_builtin_tools)
        for tool in extra_tools:
            builder.register_tool(tool)
        return builder.build(), traced_model

    def _create_agent_model_client(self):
        model_name = str(settings.strong_model or "").strip()
        provider = parse_provider(model_name)
        api_key: str | None = None
        api_base: str | None = None
        if provider == "openai":
            api_key = str(settings.openai_api_key or "").strip() or None
            api_base = str(settings.openai_base_url or "").strip() or None
        elif provider == "anthropic":
            api_key = str(settings.anthropic_api_key or "").strip() or None
        elif provider == "google-gla":
            api_key = str(settings.google_api_key or "").strip() or None
        elif provider == "deepseek":
            api_key = str(settings.deepseek_api_key or "").strip() or None
        elif provider == "openrouter":
            api_key = str(settings.openrouter_api_key or "").strip() or None
        return LiteLLMModelClient(
            model=model_name,
            api_key=api_key,
            api_base=api_base,
        )

    def _make_outline_submit_tool(self, payload_holder: dict[str, Any]) -> Tool:
        async def _handler(args: _SubmitOutlineArgs, context: ToolContext) -> dict[str, Any]:
            outline = AgentOutline.model_validate(args.model_dump(mode="python"))
            payload = outline.model_dump(mode="json", by_alias=True)
            payload_holder["outline"] = payload
            artifacts_dir = context.workspace_root / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "outline.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "status": "ok",
                "item_count": len(outline.items),
                "path": str((artifacts_dir / "outline.json").resolve()),
            }

        return Tool(
            name="submit_outline",
            description="Submit the reviewed outline as structured JSON. Call this exactly once when the outline is ready.",
            args_model=_SubmitOutlineArgs,
            handler=_handler,
            source="embedded",
        )

    def _make_presentation_submit_tool(self, payload_holder: dict[str, Any]) -> Tool:
        async def _handler(args: _SubmitPresentationArgs, context: ToolContext) -> dict[str, Any]:
            payload = args.model_dump(mode="json", by_alias=True, exclude_none=True)
            payload_holder["presentation"] = payload
            artifacts_dir = context.workspace_root / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "presentation.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "status": "ok",
                "slide_count": len(payload.get("slides") or []),
                "path": str((artifacts_dir / "presentation.json").resolve()),
            }

        return Tool(
            name="submit_presentation",
            description="Submit the final editor presentation as structured JSON. Call this exactly once when the presentation is complete.",
            args_model=_SubmitPresentationArgs,
            handler=_handler,
            source="embedded",
        )

    def _make_html_deck_submit_tool(self, payload_holder: dict[str, Any]) -> Tool:
        async def _handler(args: _SubmitHtmlDeckArgs, context: ToolContext) -> dict[str, Any]:
            artifacts_dir = context.workspace_root / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            normalized_html, meta, presentation = normalize_html_deck(
                html=args.html,
                fallback_title=args.title,
                existing_slides=None,
            )
            payload = {
                "title": meta["title"],
                "html": normalized_html,
                "meta": meta,
                "presentation": presentation,
            }
            payload_holder["html_deck"] = payload
            (artifacts_dir / "presentation.html").write_text(
                normalized_html,
                encoding="utf-8",
            )
            (artifacts_dir / "presentation.meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "status": "ok",
                "slide_count": meta["slide_count"],
                "path": str((artifacts_dir / "presentation.html").resolve()),
            }

        return Tool(
            name="submit_html_deck",
            description="Submit the final Reveal-compatible HTML deck. Call this exactly once when the deck is ready.",
            args_model=_SubmitHtmlDeckArgs,
            handler=_handler,
            source="embedded",
        )

    def _make_slidev_deck_submit_tool(self, payload_holder: dict[str, Any]) -> Tool:
        async def _handler(args: _SubmitSlidevDeckArgs, context: ToolContext) -> dict[str, Any]:
            payload = args.model_dump(mode="json", by_alias=True, exclude_none=True)
            markdown = str(payload.get("markdown") or "").strip()
            if not markdown:
                raise ValueError("Slidev deck markdown is empty.")
            payload_holder["slidev_deck"] = payload
            artifacts_dir = context.workspace_root / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            (artifacts_dir / "slides.md").write_text(markdown, encoding="utf-8")
            return {
                "status": "ok",
                "selected_style_id": payload.get("selectedStyleId"),
                "path": str((artifacts_dir / "slides.md").resolve()),
            }

        return Tool(
            name="submit_slidev_deck",
            description="Submit the final Slidev markdown deck with markdown and selected_style_id. Call this exactly once when the deck is ready.",
            args_model=_SubmitSlidevDeckArgs,
            handler=_handler,
            source="embedded",
        )

    @staticmethod
    def _extract_outline_submission(payload_holder: dict[str, Any]) -> AgentOutline | None:
        payload = payload_holder.get("outline")
        if not isinstance(payload, dict):
            return None
        return AgentOutline.model_validate(payload)

    def _extract_presentation_submission(
        self,
        job: GenerationJob,
        payload_holder: dict[str, Any],
    ) -> tuple[dict[str, Any], Presentation] | None:
        payload = payload_holder.get("presentation")
        if not isinstance(payload, dict):
            return None
        hydrated_payload = self._hydrate_submitted_presentation(job, payload)
        normalized_payload, _changed, _report = normalize_presentation_payload(hydrated_payload)
        return hydrated_payload, Presentation.model_validate(normalized_payload)

    def _extract_html_deck_submission(
        self,
        job: GenerationJob,
        payload_holder: dict[str, Any],
    ) -> tuple[dict[str, Any], Presentation] | None:
        payload = payload_holder.get("html_deck")
        if not isinstance(payload, dict):
            return None
        presentation = payload.get("presentation")
        if not isinstance(presentation, dict):
            return None
        normalized_payload, _changed, _report = normalize_presentation_payload(presentation)
        validated = Presentation.model_validate(self._hydrate_submitted_presentation(job, normalized_payload))
        return payload, validated

    async def _extract_slidev_deck_submission(
        self,
        job: GenerationJob,
        state: GenerationRuntimeState,
        payload_holder: dict[str, Any],
    ) -> tuple[dict[str, Any], Presentation] | None:
        payload = payload_holder.get("slidev_deck")
        if not isinstance(payload, dict):
            return None
        markdown = str(payload.get("markdown") or "").strip()
        if not markdown:
            return None
        outline_items = list(state.outline.get("items") or []) if isinstance(state.outline, dict) else []
        build_root = self._workspace_root_for_job(job) / "artifacts" / "slidev-build"
        finalized = await finalize_slidev_deck(
            markdown=markdown,
            fallback_title=str(payload.get("title") or job.request.title or "新演示文稿"),
            selected_style_id=str(payload.get("selectedStyleId") or "").strip() or None,
            topic=job.request.topic or job.request.title,
            outline_items=outline_items,
            expected_pages=max(3, min(job.request.num_pages, settings.max_slide_pages)),
            build_base_path=f"/api/v1/sessions/{job.request.session_id}/presentations/latest/slidev/build/",
            build_out_dir=build_root,
        )
        presentation = finalized.get("presentation")
        if not isinstance(presentation, dict):
            return None
        normalized_payload, _changed, _report = normalize_presentation_payload(presentation)
        validated = Presentation.model_validate(self._hydrate_submitted_presentation(job, normalized_payload))
        return finalized, validated

    @staticmethod
    def _workspace_root_for_job(job: GenerationJob):
        workspace = (job.document_metadata.get("agent_workspace") or {}).get("root")
        if not isinstance(workspace, str) or not workspace.strip():
            raise ValueError("Agent workspace is not initialized for this job.")
        from pathlib import Path

        return Path(workspace).resolve()

    @staticmethod
    def _hydrate_submitted_presentation(job: GenerationJob, payload: dict[str, Any]) -> dict[str, Any]:
        hydrated = deepcopy(payload)
        presentation_id = hydrated.get("presentationId")
        if not isinstance(presentation_id, str) or not presentation_id.strip():
            hydrated["presentationId"] = f"pres-{uuid4().hex[:8]}"

        title = hydrated.get("title")
        if not isinstance(title, str) or not title.strip():
            hydrated["title"] = job.request.title or job.request.topic or "新演示文稿"

        raw_slides = hydrated.get("slides")
        slides = list(raw_slides) if isinstance(raw_slides, list) else []
        for index, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                continue
            slide_id = slide.get("slideId")
            if not isinstance(slide_id, str) or not slide_id.strip():
                slide["slideId"] = f"slide-{index}"
            layout_type = slide.get("layoutType")
            if not isinstance(layout_type, str) or not layout_type.strip():
                slide["layoutType"] = "bullet-with-icons"
            layout_id = slide.get("layoutId")
            if not isinstance(layout_id, str) or not layout_id.strip():
                slide["layoutId"] = str(slide["layoutType"])
            if not isinstance(slide.get("contentData"), dict) and isinstance(slide.get("content"), dict):
                slide["contentData"] = deepcopy(slide["content"])
            slide.pop("content", None)
            if not isinstance(slide.get("contentData"), dict):
                slide["contentData"] = {}
        hydrated["slides"] = slides
        return hydrated

    def _build_agent_outline_prompt(self, job: GenerationJob, state: GenerationRuntimeState) -> str:
        skill_context = build_skill_catalog_context(
            output_mode=job.output_mode.value,
            requested_skill=job.request.skill_id,
        )
        return (
            "你是 ZhiYan 当前创建页按钮背后的第一代 AgentLoop 生成内核。\n"
            "你的工作不是解释，而是基于工作区素材，为后续 final presentation 生成提交一个严格结构化的大纲。\n\n"
            "工作区约定：\n"
            "- `request.json` 包含 topic、页数、mode、source_ids。\n"
            "- `sources/manifest.json` 描述所有可用来源。\n"
            "- `sources/*.md` 是来源解析文本；优先阅读这些文件，而不是只凭记忆生成。\n"
            "- 你有 `read_file`、`load_skill` 和 `submit_outline` 三类工具；只有任务确实匹配额外规则时才加载额外 skill。\n\n"
            "大纲要求：\n"
            f"- 必须严格提交 {state.num_pages} 页。\n"
            "- `role` 仅使用：cover, agenda, section-divider, narrative, evidence, comparison, process, highlight, closing。\n"
            "- 每页必须补齐 `objective`，并尽量提供 `keyPoints` 与 `contentHints`。\n"
            "- 这是一个故事化演示，不是文档摘抄；每页标题要清晰、可展示，并能支撑后续选择 layout。\n"
            "- 最终只通过 `submit_outline` 提交结构化结果，不要只输出自然语言。\n\n"
            f"{skill_context}\n"
        )

    def _build_agent_outline_user_prompt(self, job: GenerationJob) -> str:
        return (
            "请阅读工作区素材并提交大纲。\n"
            f"主题：{job.request.topic or job.request.title}\n"
            f"补充指令：{job.request.content or '无'}\n"
            f"目标页数：{job.request.num_pages}\n"
            "现在开始工作，并在大纲准备好后调用 `submit_outline`。"
        )

    def _build_agent_presentation_prompt(self, job: GenerationJob, state: GenerationRuntimeState) -> str:
        skill_context = build_skill_catalog_context(
            output_mode=job.output_mode.value,
            requested_skill=job.request.skill_id,
        )
        outline_json = json.dumps(state.outline, ensure_ascii=False, indent=2) if state.outline else "(auto 模式无大纲，直接按素材生成)"
        source_brief = str((state.document_metadata.get("source_brief") or {}).get("summary_markdown") or "").strip()
        palette = ", ".join(self._allowed_layout_palette(job))
        outline_items = list(state.outline.get("items") or []) if isinstance(state.outline, dict) else []
        slidev_refs = build_slidev_role_reference_bundle(outline_items) if outline_items else {
            "selected_layouts": [],
            "page_briefs": [],
        }
        slidev_ref_json = json.dumps(
            {
                "selected_layouts": slidev_refs.get("selected_layouts", []),
                "page_briefs": slidev_refs.get("page_briefs", []),
                "available_style_presets": sorted(["narrative-brief", "structured-insight", "tech-launch"]),
            },
            ensure_ascii=False,
            indent=2,
        )
        if job.output_mode.value == "html":
            return (
                "你是 ZhiYan 当前创建页按钮背后的 HTML 演示生成内核。\n"
                "请基于工作区素材和已确认的大纲，产出一个可直接播放、可后续继续编辑的 Reveal HTML deck。\n\n"
                "工作方式：\n"
                "- 先使用本地素材摘要判断叙事与风格，再按需补读原始 source 文本。\n"
                "- 你有 `read_file`、`load_skill` 和 `submit_html_deck` 三类工具，不要输出解释，也不要做仓库探索。\n"
                "- 最终必须只通过 `submit_html_deck` 提交。\n\n"
                f"{skill_context}\n\n"
                "HTML 约束：\n"
                f"- 严格输出 {state.num_pages} 页，且必须严格包含 {state.num_pages} 个 `<section>`。\n"
                "- 每页必须是 16:9 演示页面，不要写成文档排版。\n"
                "- 每个 `<section>` 都必须有稳定的 `data-slide-id=\"slide-N\"` 和 `data-slide-title=\"页面标题\"`。\n"
                "- 必须体现强视觉设计：鲜明但克制的主题、明确的版式层级、面向展示的文案密度、符合主题的艺术风格。\n"
                "- 优先做带艺术方向的 HTML PPT，不要退化成普通 markdown 页面。\n"
                "- 内容要贴合素材，不要空泛，不要出现“待补充”“内容生成中”之类占位文本。\n\n"
                f"本地素材摘要：\n{source_brief}\n\n"
                f"已确认大纲：\n{outline_json}\n"
            )
        if job.output_mode.value == "slidev":
            return (
                "你是 ZhiYan 当前创建页按钮背后的 Slidev 演示生成内核。\n"
                "Slidev 是一个 markdown-first 的演示框架：一份 deck 由全局 frontmatter 和多个用 `---` 分隔的 slide 组成，目标是生成能被 `slidev build` 编译的 presentation markdown，而不是文章 markdown。\n"
                "请基于工作区素材和已确认大纲，产出一个完整、可编译、可展示、可继续改稿的 Slidev markdown deck。\n\n"
                "工作方式：\n"
                "- 先使用本地素材摘要判断叙事、语气和视觉方向，再按需补读原始 source 文本。\n"
                "- 你有 `read_file`、`load_skill` 和 `submit_slidev_deck` 三类工具，不要输出解释，也不要做仓库探索。\n"
                "- 最终必须只通过 `submit_slidev_deck` 提交 markdown 和 selected_style_id。\n\n"
                f"{skill_context}\n\n"
                "Slidev 约束：\n"
                f"- 严格输出 {state.num_pages} 页。\n"
                "- deck 必须由全局 frontmatter + `---` 分隔的 slides 组成。\n"
                "- 输出目标是可被 `slidev build` 编译的 presentation markdown，不是普通文档 markdown。\n"
                "- 允许使用 Slidev 原生结构：theme、themeConfig、layout、class、Mermaid、表格、双栏、callout、quote 等。\n"
                "- 不要把页面写成长段落文档，不要出现“待补充”“内容生成中”等占位语。\n"
                "- 只能从本地 style preset 中选择一个 deck 风格，并通过 selected_style_id 提交。\n"
                "- 默认保持演示语气和页面密度，重点让页面像 presentation，而不是报告正文。\n\n"
                f"本地 Slidev preset / role 参考：\n{slidev_ref_json}\n\n"
                f"本地素材摘要：\n{source_brief}\n\n"
                f"已确认大纲：\n{outline_json}\n"
            )
        return (
            "你是 ZhiYan 当前创建页按钮背后的第一代 AgentLoop 演示生成内核。\n"
            "请基于工作区素材和已确认的大纲/本地摘要，直接产出当前 editor 可消费的完整 presentation。\n\n"
            "工作方式：\n"
            "- 先使用本地素材摘要判断故事线和页面结构，再按需要补读原始 source 文本。\n"
            "- 你有 `read_file`、`load_skill` 和 `submit_presentation` 三类工具，不要输出解释，也不要做仓库探索。\n"
            "- 不要输出解释文本；最终只通过 `submit_presentation` 提交完整 presentation。\n\n"
            f"{skill_context}\n\n"
            "Presentation 约束：\n"
            f"- 严格输出 {state.num_pages} 页。\n"
            f"- 仅使用这组 layoutId / layoutType：{palette}。\n"
            "- 每页都必须提交 `slideId`、`layoutType`、`layoutId`、`contentData`；`layoutId` 默认与 `layoutType` 相同。\n"
            "- 禁止把页面写成提纲词条；每页都必须是可展示内容。\n"
            "- `bullet-with-icons` / `bullet-with-icons-cards`：`contentData = {title, items[{title,description,icon?}]}`，items 必须 3-4 个且 description 非空。\n"
            "- `outline-slide` / `outline-slide-rail`：`contentData = {title, subtitle?, sections[{title,description}]}`。\n"
            "- `numbered-bullets` / `numbered-bullets-track`：`contentData = {title, items[{title,description}]}`，items 至少 3 个。\n"
            "- `metrics-slide` / `metrics-slide-band`：`contentData = {title, metrics[{value,label,description?}], conclusion?}`。\n"
            "- `two-column-compare`：`contentData = {title, left{heading,items}, right{heading,items}}`。\n"
            "- `challenge-outcome`：`contentData = {title, items[{challenge,outcome}]}`。\n"
            "- `timeline`：`contentData = {title, events[{date,title,description}]}`。\n"
            "- `quote-slide` / `quote-banner`：`contentData = {quote, author?, context?}`。\n"
            "- `thank-you` / `thank-you-contact`：`contentData = {title, subtitle?, contact?}`，不能只有标题。\n"
            "- `intro-slide` / `intro-slide-left`：`contentData = {title, subtitle?, author?, date?}`。\n"
            "- 如果你拿不准某页，就退回文本安全 layout，不要发明 schema。\n\n"
            f"本地素材摘要：\n{source_brief}\n\n"
            f"已确认大纲：\n{outline_json}\n"
        )

    def _build_agent_presentation_user_prompt(self, job: GenerationJob, state: GenerationRuntimeState) -> str:
        del state
        if job.output_mode.value == "html":
            return (
                "请生成完整 HTML deck。\n"
                f"主题：{job.request.topic or job.request.title}\n"
                f"补充指令：{job.request.content or '无'}\n"
                f"目标页数：{job.request.num_pages}\n"
                "完成后调用 `submit_html_deck`。"
            )
        if job.output_mode.value == "slidev":
            return (
                "请生成完整 Slidev markdown deck。\n"
                f"主题：{job.request.topic or job.request.title}\n"
                f"补充指令：{job.request.content or '无'}\n"
                f"目标页数：{job.request.num_pages}\n"
                "完成后调用 `submit_slidev_deck`。"
            )
        return (
            "请生成完整 presentation。\n"
            f"主题：{job.request.topic or job.request.title}\n"
            f"补充指令：{job.request.content or '无'}\n"
            f"目标页数：{job.request.num_pages}\n"
            "完成后调用 `submit_presentation`。"
        )

    def _build_agent_presentation_retry_prompt(
        self,
        expected: int,
        issues: list[str],
        *,
        output_mode: str,
    ) -> str:
        issue_text = "\n".join(f"- {issue}" for issue in issues[:8]) or "- 上一次 presentation 未通过本地审计。"
        if output_mode == "html":
            submit_tool = "submit_html_deck"
            label = "HTML deck"
        elif output_mode == "slidev":
            submit_tool = "submit_slidev_deck"
            label = "Slidev deck"
        else:
            submit_tool = "submit_presentation"
            label = "presentation"
        return (
            f"请修正上一版 {label} 并重新提交。\n"
            f"必须严格输出 {expected} 页。\n"
            "以下问题必须全部修正：\n"
            f"{issue_text}\n"
            f"修正后再次调用 `{submit_tool}`。"
        )

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


def _summarize_model_identity(client: ModelClient) -> dict[str, Any]:
    raw_model = str(getattr(client, "model", "") or "").strip()
    normalized_model = normalize_litellm_model(raw_model) if raw_model else ""
    api_base = str(getattr(client, "api_base", "") or "").strip()
    return {
        "raw_model": raw_model or None,
        "normalized_model": normalized_model or None,
        "provider": parse_provider(raw_model) if raw_model else None,
        "api_base": api_base or None,
        "api_base_enabled": bool(api_base),
        "client_type": type(client).__name__,
    }


def _summarize_model_request(client: ModelClient, messages: list[Message], tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": _summarize_model_identity(client),
        "message_count": len(messages),
        "messages": [_serialize_message(message) for message in messages],
        "tool_count": len(tools),
        "tool_names": [str(tool.get("name") or "") for tool in tools],
        "tools": deepcopy(tools),
    }


def _summarize_model_response(response: ModelResponse) -> dict[str, Any]:
    return {
        "message": _serialize_message(response.message),
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }


def _serialize_message(message: Message) -> dict[str, Any]:
    if message.role in {"system", "user"}:
        return {
            "role": message.role,
            "content": getattr(message, "content", ""),
        }
    if message.role == "assistant":
        return {
            "role": message.role,
            "content": getattr(message, "content", ""),
            "tool_calls": [
                {
                    "tool_name": tool_call.tool_name,
                    "tool_call_id": tool_call.tool_call_id,
                    "args": deepcopy(tool_call.args),
                }
                for tool_call in getattr(message, "tool_calls", [])
            ],
        }
    if isinstance(message, ToolMessage):
        return {
            "role": message.role,
            "results": [_serialize_tool_result(result) for result in message.results],
        }
    return {"role": getattr(message, "role", "unknown"), "content": repr(message)}


def _serialize_tool_result(item: Any) -> dict[str, Any]:
    return {
        "tool_name": str(getattr(item, "tool_name", "")),
        "tool_call_id": str(getattr(item, "tool_call_id", "")),
        "is_error": bool(getattr(item, "is_error", False)),
        "content": deepcopy(getattr(item, "content", None)),
        "metadata": deepcopy(getattr(item, "metadata", {}) or {}),
    }


def _aggregate_model_usage(runs: dict[str, Any]) -> dict[str, int]:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for run in runs.values():
        calls = run.get("calls") or []
        for call in calls:
            response = call.get("response") or {}
            usage = response.get("usage") or {}
            for key in totals:
                value = usage.get(key)
                if isinstance(value, int):
                    totals[key] += value
    return totals


def _text_field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _extract_source_headings(text: str, limit: int = 6) -> list[str]:
    headings: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("#").strip()
        if not line:
            continue
        if len(line) > 48:
            continue
        if line.startswith(("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "0", "1", "2", "3", "4", "5")):
            headings.append(line)
        elif raw_line.lstrip().startswith("#"):
            headings.append(line)
        if len(headings) >= limit:
            break
    return headings


def _extract_source_passages(text: str, limit: int = 3) -> list[str]:
    passages: list[str] = []
    for block in text.split("\n\n"):
        paragraph = " ".join(part.strip() for part in block.splitlines() if part.strip()).strip()
        if len(paragraph) < 24:
            continue
        passages.append(paragraph[:180])
        if len(passages) >= limit:
            break
    return passages


def _render_source_brief_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Local Source Brief",
        "",
        f"- Topic: {payload.get('topic') or ''}",
        f"- Target Pages: {payload.get('num_pages') or ''}",
        f"- Recommended Layouts: {', '.join(payload.get('recommended_layouts') or [])}",
        "",
    ]
    for source in payload.get("sources") or []:
        lines.append(f"## {source.get('name') or source.get('id') or 'Source'}")
        headings = source.get("headings") or []
        passages = source.get("key_passages") or []
        if headings:
            lines.append("Headings:")
            lines.extend(f"- {heading}" for heading in headings)
        if passages:
            lines.append("Passages:")
            lines.extend(f"- {passage}" for passage in passages)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
