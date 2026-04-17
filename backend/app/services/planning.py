"""Agentic create-page orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.generation import CreateJobRequest
from app.services.generation.agentic import AgentBuilder, Tool, ToolContext, ToolRegistry
from app.services.generation.agentic.tools import load_skill
from app.services.model_clients import create_model_client
from app.services.planning_normalization import normalize_planning_outline
from app.services.skill_runtime.registry import build_skill_catalog


_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")
_PAGE_COUNT_RE = re.compile(r"(?P<count>\d{1,2})\s*页")
_OUTLINE_LINE_RE = re.compile(
    r"^(?:第?\s*(?P<page>\d{1,2})\s*页|(?P<num>\d{1,2})[.)、])\s*(?P<title>[^:：|-]+?)(?:\s*[-|:：]\s*(?P<summary>.+))?$"
)


@dataclass
class PlanningTurnOutcome:
    assistant_message: str
    brief: dict[str, Any]
    outline: dict[str, Any] | None
    outline_version_increment: int = 0
    status: str = "collecting_requirements"
    output_mode: str = "slidev"
    mode_selection_source: str = "default"
    events: list[dict[str, Any]] | None = None
    topic_suggestions: list[dict[str, Any]] = field(default_factory=list)
    assistant_status: str | None = None
    active_job_id: str | None = None


@dataclass
class _TurnState:
    brief: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] | None = None
    topic_suggestions: list[dict[str, Any]] = field(default_factory=list)
    assistant_status: str | None = None
    output_mode: str = "slidev"
    mode_selection_source: str = "default"
    launch_requested: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


class _ReadSourceFileArgs(BaseModel):
    source_id: str = Field(description="Selected source id to inspect.")
    limit: int = Field(default=2400, ge=200, le=8000)


class _SuggestTopicsArgs(BaseModel):
    focus: str = Field(default="", description="Optional direction from the current conversation.")
    count: int = Field(default=4, ge=3, le=5)


class _SubmitBriefArgs(BaseModel):
    topic: str = ""
    audience: str = ""
    objective: str = ""
    style: str = ""
    tone: str = ""
    preferred_pages: int | None = Field(default=None, ge=3, le=20)
    extra_requirements: str = ""


class _OutlineItemArgs(BaseModel):
    slide_number: int | None = None
    title: str
    content_brief: str = ""
    key_points: list[str] = Field(default_factory=list)
    content_hints: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    suggested_slide_role: str = "narrative"
    note: str = ""


class _OutlineArgs(BaseModel):
    narrative_arc: str = "问题→分析→方案→结论"
    items: list[_OutlineItemArgs] = Field(default_factory=list)


class _LaunchGenerationArgs(BaseModel):
    confirmed: bool = False


class _SetOutputModeArgs(BaseModel):
    output_mode: str = Field(description="One of slidev or html.")
    selection_source: str = Field(
        default="natural_language",
        description="How this mode was chosen: default, button, natural_language, or agent_recommendation.",
    )
    reason: str = ""


def _merge_brief(current: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                merged[key] = cleaned
            continue
        if key == "preferred_pages" and isinstance(value, int) and value > 0:
            merged[key] = value
    return merged


def _safe_slug(value: str) -> str:
    cleaned = _FILENAME_SANITIZER.sub("-", value.strip())
    collapsed = cleaned.strip("-._")
    return collapsed[:48] or "source"


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
        "# Create Agent Source Brief",
        "",
        f"- Topic Hint: {payload.get('topic_hint') or ''}",
        f"- Source Count: {payload.get('source_count') or 0}",
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


def _strip_markdown(value: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", value)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    return cleaned.strip()


def _preferred_page_count(user_message: str, brief: dict[str, Any]) -> int | None:
    preferred = brief.get("preferred_pages")
    if isinstance(preferred, int) and preferred > 0:
        return preferred
    matched = _PAGE_COUNT_RE.search(user_message)
    if matched:
        count = int(matched.group("count"))
        if 3 <= count <= 20:
            return count
    return None


def _extract_outline_table_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "|" not in line:
            continue
        parts = [_strip_markdown(cell.strip()) for cell in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        if all(set(cell) <= {"-", ":"} for cell in parts if cell):
            continue
        if any(token in (parts[0] + "".join(parts[1:3])) for token in ("页数", "标题", "内容要点", "角色")):
            continue
        page_cell = parts[0]
        if not page_cell.isdigit():
            continue
        title = parts[2] if len(parts) >= 3 else ""
        summary = parts[3] if len(parts) >= 4 else (parts[2] if len(parts) >= 3 else "")
        rows.append(
            {
                "slide_number": int(page_cell),
                "title": title.strip(),
                "content_brief": summary.strip(),
                "note": summary.strip(),
                "key_points": [summary.strip()] if summary.strip() else [],
            }
        )
    return rows


def _extract_outline_line_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = _strip_markdown(raw_line.strip())
        if not line:
            continue
        matched = _OUTLINE_LINE_RE.match(line)
        if not matched:
            continue
        page_raw = matched.group("page") or matched.group("num")
        if not page_raw:
            continue
        title = (matched.group("title") or "").strip(" -|:：")
        summary = (matched.group("summary") or "").strip()
        rows.append(
            {
                "slide_number": int(page_raw),
                "title": title,
                "content_brief": summary,
                "note": summary,
                "key_points": [summary] if summary else [],
            }
        )
    return rows


def _is_outline_like_text(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if len(_extract_outline_table_rows(normalized)) >= 3:
        return True
    line_rows = _extract_outline_line_rows(normalized)
    if len(line_rows) >= 3:
        return True
    return normalized.count("第 ") >= 3 and "页" in normalized


def _normalize_recovered_outline_items(
    items: list[dict[str, Any]],
    *,
    preferred_pages: int | None,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    for item in items:
        slide_number = int(item.get("slide_number") or 0)
        title = str(item.get("title") or "").strip()
        if slide_number <= 0 or not title or slide_number in seen_numbers:
            continue
        seen_numbers.add(slide_number)
        deduped.append(item)
    deduped.sort(key=lambda row: int(row.get("slide_number") or 0))
    if preferred_pages and len(deduped) > preferred_pages:
        deduped = deduped[:preferred_pages]
    return deduped


class CreateAgentService:
    def __init__(self, session_store) -> None:
        self._session_store = session_store

    async def ensure_opening_message(self, *, workspace_id: str, session_id: str) -> dict | None:
        chats = await self._session_store.list_chat_messages(workspace_id, session_id, limit=300)
        planning_messages = [
            item
            for item in chats
            if isinstance(item.get("model_meta"), dict) and item["model_meta"].get("phase") == "planning"
        ]
        if planning_messages:
            return await self._session_store.get_planning_state(workspace_id, session_id)

        current_state = await self._session_store.get_planning_state(workspace_id, session_id)
        workspace_bundle = await self._prepare_workspace(
            workspace_id=workspace_id,
            session_id=session_id,
            current_state=current_state,
        )
        opening_message, suggestions = self._build_opening_message(workspace_bundle["sources"])
        next_state = await self._session_store.save_planning_state(
            workspace_id=workspace_id,
            session_id=session_id,
            mode="agentic",
            status="collecting_requirements",
            output_mode=(current_state or {}).get("output_mode") or "slidev",
            mode_selection_source=(current_state or {}).get("mode_selection_source") or "default",
            brief=current_state.get("brief") if current_state else {},
            outline=current_state.get("outline") if current_state else {},
            outline_version=int(current_state.get("outline_version") or 0) if current_state else 0,
            source_ids=workspace_bundle["source_ids"],
            source_digest=workspace_bundle["source_digest"],
            outline_stale=bool(current_state.get("outline_stale")) if current_state else False,
            active_job_id=str(current_state.get("active_job_id") or "") if current_state else None,
            agent_workspace_root=str(workspace_bundle["root"]),
            agent_session_version=int(current_state.get("agent_session_version") or 0) if current_state else 0,
            assistant_status="ready",
            topic_suggestions=suggestions,
        )
        await self._session_store.add_chat_message(
            workspace_id=workspace_id,
            session_id=session_id,
            role="assistant",
            content=opening_message,
            model_meta={
                "phase": "planning",
                "message_kind": "assistant_reply",
                "outline_version": next_state.get("outline_version", 0),
            },
        )
        return next_state

    async def handle_turn(
        self,
        *,
        workspace_id: str,
        session_id: str,
        user_message: str,
    ) -> PlanningTurnOutcome:
        current_state = await self._session_store.get_planning_state(workspace_id, session_id)
        workspace_bundle = await self._prepare_workspace(
            workspace_id=workspace_id,
            session_id=session_id,
            current_state=current_state,
        )
        current_outline = dict(current_state.get("outline") or {}) if current_state else {}
        outline_stale = bool(current_state.get("outline_stale")) if current_state else False
        if current_state and current_state.get("source_digest") != workspace_bundle["source_digest"]:
            outline_stale = bool(current_outline.get("items"))

        await self._session_store.add_chat_message(
            workspace_id=workspace_id,
            session_id=session_id,
            role="user",
            content=user_message,
            model_meta={
                "phase": "planning",
                "message_kind": "user_turn",
                "outline_version": int(current_state.get("outline_version") or 0) if current_state else 0,
            },
        )

        turn_state = _TurnState(
            brief=dict(current_state.get("brief") or {}) if current_state else {},
            outline=current_outline if current_outline else None,
            topic_suggestions=list(current_state.get("topic_suggestions") or []) if current_state else [],
            assistant_status="thinking",
            output_mode=str((current_state or {}).get("output_mode") or "slidev"),
            mode_selection_source=str((current_state or {}).get("mode_selection_source") or "default"),
            events=[{"type": "assistant_status", "assistant_status": "thinking"}],
        )

        agent = self._build_agent(
            workspace_root=workspace_bundle["root"],
            turn_state=turn_state,
            source_bundle=workspace_bundle,
            current_state=current_state or {},
        )
        session = agent.start_session(snapshot=workspace_bundle["snapshot"])
        prompt = self._build_turn_prompt(
            user_message=user_message,
            current_state=current_state or {},
            source_bundle=workspace_bundle,
            outline_stale=outline_stale,
        )
        result = await session.send(prompt)
        recovered_outline = self._recover_outline_from_text(
            result.output_text,
            user_message=user_message,
            brief=turn_state.brief or (current_state.get("brief") if current_state else {}) or {},
        )
        recovered_outline_used = False
        if turn_state.outline is None and recovered_outline is not None:
            turn_state.outline = recovered_outline
            turn_state.topic_suggestions = []
            turn_state.assistant_status = "outline_ready"
            turn_state.events.append({"type": "outline_updated", "outline": recovered_outline})
            turn_state.events.append({"type": "assistant_status", "assistant_status": "outline_ready"})
            recovered_outline_used = True

        next_snapshot_version = int(current_state.get("agent_session_version") or 0) + 1 if current_state else 1
        self._write_snapshot(
            workspace_bundle["state_path"],
            {
                "version": next_snapshot_version,
                "session": session.to_snapshot(),
            },
        )

        next_brief = _merge_brief(current_state.get("brief") if current_state else None, turn_state.brief)
        next_outline = turn_state.outline or current_outline or {}
        has_new_outline = bool(turn_state.outline and turn_state.outline.get("items"))
        next_outline_version = int(current_state.get("outline_version") or 0) if current_state else 0
        if has_new_outline:
            next_outline_version += 1
        next_status = "outline_ready" if next_outline.get("items") else "collecting_requirements"
        next_outline_stale = False if has_new_outline else outline_stale
        topic_suggestions = turn_state.topic_suggestions
        assistant_status = turn_state.assistant_status or ("outline_ready" if next_outline.get("items") else "ready")

        next_state = await self._session_store.save_planning_state(
            workspace_id=workspace_id,
            session_id=session_id,
            mode="agentic",
            status=next_status,
            output_mode=turn_state.output_mode,
            mode_selection_source=turn_state.mode_selection_source,
            brief=next_brief,
            outline=next_outline,
            outline_version=next_outline_version,
            source_ids=workspace_bundle["source_ids"],
            source_digest=workspace_bundle["source_digest"],
            outline_stale=next_outline_stale,
            active_job_id=str(current_state.get("active_job_id") or "") if current_state else None,
            agent_workspace_root=str(workspace_bundle["root"]),
            agent_session_version=next_snapshot_version,
            assistant_status=assistant_status,
            topic_suggestions=topic_suggestions,
        )

        assistant_message = result.output_text.strip() or self._fallback_assistant_message(
            topic_suggestions=topic_suggestions,
            outline=next_outline,
            outline_stale=next_outline_stale,
        )
        if recovered_outline_used and _is_outline_like_text(assistant_message):
            assistant_message = self._outline_ready_message()
        if assistant_message:
            await self._session_store.add_chat_message(
                workspace_id=workspace_id,
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                model_meta={
                    "phase": "planning",
                    "message_kind": "assistant_reply",
                    "outline_version": next_outline_version,
                },
            )

        return PlanningTurnOutcome(
            assistant_message=assistant_message,
            brief=next_brief,
            outline=next_outline or None,
            outline_version_increment=1 if has_new_outline else 0,
            status=next_status,
            output_mode=turn_state.output_mode,
            mode_selection_source=turn_state.mode_selection_source,
            events=list(turn_state.events),
            topic_suggestions=topic_suggestions,
            assistant_status=assistant_status,
            active_job_id=next_state.get("active_job_id"),
        )

    def _build_agent(
        self,
        *,
        workspace_root: Path,
        turn_state: _TurnState,
        source_bundle: dict[str, Any],
        current_state: dict[str, Any],
    ):
        builder = AgentBuilder.from_project(workspace_root)
        builder.with_model_client(self._create_model_client())
        builder.with_system_prompt(self._system_prompt())
        builder.with_max_turns(6)
        builder.with_auto_compact(True)
        builder.with_compact_token_threshold(4500)
        builder.skill_catalog = build_skill_catalog(settings.project_root)
        builder.tool_registry = self._build_tool_registry(
            workspace_root=workspace_root,
            turn_state=turn_state,
            source_bundle=source_bundle,
            current_state=current_state,
        )
        return builder.build()

    def _build_tool_registry(
        self,
        *,
        workspace_root: Path,
        turn_state: _TurnState,
        source_bundle: dict[str, Any],
        current_state: dict[str, Any],
    ) -> ToolRegistry:
        registry = ToolRegistry()

        async def _list_selected_sources(_args: BaseModel, _context: ToolContext) -> dict[str, Any]:
            return {
                "source_count": len(source_bundle["sources"]),
                "sources": source_bundle["sources"],
            }

        async def _read_source_brief(_args: BaseModel, _context: ToolContext) -> dict[str, Any]:
            return {
                "path": str(source_bundle["brief_markdown_path"]),
                "content": source_bundle["brief_markdown_path"].read_text(encoding="utf-8"),
            }

        async def _read_source_file(args: _ReadSourceFileArgs, _context: ToolContext) -> dict[str, Any]:
            for source in source_bundle["sources"]:
                if source["id"] != args.source_id:
                    continue
                path = workspace_root / source["workspace_text_path"]
                text = path.read_text(encoding="utf-8") if path.exists() else ""
                truncated = len(text) > args.limit
                return {
                    "source_id": source["id"],
                    "name": source["name"],
                    "content": text[: args.limit],
                    "truncated": truncated,
                }
            raise ValueError(f"Unknown source id: {args.source_id}")

        async def _suggest_topics(args: _SuggestTopicsArgs, _context: ToolContext) -> dict[str, Any]:
            suggestions = self._suggest_topics(
                sources=source_bundle["sources"],
                focus=args.focus,
                count=args.count,
                current_brief=current_state.get("brief") or {},
            )
            turn_state.topic_suggestions = suggestions
            turn_state.assistant_status = "topic_suggestions_ready"
            turn_state.events.append(
                {"type": "topic_suggestions", "topics": suggestions}
            )
            turn_state.events.append(
                {"type": "assistant_status", "assistant_status": "topic_suggestions_ready"}
            )
            return {"topics": suggestions}

        async def _submit_brief(args: _SubmitBriefArgs, _context: ToolContext) -> dict[str, Any]:
            payload = args.model_dump(exclude_none=True)
            turn_state.brief = _merge_brief(turn_state.brief, payload)
            turn_state.events.append({"type": "brief_updated", "brief": turn_state.brief})
            return {"brief": turn_state.brief}

        async def _submit_outline(args: _OutlineArgs, _context: ToolContext) -> dict[str, Any]:
            normalized = normalize_planning_outline(args.model_dump(mode="python"))
            turn_state.outline = normalized
            turn_state.topic_suggestions = []
            turn_state.assistant_status = "outline_ready"
            turn_state.events.append({"type": "outline_updated", "outline": normalized})
            turn_state.events.append({"type": "assistant_status", "assistant_status": "outline_ready"})
            return {
                "status": "ok",
                "item_count": len(normalized.get("items") or []),
            }

        async def _update_outline(args: _OutlineArgs, context: ToolContext) -> dict[str, Any]:
            return await _submit_outline(args, context)

        async def _launch_generation(args: _LaunchGenerationArgs, _context: ToolContext) -> dict[str, Any]:
            if not args.confirmed:
                return {
                    "status": "blocked",
                    "reason": "UI 仍会通过 planning/confirm 显式启动生成，本轮不要直接启动。",
                }
            turn_state.launch_requested = True
            return {"status": "blocked", "reason": "当前创建页仍要求通过 planning/confirm 启动生成。"}

        async def _set_output_mode(args: _SetOutputModeArgs, _context: ToolContext) -> dict[str, Any]:
            normalized = str(args.output_mode or "").strip().lower()
            if normalized not in {"slidev", "html"}:
                raise ValueError("output_mode 仅支持 slidev 或 html。")
            selection_source = str(args.selection_source or "natural_language").strip() or "natural_language"
            turn_state.output_mode = normalized
            turn_state.mode_selection_source = selection_source
            turn_state.events.append(
                {
                    "type": "output_mode_selected",
                    "output_mode": normalized,
                    "selection_source": selection_source,
                    "reason": str(args.reason or "").strip(),
                }
            )
            return {
                "status": "ok",
                "output_mode": normalized,
                "selection_source": selection_source,
            }

        empty_args = type("_EmptyArgs", (BaseModel,), {})
        registry.register(
            Tool(
                name="list_selected_sources",
                description="List selected source materials and light metadata.",
                args_model=empty_args,
                handler=_list_selected_sources,
            )
        )
        registry.register(
            Tool(
                name="read_source_brief",
                description="Read the local source brief synthesized from selected materials.",
                args_model=empty_args,
                handler=_read_source_brief,
            )
        )
        registry.register(
            Tool(
                name="read_source_file",
                description="Read one selected source file by source id when you need more detail.",
                args_model=_ReadSourceFileArgs,
                handler=_read_source_file,
            )
        )
        registry.register(
            Tool(
                name="suggest_topics",
                description="Return 3-5 viable topic directions when the user is unsure what to write.",
                args_model=_SuggestTopicsArgs,
                handler=_suggest_topics,
            )
        )
        registry.register(
            Tool(
                name="submit_brief",
                description="Save stable planning requirements extracted from the conversation.",
                args_model=_SubmitBriefArgs,
                handler=_submit_brief,
            )
        )
        registry.register(
            Tool(
                name="submit_outline",
                description="Submit a fresh outline artifact for the create page.",
                args_model=_OutlineArgs,
                handler=_submit_outline,
            )
        )
        registry.register(
            Tool(
                name="update_outline",
                description="Update the current outline after the user changes direction.",
                args_model=_OutlineArgs,
                handler=_update_outline,
            )
        )
        registry.register(
            Tool(
                name="launch_generation",
                description="Reserved for explicit confirmation flows. Do not use during normal create-page turns.",
                args_model=_LaunchGenerationArgs,
                handler=_launch_generation,
            )
        )
        registry.register(
            Tool(
                name="set_output_mode",
                description="Persist the user's explicitly confirmed output mode choice.",
                args_model=_SetOutputModeArgs,
                handler=_set_output_mode,
            )
        )
        registry.register(getattr(load_skill, "__agentloop_tool__"))
        return registry

    def _system_prompt(self) -> str:
        return (
            "你是知演创建页里的 AI 助手，不是固定问卷。\n"
            "你的目标是像一个真正的助手那样推进：在用户迷茫时先给方向，在信息足够时再沉淀 brief 和大纲。\n\n"
            "工具使用原则：\n"
            "- 先用 `list_selected_sources` 和 `read_source_brief` 建立上下文，必要时再用 `read_source_file`。\n"
            "- 当用户说不知道写什么、主题还没定、想先找切入点时，优先调用 `suggest_topics`，不要只追问两个字段。\n"
            "- 当你识别到稳定需求时，用 `submit_brief` 保存。\n"
            "- 当你已经能给出 4-8 页的页级结构时，必须先调用 `submit_outline` 或 `update_outline`，不要只在正文里写表格或长列表。\n"
            "- 当用户明确说“用 HTML 做”或“就用 Slidev”时，调用 `set_output_mode` 保存这个决定。\n"
            "- 如果你认为另一种输出模式更合适，可以在自然语言里建议，但不要只凭自己的建议调用 `set_output_mode`。\n"
            "- 当任务需要专项 skill 时，先调用 `load_skill` 再应用其规则。\n"
            "- 不要调用 `launch_generation`；创建页仍通过单独的确认按钮开始生成。\n\n"
            "回复要求：\n"
            "- 使用中文，语气自然、有温度。\n"
            "- 回复要推动用户前进，不要重复工具结果。\n"
            "- `topic suggestions` 只通过 UI 卡片展示，不要在正文里复述具体建议，也不要说成是用户提到过的方向。\n"
            "- 如果你已经提交了 outline，正文只用 1-2 句短说明提醒用户可以直接编辑页序和标题。\n"
            "- 只有仍缺少关键信息时才继续追问；如果你已经准备在正文里列第 1 页、第 2 页，就说明应该先提交 outline。\n"
            "- 你可以解释 `slidev` 更适合 markdown-first 快速改稿，`html` 更适合更重的异步强视觉渲染。"
        )

    def _build_turn_prompt(
        self,
        *,
        user_message: str,
        current_state: dict[str, Any],
        source_bundle: dict[str, Any],
        outline_stale: bool,
    ) -> str:
        current_outline = current_state.get("outline") or {}
        return (
            "当前 create-page 内部状态（internal planning state，不是聊天历史）：\n"
            f"- selected_source_count: {len(source_bundle['sources'])}\n"
            f"- outline_stale: {'true' if outline_stale else 'false'}\n"
            f"- current_output_mode: {str(current_state.get('output_mode') or 'slidev')}\n"
            f"- brief_state: {json.dumps(current_state.get('brief') or {}, ensure_ascii=False)}\n"
            f"- outline_state: {json.dumps(current_outline, ensure_ascii=False)}\n"
            f"- pending_topic_suggestion_cards: {'true' if current_state.get('topic_suggestions') else 'false'}\n\n"
            f"用户最新输入：{user_message.strip()}\n\n"
            "请基于这些信息决定下一步。"
        )

    def _create_model_client(self):
        model_name = str(settings.fast_model or settings.strong_model or "").strip()
        return create_model_client(model_name)

    async def _prepare_workspace(
        self,
        *,
        workspace_id: str,
        session_id: str,
        current_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        sources = await self._session_store.list_sources(workspace_id, session_id)
        ready_sources = [source for source in sources if source.get("status") == "ready" and source.get("id")]
        source_ids = [str(source["id"]) for source in ready_sources]
        source_records = await self._session_store.get_workspace_source_records_by_ids(workspace_id, source_ids)
        source_digest = self._compute_source_digest(source_records)
        root = (settings.project_root / "data" / "create-agent" / workspace_id / session_id).resolve()
        sources_dir = root / "sources"
        artifacts_dir = root / "artifacts"
        state_dir = root / "state"
        root.mkdir(parents=True, exist_ok=True)
        sources_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        source_payloads: list[dict[str, Any]] = []
        combined_parts: list[str] = []
        for index, record in enumerate(source_records, start=1):
            source_id = str(record.get("id") or f"source-{index}")
            parsed_content = str(record.get("parsed_content") or "").strip()
            file_name = f"{index:02d}-{source_id}-{_safe_slug(str(record.get('name') or source_id))}.md"
            relative_path = Path("sources") / file_name
            target_path = root / relative_path
            target_path.write_text(parsed_content, encoding="utf-8")
            source_payloads.append(
                {
                    "id": source_id,
                    "name": record.get("name"),
                    "fileCategory": record.get("fileCategory"),
                    "workspace_text_path": str(relative_path),
                    "previewSnippet": record.get("previewSnippet"),
                    "headings": _extract_source_headings(parsed_content),
                    "key_passages": _extract_source_passages(parsed_content),
                }
            )
            combined_parts.append(f"# Source: {record.get('name') or source_id}\n\n{parsed_content}".strip())

        manifest = {
            "source_count": len(source_payloads),
            "source_digest": source_digest,
            "sources": [
                {
                    "id": source["id"],
                    "name": source["name"],
                    "fileCategory": source["fileCategory"],
                    "workspace_text_path": source["workspace_text_path"],
                    "previewSnippet": source["previewSnippet"],
                }
                for source in source_payloads
            ],
        }
        request_payload = {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "source_ids": source_ids,
            "source_digest": source_digest,
            "brief": current_state.get("brief") if current_state else {},
            "outline_version": int(current_state.get("outline_version") or 0) if current_state else 0,
        }
        brief_payload = {
            "topic_hint": (current_state or {}).get("brief", {}).get("topic") if current_state else "",
            "source_count": len(source_payloads),
            "sources": source_payloads,
        }
        brief_markdown = _render_source_brief_markdown(brief_payload)

        (root / "request.json").write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (sources_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (sources_dir / "combined.md").write_text("\n\n---\n\n".join(part for part in combined_parts if part).strip(), encoding="utf-8")
        brief_json_path = artifacts_dir / "source-brief.json"
        brief_markdown_path = artifacts_dir / "source-brief.md"
        brief_json_path.write_text(json.dumps(brief_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        brief_markdown_path.write_text(brief_markdown, encoding="utf-8")

        snapshot_path = state_dir / "agent-session.json"
        snapshot_payload = {}
        if snapshot_path.exists():
            with snapshot_path.open("r", encoding="utf-8") as handle:
                snapshot_payload = json.load(handle)
        return {
            "root": root,
            "state_path": snapshot_path,
            "snapshot": dict(snapshot_payload.get("session") or {}),
            "source_ids": source_ids,
            "source_digest": source_digest,
            "sources": source_payloads,
            "brief_markdown_path": brief_markdown_path,
            "brief_json_path": brief_json_path,
        }

    def _write_snapshot(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_opening_message(self, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        suggestions = self._suggest_topics(sources=sources, focus="", count=4, current_brief={})
        if sources:
            top_names = "、".join(str(source.get("name") or "素材") for source in sources[:3])
            return (
                f"我先看了你当前勾选的素材：{top_names}。如果你还没想好怎么讲，我可以先给你几个切入方向，或者直接按你想要的受众和目标起一版结构。默认我会按 Slidev 这条 markdown-first 路径来准备；如果你更想走 HTML，也可以直接告诉我。",
                suggestions,
            )
        return (
            "我们可以先一起定方向。如果你还没想好写什么，我先给你几个常见的演示题目切口；你也可以直接告诉我想给谁看、希望他们看完形成什么判断。默认会走 Slidev，如果你想改成 HTML，也可以直接说。",
            suggestions,
        )

    def _fallback_assistant_message(
        self,
        *,
        topic_suggestions: list[dict[str, Any]],
        outline: dict[str, Any],
        outline_stale: bool,
    ) -> str:
        if outline_stale:
            return "我注意到素材刚更新了。要不要我按最新素材重新整理一版结构，或者你先告诉我这次想强调哪一部分？"
        if outline.get("items"):
            return self._outline_ready_message()
        if topic_suggestions:
            return "我先给你几种可行方向。你挑一个最接近的，我就顺着它继续起结构。"
        return "我先继续帮你梳理，你也可以直接告诉我这份 PPT 最想讲清楚什么。"

    def _outline_ready_message(self) -> str:
        return "我先整理成一版可编辑提纲了，你可以直接改页序和标题；如果方向对，我就按这版继续生成。"

    def _recover_outline_from_text(
        self,
        text: str,
        *,
        user_message: str,
        brief: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not _is_outline_like_text(text):
            return None
        preferred_pages = _preferred_page_count(user_message, brief)
        items = _extract_outline_table_rows(text)
        if len(items) < 3:
            items = _extract_outline_line_rows(text)
        normalized_items = _normalize_recovered_outline_items(
            items,
            preferred_pages=preferred_pages,
        )
        if len(normalized_items) < 3:
            return None
        return normalize_planning_outline(
            {
                "narrative_arc": "问题→分析→方案→结论",
                "items": normalized_items,
            }
        )

    def _suggest_topics(
        self,
        *,
        sources: list[dict[str, Any]],
        focus: str,
        count: int,
        current_brief: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized_focus = focus.strip()
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()

        for source in sources:
            source_name = str(source.get("name") or "素材")
            for heading in source.get("headings") or []:
                title = str(heading).strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                suggestions.append(
                    {
                        "title": title,
                        "reason": f"可以直接从 {source_name} 里的这个部分展开，比较容易讲成一页一观点的结构。",
                        "prompt": f"做一份围绕「{title}」的演示，帮我先梳理给谁看、核心结论是什么。",
                    }
                )
                if len(suggestions) >= count:
                    return suggestions

        generic_focus = normalized_focus or str(current_brief.get("topic") or "").strip()
        generic_templates = [
            ("现状问题与机会", "先讲现在发生了什么、哪里有机会或风险，适合汇报和沟通共识。"),
            ("方案设计与取舍", "聚焦方案本身，适合提案、评审和对比不同路线。"),
            ("项目复盘与经验", "把过程、结果、经验讲清楚，适合内部分享或复盘。"),
            ("策略建议与下一步", "更偏行动导向，适合希望推动决策或拿到资源支持的场景。"),
            ("新人理解版导览", "把复杂内容讲得更容易懂，适合培训、入门介绍或跨团队同步。"),
        ]
        for title, reason in generic_templates:
            label = f"{generic_focus}：{title}" if generic_focus else title
            if label in seen:
                continue
            seen.add(label)
            suggestions.append(
                {
                    "title": label,
                    "reason": reason,
                    "prompt": f"围绕「{label}」做一份演示，先帮我梳理结构和适合的受众。",
                }
            )
            if len(suggestions) >= count:
                break
        return suggestions[:count]

    def _compute_source_digest(self, source_records: list[dict[str, Any]]) -> str:
        serializable = [
            {
                "id": str(record.get("id") or ""),
                "name": str(record.get("name") or ""),
                "updated_at": str(record.get("updated_at") or ""),
                "content_hash": str(record.get("content_hash") or ""),
            }
            for record in source_records
        ]
        return hashlib.sha256(
            json.dumps(serializable, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


async def ensure_planning_opening(*, workspace_id: str, session_id: str) -> dict | None:
    from app.services.sessions import session_store

    service = CreateAgentService(session_store)
    return await service.ensure_opening_message(workspace_id=workspace_id, session_id=session_id)


async def handle_planning_turn(
    *,
    workspace_id: str,
    session_id: str,
    user_message: str,
) -> PlanningTurnOutcome:
    from app.services.sessions import session_store

    service = CreateAgentService(session_store)
    return await service.handle_turn(
        workspace_id=workspace_id,
        session_id=session_id,
        user_message=user_message,
    )


async def launch_generation_from_planning(
    *,
    workspace_id: str,
    session_id: str,
    topic: str,
    brief: dict[str, Any],
    approved_outline: dict[str, Any],
    source_ids: list[str],
):
    from app.services.generation.job_factory import create_generation_job_record

    return await create_generation_job_record(
        workspace_id=workspace_id,
        req=CreateJobRequest(
            topic=topic,
            content=str(brief.get("extra_requirements") or ""),
            session_id=session_id,
            source_ids=source_ids,
            template_id=None,
            num_pages=len(approved_outline.get("items") or []),
            approved_outline=approved_outline,
        ),
    )


__all__ = [
    "CreateAgentService",
    "PlanningTurnOutcome",
    "ensure_planning_opening",
    "handle_planning_turn",
    "launch_generation_from_planning",
    "normalize_planning_outline",
]
