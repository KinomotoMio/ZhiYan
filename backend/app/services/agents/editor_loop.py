"""Editor-specific agent loop service for the slide editor chat panel."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.model_status import parse_provider
from app.services.generation.agentic import AgentBuilder, LiteLLMModelClient, SkillCatalog, Tool, ToolContext, ToolRegistry
from app.services.generation.agentic.tools import todo
from app.services.generation.agentic.types import AssistantMessage, Message, ToolMessage, ToolResult
from app.services.html_deck import normalize_html_deck

from .chat_agent import (
    DEFAULT_COMPARE_FILLER,
    DEFAULT_COMPARE_LEFT_HEADING,
    DEFAULT_COMPARE_RIGHT_HEADING,
    SlideModification,
)


_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_LINE_RE = re.compile(r"(?im)^\s*</?think\b[^>]*>\s*$")
_THINK_INLINE_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)

_HTML_SECTION_RE = re.compile(
    r"<section\b([^>]*)>(.*?)</section>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_ATTR_RE = re.compile(
    r'data-(slide-id|slide-title)\s*=\s*"([^"]*)"|data-(slide-id|slide-title)\s*=\s*\'([^\']*)\'',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

READ_ONLY_TOOLS = {
    "todo",
    "get_current_slide_info",
    "get_deck_summary",
    "get_current_html_slide_info",
}
WRITE_TOOLS = {
    "modify_slide_title",
    "modify_slide_content",
    "modify_slide_speaker_notes",
    "update_two_column_compare",
    "submit_html_revision",
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


class _ModifyTitleArgs(BaseModel):
    slide_index: int = Field(ge=0)
    new_title: str


class _ModifyContentArgs(BaseModel):
    slide_index: int = Field(ge=0)
    field_path: str
    new_value: str


class _ModifyNotesArgs(BaseModel):
    slide_index: int = Field(ge=0)
    new_notes: str


class _CompareArgs(BaseModel):
    slide_index: int = Field(ge=0)
    left_items: list[str] | None = None
    right_items: list[str] | None = None
    left_heading: str | None = None
    right_heading: str | None = None


class _SubmitHtmlRevisionArgs(BaseModel):
    html: str
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
    html_content: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class EditorLoopOutcome:
    assistant_reply: str
    events: list[dict[str, Any]]
    modifications: list[SlideModification]
    slides: list[dict[str, Any]]
    html_content: str | None = None
    normalized_presentation: dict[str, Any] | None = None
    normalized_html_meta: dict[str, Any] | None = None

    @property
    def modification_count(self) -> int:
        return len(self.modifications)

    @property
    def effective_modification_count(self) -> int:
        if not self.modifications:
            return 0
        return sum(1 for item in self.modifications if item.action != "update_notes")


@dataclass(slots=True)
class _EditorRuntimeState:
    request: EditorLoopRequest
    current_slide_index: int
    slides: list[dict[str, Any]]
    html_content: str | None
    submitted_html: str | None = None
    normalized_presentation: dict[str, Any] | None = None
    normalized_html_meta: dict[str, Any] | None = None
    modifications: list[SlideModification] = field(default_factory=list)
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


def _is_new_format(slide: dict[str, Any]) -> bool:
    return bool(slide.get("contentData") and slide.get("layoutId"))


def _is_scalar_field(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _sanitize_items(items: list[str], *, fallback: str) -> list[str]:
    cleaned: list[str] = []
    for raw in items:
        text = str(raw).strip()
        if not text:
            continue
        cleaned.append(text[:80])
    if not cleaned:
        return [fallback]
    return cleaned[:8]


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


def _extract_data_attr(attrs: str, expected_name: str) -> str:
    for match in _HTML_ATTR_RE.finditer(attrs):
        left_name = (match.group(1) or "").lower()
        left_value = match.group(2) or ""
        right_name = (match.group(3) or "").lower()
        right_value = match.group(4) or ""
        if left_name == expected_name:
            return left_value.strip()
        if right_name == expected_name:
            return right_value.strip()
    return ""


def _html_slide_summaries(html: str) -> list[dict[str, Any]]:
    slides: list[dict[str, Any]] = []
    for index, match in enumerate(_HTML_SECTION_RE.finditer(html), start=1):
        attrs = match.group(1) or ""
        body = match.group(2) or ""
        title = _extract_data_attr(attrs, "slide-title") or f"第 {index} 页"
        slide_id = _extract_data_attr(attrs, "slide-id") or f"slide-{index}"
        plain_body = _truncate(_WS_RE.sub(" ", _TAG_RE.sub(" ", body)).strip(), limit=160)
        slides.append(
            {
                "index": index - 1,
                "slide_id": slide_id,
                "title": title,
                "body_summary": plain_body,
            }
        )
    return slides


def _tool_call_summary(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "todo":
        return "整理本轮执行步骤"
    if tool_name == "get_current_slide_info":
        return "读取当前页详细结构"
    if tool_name == "get_deck_summary":
        return "读取整份演示摘要"
    if tool_name == "get_current_html_slide_info":
        return "读取当前 HTML 页面结构"
    if tool_name == "modify_slide_title":
        return f"修改第 {int(args.get('slide_index', 0)) + 1} 页标题"
    if tool_name == "modify_slide_content":
        field_name = str(args.get("field_path") or "字段")
        return f"修改第 {int(args.get('slide_index', 0)) + 1} 页 {field_name}"
    if tool_name == "modify_slide_speaker_notes":
        return f"修改第 {int(args.get('slide_index', 0)) + 1} 页演讲者注释"
    if tool_name == "update_two_column_compare":
        return f"更新第 {int(args.get('slide_index', 0)) + 1} 页双栏要点"
    if tool_name == "submit_html_revision":
        return "提交整份 HTML 改稿"
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
    if tool_result.tool_name in {"get_current_slide_info", "get_deck_summary", "get_current_html_slide_info"}:
        return "已读取所需上下文"
    if isinstance(content, dict):
        return _truncate(str(content.get("message") or content.get("status") or "工具执行完成"))
    return _truncate(str(content or "工具执行完成"))


class EditorLoopService:
    def __init__(self) -> None:
        self._model_client_factory = self._create_model_client

    async def run(self, request: EditorLoopRequest) -> EditorLoopOutcome:
        workspace_bundle = self._prepare_workspace(request)
        runtime = _EditorRuntimeState(
            request=request,
            current_slide_index=request.current_slide_index,
            slides=json.loads(json.dumps(request.slides, ensure_ascii=False)),
            html_content=request.html_content,
        )
        self._write_debug_artifacts(workspace_bundle["artifacts_dir"], request, runtime)

        builder = AgentBuilder.from_project(workspace_bundle["root"])
        builder.with_model_client(self._model_client_factory())
        builder.with_system_prompt(self._system_prompt(request))
        builder.with_max_turns(max(8, settings.agentic_max_turns))
        builder.with_auto_compact(True)
        builder.with_compact_token_threshold(4500)
        builder.tool_registry = self._build_tool_registry(runtime=runtime)
        builder.skill_catalog = SkillCatalog()
        agent = builder.build()
        session = agent.start_session(snapshot=workspace_bundle["snapshot"])
        prompt = self._build_prompt(request=request, runtime=runtime)

        start_index = len(session.messages)
        result = await session.send(prompt)
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
            html_content=runtime.submitted_html,
            normalized_presentation=runtime.normalized_presentation,
            normalized_html_meta=runtime.normalized_html_meta,
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
            "html_content": request.html_content or "",
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

        async def _get_current_html_slide_info(_args: _NoArgs, _context: ToolContext) -> dict[str, Any]:
            html = runtime.submitted_html or runtime.html_content or ""
            slides = _html_slide_summaries(html)
            current = slides[runtime.current_slide_index] if 0 <= runtime.current_slide_index < len(slides) else None
            return {
                "slide_count": len(slides),
                "current_slide": current,
                "slides": slides,
                "message": "已读取当前 HTML 页面结构",
            }

        async def _modify_slide_title(args: _ModifyTitleArgs, _context: ToolContext) -> dict[str, Any]:
            slide = self._get_slide(runtime, args.slide_index)
            new_title = args.new_title.strip()[:30]
            if _is_new_format(slide):
                slide.setdefault("contentData", {})["title"] = new_title
            else:
                for comp in slide.get("components", []):
                    if comp.get("role") == "title":
                        comp["content"] = new_title
                        break
                else:
                    slide.setdefault("components", []).append({"role": "title", "content": new_title})
            runtime.modifications.append(
                SlideModification(
                    slide_index=args.slide_index,
                    action="update_title",
                    data={"new_title": new_title},
                )
            )
            return {"message": f"已修改第 {args.slide_index + 1} 页标题"}

        async def _modify_slide_content(args: _ModifyContentArgs, _context: ToolContext) -> dict[str, Any]:
            slide = self._get_slide(runtime, args.slide_index)
            new_value = args.new_value.strip()
            field_path = args.field_path.strip()
            if _is_new_format(slide):
                content_data = slide.setdefault("contentData", {})
                existing = content_data.get(field_path)
                if field_path in content_data and not _is_scalar_field(existing):
                    raise ValueError(f"字段 {field_path} 为结构化内容，不能直接覆盖为纯文本。")
                content_data[field_path] = new_value
                action = "update_content_data"
            else:
                for comp in slide.get("components", []):
                    if comp.get("role") == field_path or (field_path == "body" and comp.get("role") == "body"):
                        comp["content"] = new_value
                        break
                else:
                    slide.setdefault("components", []).append({"role": field_path, "content": new_value})
                action = "update_body"
            runtime.modifications.append(
                SlideModification(
                    slide_index=args.slide_index,
                    action=action,
                    data={"field": field_path, "value": new_value},
                )
            )
            return {"message": f"已更新第 {args.slide_index + 1} 页 {field_path}"}

        async def _modify_slide_speaker_notes(args: _ModifyNotesArgs, _context: ToolContext) -> dict[str, Any]:
            slide = self._get_slide(runtime, args.slide_index)
            slide["speakerNotes"] = args.new_notes.strip()
            runtime.modifications.append(
                SlideModification(
                    slide_index=args.slide_index,
                    action="update_notes",
                    data={"new_notes": args.new_notes.strip()},
                )
            )
            return {"message": f"已更新第 {args.slide_index + 1} 页演讲者注释"}

        async def _update_two_column_compare(args: _CompareArgs, _context: ToolContext) -> dict[str, Any]:
            slide = self._get_slide(runtime, args.slide_index)
            if slide.get("layoutId") != "two-column-compare":
                raise ValueError(f"第 {args.slide_index + 1} 页布局不是 two-column-compare。")
            content = slide.setdefault("contentData", {})
            left_raw = content.get("left")
            right_raw = content.get("right")
            left = left_raw if isinstance(left_raw, dict) else {}
            right = right_raw if isinstance(right_raw, dict) else {}
            next_left_items = (
                _sanitize_items(args.left_items or [], fallback=DEFAULT_COMPARE_FILLER)
                if args.left_items is not None
                else _sanitize_items([str(item) for item in left.get("items", [])], fallback=DEFAULT_COMPARE_FILLER)
            )
            next_right_items = (
                _sanitize_items(args.right_items or [], fallback=DEFAULT_COMPARE_FILLER)
                if args.right_items is not None
                else _sanitize_items([str(item) for item in right.get("items", [])], fallback=DEFAULT_COMPARE_FILLER)
            )
            content["left"] = {
                "heading": (args.left_heading or str(left.get("heading") or left.get("title") or "")).strip()
                or DEFAULT_COMPARE_LEFT_HEADING,
                "items": next_left_items,
            }
            content["right"] = {
                "heading": (args.right_heading or str(right.get("heading") or right.get("title") or "")).strip()
                or DEFAULT_COMPARE_RIGHT_HEADING,
                "items": next_right_items,
            }
            runtime.modifications.append(
                SlideModification(
                    slide_index=args.slide_index,
                    action="update_two_column_compare",
                    data={
                        "left_heading": content["left"]["heading"],
                        "right_heading": content["right"]["heading"],
                        "left_items_count": len(next_left_items),
                        "right_items_count": len(next_right_items),
                    },
                )
            )
            return {"message": f"已更新第 {args.slide_index + 1} 页双栏要点"}

        async def _submit_html_revision(args: _SubmitHtmlRevisionArgs, _context: ToolContext) -> dict[str, Any]:
            normalized_html, meta, presentation = normalize_html_deck(
                html=args.html,
                fallback_title=runtime.request.presentation_title,
                expected_slide_count=len(runtime.slides) if runtime.slides else None,
                existing_slides=runtime.slides,
            )
            runtime.submitted_html = normalized_html
            runtime.normalized_presentation = presentation
            runtime.normalized_html_meta = meta
            runtime.modifications.append(
                SlideModification(
                    slide_index=max(0, runtime.current_slide_index),
                    action="update_html_deck",
                    data={"summary": (args.summary or "").strip()},
                )
            )
            return {"message": "已提交并校验 HTML 改稿"}

        if runtime.request.output_mode == "html":
            registry.extend(
                [
                    Tool(
                        name="get_current_html_slide_info",
                        description="Read the current HTML slide summary for the active page.",
                        args_model=_NoArgs,
                        handler=_get_current_html_slide_info,
                        source="editor",
                    ),
                    Tool(
                        name="modify_slide_speaker_notes",
                        description="Update speaker notes for one slide.",
                        args_model=_ModifyNotesArgs,
                        handler=_modify_slide_speaker_notes,
                        source="editor",
                    ),
                    Tool(
                        name="submit_html_revision",
                        description="Submit the full revised HTML deck after editing.",
                        args_model=_SubmitHtmlRevisionArgs,
                        handler=_submit_html_revision,
                        source="editor",
                    ),
                    getattr(todo, "__agentloop_tool__"),
                ]
            )
            return registry

        registry.extend(
            [
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
                Tool(
                    name="modify_slide_title",
                    description="Update a slide title in the structured presentation.",
                    args_model=_ModifyTitleArgs,
                    handler=_modify_slide_title,
                    source="editor",
                ),
                Tool(
                    name="modify_slide_content",
                    description="Update a scalar content field in the structured presentation.",
                    args_model=_ModifyContentArgs,
                    handler=_modify_slide_content,
                    source="editor",
                ),
                Tool(
                    name="modify_slide_speaker_notes",
                    description="Update speaker notes for one slide.",
                    args_model=_ModifyNotesArgs,
                    handler=_modify_slide_speaker_notes,
                    source="editor",
                ),
                Tool(
                    name="update_two_column_compare",
                    description="Update headings and items for a two-column-compare slide.",
                    args_model=_CompareArgs,
                    handler=_update_two_column_compare,
                    source="editor",
                ),
                getattr(todo, "__agentloop_tool__"),
            ]
        )
        return registry

    def _system_prompt(self, request: EditorLoopRequest) -> str:
        mode_line = (
            "当前工作模式是 HTML deck 全稿改写，必须在准备好后使用 submit_html_revision 提交完整 HTML。"
            if request.output_mode == "html"
            else "当前工作模式是结构化 slide 改稿，优先直接修改当前页对应的结构化字段。"
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
            "- two-column-compare 页面优先使用 update_two_column_compare。\n"
            "- 可以使用 todo 先整理执行步骤，但不要把 todo 原文当成最终回复。"
        )

    def _build_prompt(self, *, request: EditorLoopRequest, runtime: _EditorRuntimeState) -> str:
        if request.output_mode == "html":
            html_slides = _html_slide_summaries(runtime.html_content or "")
            current_meta = (
                runtime.slides[runtime.current_slide_index]
                if 0 <= runtime.current_slide_index < len(runtime.slides)
                else {}
            )
            current_html_slide = (
                html_slides[runtime.current_slide_index]
                if 0 <= runtime.current_slide_index < len(html_slides)
                else None
            )
            deck_summary = []
            for index, slide in enumerate(html_slides[:12]):
                meta = runtime.slides[index] if index < len(runtime.slides) else {}
                deck_summary.append(
                    {
                        "index": slide.get("index"),
                        "slide_id": slide.get("slide_id"),
                        "title": slide.get("title"),
                        "body_summary": slide.get("body_summary"),
                        "speaker_notes": str(meta.get("speakerNotes") or ""),
                    }
                )
            current_title = (
                str((current_html_slide or {}).get("title") or "")
                or str(current_meta.get("contentData", {}).get("title") or "")
                or f"第 {runtime.current_slide_index + 1} 页"
            )
            current_summary = str((current_html_slide or {}).get("body_summary") or "HTML 页面摘要为空")
            current_notes = str(current_meta.get("speakerNotes") or "")
            history = request.history[-8:]
            return (
                f"当前会话 output_mode: {request.output_mode}\n"
                f"操作意图: {request.action_hint}\n"
                f"演示标题: {request.presentation_title}\n"
                f"当前页索引: {runtime.current_slide_index}\n"
                f"当前页标题: {current_title}\n"
                f"当前页 HTML 摘要: {current_summary}\n"
                f"当前页演讲者注释: {current_notes}\n"
                f"整份 HTML 演示概览: {_safe_json_dumps(deck_summary)}\n"
                f"最近对话: {_safe_json_dumps(history)}\n\n"
                f"用户消息:\n{request.message.strip()}\n\n"
                "如需修改页面可见内容，直接改完整 HTML 并通过 submit_html_revision 提交；不要输出结构化 slide 修改方案。"
            )

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
                    "html_content": request.html_content or "",
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
                    "modifications": [item.model_dump(mode="json") for item in runtime.modifications],
                    "submitted_html": runtime.submitted_html or "",
                    "normalized_presentation": runtime.normalized_presentation,
                    "normalized_html_meta": runtime.normalized_html_meta,
                    "stop_reason": stop_reason,
                    "error": error,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _get_slide(self, runtime: _EditorRuntimeState, slide_index: int) -> dict[str, Any]:
        if slide_index < 0 or slide_index >= len(runtime.slides):
            raise ValueError(f"幻灯片索引 {slide_index} 超出范围（共 {len(runtime.slides)} 页）")
        return runtime.slides[slide_index]

    def _create_model_client(self) -> LiteLLMModelClient:
        model_name = str(settings.fast_model or settings.strong_model or "").strip()
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
        return LiteLLMModelClient(model=model_name, api_key=api_key, api_base=api_base)


editor_loop_service = EditorLoopService()
