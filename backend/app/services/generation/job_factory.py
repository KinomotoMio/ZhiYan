"""Shared generation job creation helpers."""

from __future__ import annotations

from uuid import uuid4

from app.core.config import settings
from app.models.generation import (
    CreateJobRequest,
    GenerationJob,
    GenerationMode,
    GenerationRequestData,
    StageStatus,
)
from app.services.generation.agent_workspace import build_agent_workspace
from app.services.generation.loading_title import (
    DEFAULT_LOADING_TITLE,
    build_loading_title,
)


def _build_source_hints(
    *,
    source_ids: list[str],
    source_metas: list[dict],
) -> dict:
    by_category: dict[str, int] = {}
    for meta in source_metas or []:
        raw = meta.get("fileCategory")
        category = str(raw).strip().lower() if raw else "unknown"
        by_category[category] = by_category.get(category, 0) + 1

    def count(*cats: str) -> int:
        return sum(by_category.get(cat, 0) for cat in cats)

    images = count("image")
    slides = count("pptx")
    documents = count("pdf", "docx", "markdown")
    data = count("text")
    unknown = len(source_ids or []) - (images + slides + documents + data)
    if unknown < 0:
        unknown = by_category.get("unknown", 0)

    return {
        "total_sources": int(len(source_ids or [])),
        "images": int(images),
        "documents": int(documents),
        "slides": int(slides),
        "data": int(data),
        "unknown": int(unknown),
        "by_file_category": by_category,
    }


async def create_generation_job_record(
    *,
    workspace_id: str,
    req: CreateJobRequest,
    session_store_override=None,
    job_store_override=None,
    generation_runner_override=None,
) -> tuple[GenerationJob, str]:
    from app.services.generation import generation_runner, job_store
    from app.services.sessions import session_store

    session_store = session_store_override or session_store
    job_store = job_store_override or job_store
    generation_runner = generation_runner_override or generation_runner

    await session_store.ensure_workspace(workspace_id)

    combined = req.content
    session_id = req.session_id
    if not session_id:
        created_session = await session_store.create_session(workspace_id, "未命名会话")
        session_id = created_session["id"]

    session = await session_store.get_session(workspace_id, session_id)
    if session.get("has_presentation"):
        raise ValueError("当前会话已有演示稿，请新建会话生成")

    if req.source_ids:
        source_metas = await session_store.get_workspace_sources_by_ids(workspace_id, req.source_ids)
        source_records = await session_store.get_workspace_source_records_by_ids(workspace_id, req.source_ids)
        source_hints = _build_source_hints(source_ids=req.source_ids, source_metas=source_metas)
        source_content = await session_store.get_combined_source_content(
            workspace_id,
            session_id,
            req.source_ids,
        )
        combined = f"{source_content}\n\n{combined}".strip() if combined else source_content
    else:
        source_hints = {}
        source_metas = []
        source_records = []

    if not combined and not req.topic and not req.approved_outline:
        raise ValueError("请提供来源文档或主题描述")

    loading_title = build_loading_title(
        topic=req.topic or req.content,
        source_names=[meta.get("name", "") for meta in source_metas],
        fallback=DEFAULT_LOADING_TITLE,
    )
    await session_store.set_generated_title_if_unedited(
        workspace_id,
        session_id,
        loading_title,
    )

    job_id = f"job-{uuid4().hex[:12]}"
    approved_outline = req.approved_outline or {}
    outline_items = approved_outline.get("items") if isinstance(approved_outline, dict) else None
    effective_num_pages = (
        len(outline_items)
        if isinstance(outline_items, list) and outline_items
        else max(3, min(req.num_pages, settings.max_slide_pages))
    )
    normalized_mode = GenerationMode.AUTO if req.approved_outline else req.mode

    job = GenerationJob(
        job_id=job_id,
        mode=normalized_mode,
        request=GenerationRequestData(
            topic=req.topic,
            content=req.content,
            session_id=session_id,
            source_ids=req.source_ids,
            source_hints=source_hints,
            template_id=req.template_id,
            num_pages=effective_num_pages,
            title=loading_title,
            resolved_content=combined or req.topic,
        ),
        outline=approved_outline if isinstance(approved_outline, dict) else {},
        outline_accepted=bool(req.approved_outline) or normalized_mode == GenerationMode.AUTO,
    )
    workspace_bundle = build_agent_workspace(
        root=settings.project_root / "data" / "agentic-runs" / job_id,
        request_payload={
            "job_id": job_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "topic": req.topic,
            "content": req.content,
            "source_ids": list(req.source_ids),
            "template_id": req.template_id,
            "num_pages": effective_num_pages,
            "mode": normalized_mode.value,
            "title": loading_title,
        },
        source_records=source_records,
    )
    job.document_metadata["agent_workspace"] = workspace_bundle.to_metadata()
    job.document_metadata["agent_workspace"]["workspace_id"] = workspace_id
    job.document_metadata["agent_workspace"]["source_hints"] = source_hints

    await job_store.create_job(job)
    await session_store.save_generation_job(job.job_id, session_id, job.status.value)
    from_stage = StageStatus.LAYOUT if req.approved_outline else None
    await generation_runner.start_job(job_id, from_stage=from_stage)
    return job, session_id
