"""Editor-specific agent loop service for the slide editor chat panel."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.services.generation.agentic import AgentBuilder, Tool, ToolContext, ToolRegistry
from app.services.generation.agentic.tools import load_skill, read_skill_resource, todo
from app.services.generation.agentic.types import AssistantMessage, Message, ToolMessage, ToolResult
from app.services.model_clients import create_model_client
from app.services.skill_runtime.contracts import build_skill_catalog_context, resolve_skill_name
from app.services.skill_runtime.registry import build_skill_catalog
from app.services.slidev import create_slidev_preview
from app.services.centi_deck import normalize_centi_deck_submission


_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_LINE_RE = re.compile(r"(?im)^\s*</?think\b[^>]*>\s*$")
_THINK_INLINE_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)

_WS_RE = re.compile(r"\s+")

READ_ONLY_TOOLS = {
    "todo",
    "load_skill",
    "read_skill_resource",
    "get_current_slide_info",
    "get_deck_summary",
}
WRITE_TOOLS = {
    "submit_slidev_revision",
    "submit_centi_deck_revision",
}
VISIBLE_CONTENT_ACTIONS = {
    "refresh_layout",
    "simplify",
    "add_detail",
    "enrich_visual",
    "change_theme",
}


class _NoArgs(BaseModel):
    pass


class _SubmitSlidevRevisionArgs(BaseModel):
    markdown: str
    selected_style_id: str | None = None
    summary: str | None = None


class _SubmitCentiDeckRevisionArgs(BaseModel):
    title: str = ""
    theme: dict[str, Any] | None = None
    presenter: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    slides: list[dict[str, Any]]
    summary: str | None = None


@dataclass(slots=True)
class EditorLoopRequest:
    workspace_id: str
    session_id: str | None
    message: str
    action_hint: str
    current_slide_index: int
    presentation_title: str
    slides: list[dict[str, Any]]
    output_mode: str
    slidev_markdown: str | None = None
    slidev_meta: dict[str, Any] | None = None
    selected_style_id: str | None = None
    centi_deck_artifact: dict[str, Any] | None = None
    centi_deck_render: dict[str, Any] | None = None
    skill_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class EditorLoopOutcome:
    assistant_reply: str
    events: list[dict[str, Any]]
    modifications: list[dict[str, Any]]
    slides: list[dict[str, Any]]
    slidev_markdown: str | None = None
    slidev_meta: dict[str, Any] | None = None
    slidev_preview_url: str | None = None
    selected_style_id: str | None = None
    centi_deck_artifact: dict[str, Any] | None = None
    centi_deck_render: dict[str, Any] | None = None
    skill_id: str | None = None

    @property
    def modification_count(self) -> int:
        return len(self.modifications)

    @property
    def effective_modification_count(self) -> int:
        if not self.modifications:
            return 0
        return sum(1 for item in self.modifications if item.get("action") != "update_notes")


@dataclass(slots=True)
class _EditorRuntimeState:
    request: EditorLoopRequest
    current_slide_index: int
    slides: list[dict[str, Any]]
    slidev_markdown: str | None = None
    slidev_meta: dict[str, Any] | None = None
    slidev_preview_url: str | None = None
    selected_style_id: str | None = None
    centi_deck_artifact: dict[str, Any] | None = None
    centi_deck_render: dict[str, Any] | None = None
    modifications: list[dict[str, Any]] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current_slide(self) -> dict[str, Any] | None:
        if 0 <= self.current_slide_index < len(self.slides):
            return self.slides[self.current_slide_index]
        return None


def sanitize_think_text(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", str(text or ""))
    cleaned = _THINK_LINE_RE.sub("", cleaned)
    cleaned = _THINK_INLINE_RE.sub("", cleaned)
    cleaned = cleaned.replace("<thinking>", "").replace("</thinking>", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truncate(text: str, limit: int = 120) -> str:
    normalized = _WS_RE.sub(" ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: max(0, limit - 1)].rstrip()}..."


def _extract_title(slide: dict[str, Any]) -> str:
    content_data = slide.get("contentData")
    if isinstance(content_data, dict):
        raw_title = content_data.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
    for comp in slide.get("components", []):
        if comp.get("role") == "title":
            return str(comp.get("content") or "").strip()
    return ""


def _summarize_content_data(content_data: Any) -> str:
    if not isinstance(content_data, dict):
        return "无结构化内容"
    fields: list[str] = []
    for key, value in content_data.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, list):
            fields.append(f"{key}:{len(value)}项")
        elif isinstance(value, dict):
            sub_keys = ",".join(str(item) for item in list(value.keys())[:3])
            fields.append(f"{key}:对象({sub_keys})")
        elif isinstance(value, str):
            text = value.strip()
            if text:
                fields.append(f"{key}:{text[:24]}")
        elif isinstance(value, (int, float, bool)):
            fields.append(f"{key}:{value}")
        if len(fields) >= 6:
            break
    return "；".join(fields) if fields else "字段为空"


def _derive_runtime_slides_from_centi_artifact(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    slides = artifact.get("slides") if isinstance(artifact, dict) else None
    if not isinstance(slides, list):
        return []
    runtime_slides: list[dict[str, Any]] = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slideId") or f"slide-{index + 1}")
        runtime_slides.append(
            {
                "slideId": slide_id,
                "layoutType": "centi-deck",
                "layoutId": "centi-deck",
                "contentData": {
                    "_centiDeck": True,
                    "slideId": slide_id,
                    "title": str(slide.get("title") or f"第 {index + 1} 页"),
                    "plainText": str(slide.get("plainText") or ""),
                },
                "components": [],
            }
        )
    return runtime_slides


def _derive_runtime_slides_from_slidev_meta(slide_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    slides = slide_meta.get("slides") if isinstance(slide_meta, dict) else None
    if not isinstance(slides, list):
        return []
    runtime_slides: list[dict[str, Any]] = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        runtime_slides.append(
            {
                "slideId": str(slide.get("slide_id") or f"slide-{index + 1}"),
                "layoutType": "slidev-index",
                "layoutId": "slidev-index",
                "contentData": {
                    "title": str(slide.get("title") or f"第 {index + 1} 页"),
                    "role": str(slide.get("role") or "narrative"),
                    "layout": str(slide.get("layout") or "default"),
                },
                "components": [],
            }
        )
    return runtime_slides


def _slidev_outline_items(slide_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    slides = slide_meta.get("slides") if isinstance(slide_meta, dict) else None
    if not isinstance(slides, list):
        return []
    items: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
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
    return items


def _tool_call_summary(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "todo":
        return "整理本轮执行步骤"
    if tool_name == "load_skill":
        return f"加载 skill {str(args.get('name') or '').strip() or 'unknown'}"
    if tool_name == "read_skill_resource":
        return f"读取 skill 资源 {str(args.get('skill_name') or '').strip()}/{str(args.get('path') or '').strip()}"
    if tool_name == "get_current_slide_info":
        return "读取当前页详细结构"
    if tool_name == "get_deck_summary":
        return "读取整份演示摘要"
    if tool_name == "submit_slidev_revision":
        return "提交整份 Slidev markdown 改稿"
    if tool_name == "submit_centi_deck_revision":
        return "提交整份 centi-deck artifact 改稿"
    return f"调用工具 {tool_name}"


def _tool_result_summary(tool_result: ToolResult) -> str:
    content = tool_result.content
    if tool_result.is_error:
        if isinstance(content, dict):
            return _truncate(str(content.get("error") or f"{tool_result.tool_name} 执行失败"))
        return _truncate(str(content or f"{tool_result.tool_name} 执行失败"))
    if tool_result.tool_name == "todo":
        if isinstance(content, dict) and isinstance(content.get("items"), list):
            return f"已整理 {len(content['items'])} 个步骤"
        return "已整理执行步骤"
    if tool_result.tool_name == "load_skill":
        if isinstance(content, dict) and str(content.get("name") or "").strip():
            return f"已加载 skill {str(content.get('name')).strip()}"
        return "已加载 skill"
    if tool_result.tool_name == "read_skill_resource":
        return "已读取 skill 资源"
    if tool_result.tool_name in {"get_current_slide_info", "get_deck_summary"}:
        return "已读取所需上下文"
    if isinstance(content, dict):
        return _truncate(str(content.get("message") or content.get("status") or "工具执行完成"))
    return _truncate(str(content or "工具执行完成"))


class EditorLoopService:
    def __init__(self) -> None:
        self._model_client_factory = self._create_model_client

    async def run(self, request: EditorLoopRequest) -> EditorLoopOutcome:
        workspace_bundle = self._prepare_workspace(request)
        if request.slides:
            initial_slides = json.loads(json.dumps(request.slides, ensure_ascii=False))
        elif request.output_mode == "slidev":
            initial_slides = _derive_runtime_slides_from_slidev_meta(request.slidev_meta)
        elif request.output_mode == "html":
            initial_slides = _derive_runtime_slides_from_centi_artifact(request.centi_deck_artifact)
        else:
            initial_slides = []
        runtime = _EditorRuntimeState(
            request=request,
            current_slide_index=request.current_slide_index,
            slides=initial_slides,
            slidev_markdown=request.slidev_markdown,
            slidev_meta=dict(request.slidev_meta) if isinstance(request.slidev_meta, dict) else None,
            selected_style_id=request.selected_style_id,
            centi_deck_artifact=dict(request.centi_deck_artifact) if isinstance(request.centi_deck_artifact, dict) else None,
            centi_deck_render=dict(request.centi_deck_render) if isinstance(request.centi_deck_render, dict) else None,
        )
        self._write_debug_artifacts(workspace_bundle["artifacts_dir"], request, runtime)

        builder = AgentBuilder.from_project(workspace_bundle["root"])
        builder.with_model_client(self._model_client_factory())
        builder.with_system_prompt(self._system_prompt(request))
        builder.with_max_turns(max(8, settings.agentic_max_turns))
        builder.with_auto_compact(True)
        builder.with_compact_token_threshold(4500)
        builder.tool_registry = self._build_tool_registry(runtime=runtime)
        builder.skill_catalog = build_skill_catalog(settings.project_root)
        agent = builder.build()
        session = agent.start_session(snapshot=workspace_bundle["snapshot"])
        start_index = len(session.messages)
        resolved_skill_id = resolve_skill_name(
            requested_skill=request.skill_id,
            output_mode=request.output_mode,
        )
        preload_tool_results = []
        if resolved_skill_id:
            preload = await session.load_skill(resolved_skill_id)
            if preload.stop_reason != "completed":
                raise RuntimeError(preload.error or f"Failed to activate base skill: {resolved_skill_id}")
            preload_tool_results = list(preload.tool_results)
        prompt = self._build_prompt(request=request, runtime=runtime)

        result = await session.send(prompt)
        if preload_tool_results:
            result.tool_results = [*preload_tool_results, *result.tool_results]
        new_messages = session.messages[start_index:]
        sanitized_reply = sanitize_think_text(result.output_text.strip())

        snapshot_payload = {
            "base_signature": workspace_bundle["base_signature"],
            "session": session.to_snapshot(),
        }
        self._write_snapshot(workspace_bundle["snapshot_path"], snapshot_payload)

        events = self._build_events(
            messages=new_messages,
            assistant_reply=sanitized_reply,
        )
        self._write_result_artifact(
            workspace_bundle["artifacts_dir"],
            assistant_reply=sanitized_reply,
            runtime=runtime,
            stop_reason=result.stop_reason,
            error=result.error,
        )

        return EditorLoopOutcome(
            assistant_reply=sanitized_reply,
            events=events,
            modifications=list(runtime.modifications),
            slides=runtime.slides,
            slidev_markdown=runtime.slidev_markdown,
            slidev_meta=runtime.slidev_meta,
            slidev_preview_url=runtime.slidev_preview_url,
            selected_style_id=runtime.selected_style_id,
            centi_deck_artifact=runtime.centi_deck_artifact,
            centi_deck_render=runtime.centi_deck_render,
            skill_id=resolved_skill_id,
        )

    def _prepare_workspace(self, request: EditorLoopRequest) -> dict[str, Any]:
        session_key = request.session_id or "adhoc"
        root = (settings.project_root / "data" / "editor-agent" / request.workspace_id / session_key).resolve()
        state_dir = root / "state"
        artifacts_dir = root / "artifacts"
        state_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        base_payload = {
            "output_mode": request.output_mode,
            "slides": request.slides,
            "slidev_markdown": request.slidev_markdown or "",
            "slidev_meta": request.slidev_meta or {},
            "selected_style_id": request.selected_style_id or "",
            "centi_deck_artifact": request.centi_deck_artifact or {},
        }
        base_signature = hashlib.sha256(_safe_json_dumps(base_payload).encode("utf-8")).hexdigest()
        snapshot_path = state_dir / "agent-session.json"
        snapshot: dict[str, Any] = {}
        if snapshot_path.exists():
            try:
                persisted = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                persisted = {}
            if str(persisted.get("base_signature") or "") == base_signature:
                snapshot = dict(persisted.get("session") or {})
        return {
            "root": root,
            "state_dir": state_dir,
            "artifacts_dir": artifacts_dir,
            "snapshot_path": snapshot_path,
            "snapshot": snapshot,
            "base_signature": base_signature,
        }

    def _build_tool_registry(self, *, runtime: _EditorRuntimeState) -> ToolRegistry:
        registry = ToolRegistry()
        is_slidev_mode = runtime.request.output_mode == "slidev"
        is_centi_mode = runtime.request.output_mode == "html"

        async def _get_current_slide_info(_args: _NoArgs, _context: ToolContext) -> dict[str, Any]:
            slide = runtime.current_slide
            if slide is None:
                return {"message": "当前没有可用页面"}
            return {
                "slide_index": runtime.current_slide_index,
                "layout": slide.get("layoutId") or slide.get("layoutType") or "unknown",
                "title": _extract_title(slide) or f"第 {runtime.current_slide_index + 1} 页",
                "summary": _summarize_content_data(slide.get("contentData")),
                "slide": slide,
                "message": "已读取当前页详细结构",
            }

        async def _get_deck_summary(_args: _NoArgs, _context: ToolContext) -> dict[str, Any]:
            slides = runtime.slides
            items = [
                {
                    "index": index,
                    "layout": slide.get("layoutId") or slide.get("layoutType") or "unknown",
                    "title": _extract_title(slide) or f"第 {index + 1} 页",
                    "summary": _summarize_content_data(slide.get("contentData")),
                }
                for index, slide in enumerate(slides)
            ]
            return {
                "slide_count": len(slides),
                "slides": items,
                "message": "已读取整份演示摘要",
            }

        async def _submit_slidev_revision(args: _SubmitSlidevRevisionArgs, _context: ToolContext) -> dict[str, Any]:
            markdown = args.markdown.strip()
            if not markdown:
                raise ValueError("Slidev markdown 不能为空。")
            preview = await create_slidev_preview(
                markdown=markdown,
                fallback_title=runtime.request.presentation_title,
                selected_style_id=args.selected_style_id or runtime.selected_style_id or runtime.request.selected_style_id,
                topic=runtime.request.presentation_title,
                outline_items=_slidev_outline_items(runtime.slidev_meta or {}),
                expected_pages=max(1, len((runtime.slidev_meta or {}).get("slides") or runtime.slides)),
                preview_id=f"spv-{runtime.request.session_id or 'anon'}-{abs(hash(markdown)) % 10**10}",
            )
            runtime.slidev_markdown = preview["markdown"]
            runtime.slidev_meta = preview["meta"]
            runtime.slidev_preview_url = f"/api/v1/slidev-previews/{preview['preview_id']}"
            runtime.selected_style_id = preview["selected_style_id"]
            runtime.slides = _derive_runtime_slides_from_slidev_meta(runtime.slidev_meta)
            runtime.modifications.append(
                {
                    "slide_index": max(0, runtime.current_slide_index),
                    "action": "update_slidev_deck",
                    "data": {
                        "selected_style_id": runtime.selected_style_id,
                        "summary": (args.summary or "").strip(),
                    },
                }
            )
            return {
                "message": "已提交并校验 Slidev deck 改稿",
                "selected_style_id": runtime.selected_style_id,
                "preview_url": runtime.slidev_preview_url,
            }

        tool_definitions: list[Tool | Any] = [
            Tool(
                name="get_current_slide_info",
                description="Read the full structured data of the current slide.",
                args_model=_NoArgs,
                handler=_get_current_slide_info,
                source="editor",
            ),
            Tool(
                name="get_deck_summary",
                description="Read a compact summary of the current deck.",
                args_model=_NoArgs,
                handler=_get_deck_summary,
                source="editor",
            ),
        ]
        async def _submit_centi_deck_revision(
            args: _SubmitCentiDeckRevisionArgs, _context: ToolContext
        ) -> dict[str, Any]:
            payload = args.model_dump(mode="json", by_alias=True, exclude_none=True)
            fallback_title = runtime.request.presentation_title or "新演示文稿"
            try:
                artifact_dict, render_dict = normalize_centi_deck_submission(
                    payload=payload,
                    fallback_title=fallback_title,
                )
            except ValueError as exc:
                return {"status": "error", "message": str(exc)}
            runtime.centi_deck_artifact = artifact_dict
            runtime.centi_deck_render = render_dict
            runtime.slides = _derive_runtime_slides_from_centi_artifact(artifact_dict)
            runtime.modifications.append(
                {
                    "slide_index": max(0, runtime.current_slide_index),
                    "action": "update_centi_deck",
                    "data": {
                        "title": artifact_dict.get("title"),
                        "summary": (args.summary or "").strip(),
                    },
                }
            )
            return {
                "status": "ok",
                "message": "已提交并校验 centi-deck 改稿",
                "slide_count": len(artifact_dict.get("slides") or []),
                "title": artifact_dict.get("title"),
            }

        if is_slidev_mode:
            tool_definitions.append(
                Tool(
                    name="submit_slidev_revision",
                    description="Submit the full revised Slidev markdown deck after editing.",
                    args_model=_SubmitSlidevRevisionArgs,
                    handler=_submit_slidev_revision,
                    source="editor",
                )
            )
        if is_centi_mode:
            tool_definitions.append(
                Tool(
                    name="submit_centi_deck_revision",
                    description=(
                        "Submit the full revised centi-deck artifact (title + slides[] with "
                        "slideId/title/plainText/moduleSource/notes/etc.)."
                    ),
                    args_model=_SubmitCentiDeckRevisionArgs,
                    handler=_submit_centi_deck_revision,
                    source="editor",
                )
            )
        tool_definitions.extend(
            [
                getattr(todo, "__agentloop_tool__"),
                getattr(load_skill, "__agentloop_tool__"),
                getattr(read_skill_resource, "__agentloop_tool__"),
            ]
        )
        registry.extend(tool_definitions)
        return registry

    def _system_prompt(self, request: EditorLoopRequest) -> str:
        skill_id = resolve_skill_name(
            requested_skill=request.skill_id,
            output_mode=request.output_mode,
        )
        skill_context = build_skill_catalog_context(
            output_mode=request.output_mode,
            requested_skill=skill_id,
        )
        if request.output_mode == "slidev":
            mode_line = (
                "当前工作模式是 Slidev deck 全稿改写，必须在准备好后使用 submit_slidev_revision 提交完整 markdown deck。"
            )
        elif request.output_mode == "html":
            mode_line = (
                "当前工作模式是 centi-deck 全稿改写，必须在准备好后使用 submit_centi_deck_revision 提交完整 artifact "
                "(title + slides[] 含 slideId/title/plainText/moduleSource)。"
                "moduleSource 必须包含 `export default`，禁止 import/require/fetch/eval/new Function/document.cookie/localStorage 等。"
            )
        else:
            mode_line = (
                "当前输出模式尚未接入编辑工具，只能读取上下文并用自然语言回答用户，不要尝试调用修改工具。"
            )
        return (
            "你是知演（ZhiYan）编辑页里的 AI 助手，负责真正完成页面修改，而不是只提建议。\n"
            "要求：\n"
            "- 先用读取类工具确认当前页内容与上下文，再决定怎么改。\n"
            "- 修改请求应优先使用工具完成改稿；只有用户明显在提问时才可以只回答。\n"
            "- 不要输出任何 <think>、thinking、推理过程标签，也不要泄露内部思考。\n"
            "- 最终回复用中文，简洁说明做了什么；如果没有实际修改，要明确说明原因。\n"
            f"- {mode_line}\n"
            "- 当操作意图是 refresh_layout / simplify / add_detail / enrich_visual / change_theme 时，优先修改页面可见内容，而不是只改 speaker notes。\n"
            "- 基础 skill 会由 harness 预先激活；如果任务需要额外 skill，再调用 load_skill。\n"
            "- skill 下的 references/scripts/assets 必须通过 read_skill_resource 读取，不要对 skill 绝对路径使用 read_file。\n"
            "- 可以使用 todo 先整理执行步骤，但不要把 todo 原文当成最终回复。\n\n"
            f"{skill_context}"
        )

    def _build_prompt(self, *, request: EditorLoopRequest, runtime: _EditorRuntimeState) -> str:
        current_slide = runtime.current_slide or {}
        current_layout = str(current_slide.get("layoutId") or current_slide.get("layoutType") or "unknown")
        current_title = _extract_title(current_slide) or f"第 {runtime.current_slide_index + 1} 页"
        current_summary = _summarize_content_data(current_slide.get("contentData"))
        history = request.history[-8:]
        deck_summary = [
            {
                "index": index,
                "layout": slide.get("layoutId") or slide.get("layoutType") or "unknown",
                "title": _extract_title(slide) or f"第 {index + 1} 页",
            }
            for index, slide in enumerate(runtime.slides[:12])
        ]
        slidev_context = (
            f"当前 Slidev deck:\n{request.slidev_markdown.strip()}\n\n"
            if request.output_mode == "slidev" and request.slidev_markdown
            else ""
        )
        return (
            f"当前会话 output_mode: {request.output_mode}\n"
            f"操作意图: {request.action_hint}\n"
            f"演示标题: {request.presentation_title}\n"
            f"当前页索引: {runtime.current_slide_index}\n"
            f"当前页布局: {current_layout}\n"
            f"当前页标题: {current_title}\n"
            f"当前页内容摘要: {current_summary}\n"
            f"整份演示概览: {_safe_json_dumps(deck_summary)}\n"
            f"最近对话: {_safe_json_dumps(history)}\n\n"
            f"当前 Slidev deck 是否存在: {'yes' if request.slidev_markdown else 'no'}\n"
            f"当前 Slidev meta: {_safe_json_dumps(runtime.slidev_meta or {})}\n\n"
            f"{slidev_context}"
            f"用户消息:\n{request.message.strip()}\n\n"
            "请结合工具决定下一步，并在必要时完成真实改稿。"
        )

    def _build_events(
        self,
        *,
        messages: list[Message],
        assistant_reply: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [{"type": "assistant_status", "assistant_status": "thinking"}]
        for message in messages:
            if isinstance(message, AssistantMessage) and message.tool_calls:
                tool_names = [tool_call.tool_name for tool_call in message.tool_calls]
                if any(name in WRITE_TOOLS for name in tool_names):
                    events.append({"type": "assistant_status", "assistant_status": "applying_change"})
                elif any(name in READ_ONLY_TOOLS for name in tool_names):
                    events.append({"type": "assistant_status", "assistant_status": "inspecting_context"})
                events.append({"type": "assistant_status", "assistant_status": "running_tools"})
                for tool_call in message.tool_calls:
                    events.append(
                        {
                            "type": "tool_call",
                            "tool_name": tool_call.tool_name,
                            "call_id": tool_call.tool_call_id,
                            "summary": _tool_call_summary(tool_call.tool_name, tool_call.args),
                        }
                    )
            elif isinstance(message, ToolMessage):
                for result in message.results:
                    events.append(
                        {
                            "type": "tool_result",
                            "tool_name": result.tool_name,
                            "call_id": result.tool_call_id,
                            "ok": not result.is_error,
                            "summary": _tool_result_summary(result),
                        }
                    )
        if assistant_reply:
            events.append({"type": "assistant_status", "assistant_status": "ready"})
        return events

    def _write_snapshot(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_debug_artifacts(
        self,
        artifacts_dir: Path,
        request: EditorLoopRequest,
        runtime: _EditorRuntimeState,
    ) -> None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        request_payload = {
            "message": request.message,
            "action_hint": request.action_hint,
            "output_mode": request.output_mode,
            "current_slide_index": request.current_slide_index,
            "history": request.history,
            "selected_style_id": request.selected_style_id,
        }
        (artifacts_dir / "request.json").write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (artifacts_dir / "presentation.json").write_text(
            json.dumps(
                {
                    "title": request.presentation_title,
                    "slides": runtime.slides,
                    "slidev_markdown": request.slidev_markdown or "",
                    "slidev_meta": request.slidev_meta or {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _write_result_artifact(
        self,
        artifacts_dir: Path,
        *,
        assistant_reply: str,
        runtime: _EditorRuntimeState,
        stop_reason: str,
        error: str | None,
    ) -> None:
        (artifacts_dir / "result.json").write_text(
            json.dumps(
                {
                    "assistant_reply": assistant_reply,
                    "modifications": list(runtime.modifications),
                    "slidev_markdown": runtime.slidev_markdown or "",
                    "slidev_meta": runtime.slidev_meta or {},
                    "slidev_preview_url": runtime.slidev_preview_url,
                    "selected_style_id": runtime.selected_style_id,
                    "stop_reason": stop_reason,
                    "error": error,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _create_model_client(self):
        model_name = str(settings.fast_model or settings.strong_model or "").strip()
        return create_model_client(model_name)


editor_loop_service = EditorLoopService()
