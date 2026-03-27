from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.model_status import parse_provider
from app.models.slide import Presentation
from app.services.generation.agent_workspace import build_agent_workspace
from app.services.generation.agentic.builder import AgentBuilder
from app.services.generation.agentic.models import LiteLLMModelClient
from app.services.generation.agentic.tools import Tool, ToolContext, ToolRegistry, create_builtin_registry


class SubmittedSpeakerNote(BaseModel):
    slide_id: str = Field(alias="slideId")
    notes: str

    model_config = {"populate_by_name": True}


class SubmitSpeakerNotesArgs(BaseModel):
    notes: list[SubmittedSpeakerNote]


class SpeakerNotesGenerationResult(BaseModel):
    presentation: dict
    updated_slide_ids: list[str]
    workspace_root: str


def _create_agent_model_client() -> LiteLLMModelClient:
    model_name = str(settings.strong_model or settings.default_model or "").strip()
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


def _speaker_notes_submit_tool(payload_holder: dict[str, object]) -> Tool:
    async def _handler(args: SubmitSpeakerNotesArgs, context: ToolContext) -> dict[str, object]:
        payload = args.model_dump(mode="json", by_alias=True)
        payload_holder["notes"] = payload
        artifacts_dir = context.workspace_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifacts_dir / "speaker-notes.json"
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "status": "ok",
            "item_count": len(payload.get("notes") or []),
            "path": str(output_path.resolve()),
        }

    return Tool(
        name="submit_speaker_notes",
        description=(
            "Submit the final speaker notes for the requested slides after reading the workspace files. "
            "Call this exactly once when the notes are ready."
        ),
        args_model=SubmitSpeakerNotesArgs,
        handler=_handler,
        source="embedded",
    )


def _build_workspace_root(session_id: str) -> Path:
    return (
        settings.project_root
        / "data"
        / "speaker-notes-runs"
        / session_id
        / f"run-{uuid4().hex[:8]}"
    ).resolve()


def _build_request_payload(
    presentation: dict,
    *,
    scope: str,
    current_slide_index: int,
    target_slide_ids: list[str],
) -> dict[str, object]:
    slides = list(presentation.get("slides") or [])
    current_slide = (
        slides[current_slide_index]
        if 0 <= current_slide_index < len(slides) and isinstance(slides[current_slide_index], dict)
        else None
    )
    return {
        "scope": scope,
        "current_slide_index": current_slide_index,
        "target_slide_ids": target_slide_ids,
        "presentation_title": presentation.get("title") or "",
        "current_slide_id": current_slide.get("slideId") if isinstance(current_slide, dict) else None,
    }


def _render_presentation_markdown(presentation: dict) -> str:
    slides = list(presentation.get("slides") or [])
    parts = [
        f"# Presentation: {str(presentation.get('title') or 'Untitled')}",
        "",
        f"- Slide count: {len(slides)}",
        "",
    ]
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        content_data = slide.get("contentData")
        title = str(content_data.get("title") or "").strip() if isinstance(content_data, dict) else ""
        layout = str(slide.get("layoutId") or slide.get("layoutType") or "unknown")
        notes = str(slide.get("speakerNotes") or "").strip()
        parts.extend(
            [
                f"## Slide {index}",
                f"- slideId: {slide.get('slideId') or ''}",
                f"- layout: {layout}",
                f"- title: {title or '(untitled)'}",
                "- contentData:",
                "```json",
                json.dumps(content_data or {}, ensure_ascii=False, indent=2),
                "```",
                f"- currentSpeakerNotes: {notes or '(empty)'}",
                "",
            ]
        )
    return "\n".join(parts).strip() + "\n"


def _build_system_prompt() -> str:
    return (
        "You are the speaker notes generation agent for ZhiYan.\n"
        "You must read the workspace files before you write notes.\n"
        "Use read_file to inspect artifacts/current-presentation.md and relevant source files.\n"
        "Then call submit_speaker_notes exactly once with notes for the requested slides.\n\n"
        "Rules:\n"
        "- Notes must be grounded in the current slide content and workspace source files.\n"
        "- Write in natural spoken Chinese.\n"
        "- Include the page's key message and a smooth spoken transition when appropriate.\n"
        "- Notes should usually be 60-140 Chinese characters.\n"
        "- For cover or closing slides, shorter notes are acceptable.\n"
        "- Do not mention that you read files or used tools.\n"
        "- Do not skip any requested slide.\n"
    )


def _build_user_prompt(
    *,
    scope: str,
    current_slide_index: int,
    target_slide_ids: list[str],
) -> str:
    scope_label = "当前页" if scope == "current" else "全部页面"
    return (
        f"请为{scope_label}生成演讲者注解。\n"
        f"当前页索引: {current_slide_index}\n"
        f"目标 slideId 列表: {', '.join(target_slide_ids)}\n\n"
        "先读取 artifacts/current-presentation.md，再按需读取 sources/ 下的文件与 manifest。\n"
        "完成后调用 submit_speaker_notes，一次性提交所有目标 slideId 的 notes。"
    )


def _extract_target_slide_ids(
    presentation: Presentation,
    scope: str,
    current_slide_index: int,
) -> list[str]:
    if scope == "current":
        if current_slide_index < 0 or current_slide_index >= len(presentation.slides):
            raise ValueError("current_slide_index 超出范围")
        return [presentation.slides[current_slide_index].slide_id]
    if scope == "all":
        return [slide.slide_id for slide in presentation.slides]
    raise ValueError("scope 仅支持 current 或 all")


def _validate_submission(
    payload_holder: dict[str, object],
    *,
    target_slide_ids: list[str],
) -> list[SubmittedSpeakerNote]:
    payload = payload_holder.get("notes")
    if not isinstance(payload, dict):
        raise ValueError("Agent 没有提交演讲者注解结果")
    parsed = SubmitSpeakerNotesArgs.model_validate(payload)
    submitted_ids = [item.slide_id for item in parsed.notes]
    if sorted(submitted_ids) != sorted(target_slide_ids):
        raise ValueError(
            "提交的 slideId 与目标不匹配: "
            f"expected={target_slide_ids}, actual={submitted_ids}"
        )
    for item in parsed.notes:
        if not item.notes.strip():
            raise ValueError(f"slide {item.slide_id} 的 notes 为空")
    return parsed.notes


async def generate_speaker_notes_for_session(
    *,
    workspace_id: str,
    session_id: str,
    presentation_payload: dict,
    scope: str,
    current_slide_index: int,
) -> SpeakerNotesGenerationResult:
    from app.services.sessions import session_store

    normalized = Presentation.model_validate(presentation_payload).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    presentation = Presentation.model_validate(normalized)
    target_slide_ids = _extract_target_slide_ids(presentation, scope, current_slide_index)

    source_metas = await session_store.list_sources(workspace_id, session_id)
    source_ids = [str(item["id"]) for item in source_metas if item.get("id")]
    source_records = await session_store.get_workspace_source_records_by_ids(workspace_id, source_ids)

    workspace_root = _build_workspace_root(session_id)
    build_agent_workspace(
        root=workspace_root,
        request_payload=_build_request_payload(
            normalized,
            scope=scope,
            current_slide_index=current_slide_index,
            target_slide_ids=target_slide_ids,
        ),
        source_records=source_records,
    )

    artifacts_dir = workspace_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "current-presentation.json").write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (artifacts_dir / "current-presentation.md").write_text(
        _render_presentation_markdown(normalized),
        encoding="utf-8",
    )

    payload_holder: dict[str, object] = {}
    builder = AgentBuilder.from_project(workspace_root)
    builder.with_model_client(_create_agent_model_client())
    builder.with_system_prompt(_build_system_prompt())
    builder.with_max_turns(max(8, settings.agentic_max_turns))
    builder.with_permissive_tools(False)
    builder.with_auto_compact(True)
    builder.with_compact_token_threshold(6000)
    builder.with_compact_tail_turns(2)
    builtin_registry = create_builtin_registry(workspace_root, permissive_mode=False)
    builder.tool_registry = ToolRegistry(
        tools={
            name: tool
            for name, tool in builtin_registry.tools.items()
            if name == "read_file"
        }
    )
    builder.register_tool(_speaker_notes_submit_tool(payload_holder))
    agent = builder.build()
    session = agent.start_session()
    result = await session.send(
        _build_user_prompt(
            scope=scope,
            current_slide_index=current_slide_index,
            target_slide_ids=target_slide_ids,
        )
    )

    submitted_notes = _validate_submission(payload_holder, target_slide_ids=target_slide_ids)
    updated_presentation = deepcopy(normalized)
    notes_by_slide_id = {item.slide_id: item.notes.strip() for item in submitted_notes}
    for slide in list(updated_presentation.get("slides") or []):
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slideId") or "")
        next_notes = notes_by_slide_id.get(slide_id)
        if next_notes is None:
            continue
        if str(slide.get("speakerNotes") or "").strip() != next_notes:
            slide.pop("speakerAudio", None)
        slide["speakerNotes"] = next_notes

    await session_store.save_presentation(
        session_id=session_id,
        payload=updated_presentation,
        is_snapshot=False,
        snapshot_label=None,
    )

    (artifacts_dir / "run-summary.json").write_text(
        json.dumps(
            {
                "stop_reason": result.stop_reason,
                "turns": result.turns,
                "error": result.error,
                "updated_slide_ids": target_slide_ids,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return SpeakerNotesGenerationResult(
        presentation=updated_presentation,
        updated_slide_ids=target_slide_ids,
        workspace_root=str(workspace_root),
    )
