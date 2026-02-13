"""Chat Agent — 对话 + 幻灯片修改 tools

PydanticAI tools 允许 agent 在对话中修改幻灯片内容。
修改通过 RunContext deps 中的 presentation state 实现。

支持两种 slide 格式：
- 新版：layoutId + contentData（优先通过 contentData 修改标题/内容）
- 旧版：components 列表（通过 role 查找组件修改）
"""

from dataclasses import dataclass, field

from pydantic import BaseModel


class SlideModification(BaseModel):
    """单次幻灯片修改记录"""
    slide_index: int
    action: str  # "update_title" | "update_body" | "update_content_data" | "add_slide" | "delete_slide"
    data: dict


@dataclass
class ChatDeps:
    """Chat agent 的依赖注入"""
    slides: list[dict] = field(default_factory=list)
    current_slide_index: int = 0
    modifications: list[SlideModification] = field(default_factory=list)


_agent = None
DEFAULT_COMPARE_LEFT_HEADING = "要点 A"
DEFAULT_COMPARE_RIGHT_HEADING = "要点 B"
DEFAULT_COMPARE_FILLER = "内容生成中"


def _is_new_format(slide: dict) -> bool:
    """判断 slide 是否使用新版 contentData 格式"""
    return bool(slide.get("contentData") and slide.get("layoutId"))


def _is_scalar_field(value) -> bool:
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


def get_chat_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent, RunContext
        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.strong_model),
            deps_type=ChatDeps,
            instructions=(
                "你是知演（ZhiYan）的 AI 助手，帮助用户优化和调整演示文稿。\n"
                "你可以：\n"
                "- 回答关于演示文稿内容的问题\n"
                "- 使用工具修改幻灯片标题、正文、添加或删除幻灯片\n"
                "- 当用户要求修改某页时，先用工具完成修改，再向用户确认\n\n"
                "规则：\n"
                "- 用户说「当前页」指 current_slide_index 对应的那页\n"
                "- 修改标题不超过 15 字\n"
                "- 正文要点每条不超过 20 字，最多 5 条\n"
                "- 不要把对象/列表字段（如 left/right/items/metrics）整体改成纯文本\n"
                "- two-column-compare 布局请优先使用双栏工具修改 left/right 的 heading/items\n"
                "- 回复简洁，修改后说明做了什么改动\n"
                "- 回复使用中文，专业术语保留英文"
            ),
        )

        @_agent.tool
        async def modify_slide_title(ctx: RunContext[ChatDeps], slide_index: int, new_title: str) -> str:
            """修改指定幻灯片的标题。slide_index 从 0 开始。"""
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围（共 {len(deps.slides)} 页）"
            slide = deps.slides[slide_index]

            if _is_new_format(slide):
                slide["contentData"]["title"] = new_title
                deps.modifications.append(SlideModification(
                    slide_index=slide_index,
                    action="update_title",
                    data={"new_title": new_title},
                ))
                return f"已将第 {slide_index + 1} 页标题修改为「{new_title}」"

            for comp in slide.get("components", []):
                if comp.get("role") == "title":
                    comp["content"] = new_title
                    deps.modifications.append(SlideModification(
                        slide_index=slide_index,
                        action="update_title",
                        data={"new_title": new_title},
                    ))
                    return f"已将第 {slide_index + 1} 页标题修改为「{new_title}」"
            return f"第 {slide_index + 1} 页没有标题组件"

        @_agent.tool
        async def modify_slide_content(ctx: RunContext[ChatDeps], slide_index: int, field_path: str, new_value: str) -> str:
            """修改幻灯片 contentData 中的任意字段。
            field_path 为顶层字段名（如 'subtitle', 'description', 'quote'）。
            对于旧版幻灯片，field_path 用 'body' 修改正文组件。
            """
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围（共 {len(deps.slides)} 页）"
            slide = deps.slides[slide_index]

            if _is_new_format(slide):
                if field_path in slide["contentData"]:
                    existing = slide["contentData"][field_path]
                    if not _is_scalar_field(existing):
                        return (
                            f"第 {slide_index + 1} 页字段 '{field_path}' 为结构化内容，"
                            "不能直接用文本覆盖。请改用更细粒度字段或其他修改工具。"
                        )
                    slide["contentData"][field_path] = new_value
                    deps.modifications.append(SlideModification(
                        slide_index=slide_index,
                        action="update_content_data",
                        data={"field": field_path, "value": new_value},
                    ))
                    return f"已更新第 {slide_index + 1} 页的 {field_path}"
                return f"第 {slide_index + 1} 页的 contentData 中没有字段 '{field_path}'"

            for comp in slide.get("components", []):
                if comp.get("role") == field_path or (field_path == "body" and comp.get("role") == "body"):
                    comp["content"] = new_value
                    deps.modifications.append(SlideModification(
                        slide_index=slide_index,
                        action="update_body",
                        data={"new_body": new_value},
                    ))
                    return f"已更新第 {slide_index + 1} 页正文内容"
            return f"第 {slide_index + 1} 页没有 '{field_path}' 组件"

        @_agent.tool
        async def modify_slide_speaker_notes(ctx: RunContext[ChatDeps], slide_index: int, new_notes: str) -> str:
            """修改指定幻灯片的演讲者注释。"""
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围（共 {len(deps.slides)} 页）"
            deps.slides[slide_index]["speakerNotes"] = new_notes
            deps.modifications.append(SlideModification(
                slide_index=slide_index,
                action="update_notes",
                data={"new_notes": new_notes},
            ))
            return f"已更新第 {slide_index + 1} 页演讲者注释"

        @_agent.tool
        async def update_two_column_compare(
            ctx: RunContext[ChatDeps],
            slide_index: int,
            left_items: list[str] | None = None,
            right_items: list[str] | None = None,
            left_heading: str | None = None,
            right_heading: str | None = None,
        ) -> str:
            """更新 two-column-compare 幻灯片的双栏标题与要点。"""
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围（共 {len(deps.slides)} 页）"

            slide = deps.slides[slide_index]
            if not _is_new_format(slide):
                return f"第 {slide_index + 1} 页不是 contentData 结构，无法更新双栏内容"

            if slide.get("layoutId") != "two-column-compare":
                return f"第 {slide_index + 1} 页布局不是 two-column-compare"

            content = slide.setdefault("contentData", {})
            left_raw = content.get("left")
            right_raw = content.get("right")
            left = left_raw if isinstance(left_raw, dict) else {}
            right = right_raw if isinstance(right_raw, dict) else {}

            left_title = (left_heading or str(left.get("heading") or left.get("title") or "")).strip()
            right_title = (right_heading or str(right.get("heading") or right.get("title") or "")).strip()

            next_left_items = (
                _sanitize_items(left_items, fallback=DEFAULT_COMPARE_FILLER)
                if left_items is not None
                else _sanitize_items([str(x) for x in left.get("items", [])], fallback=DEFAULT_COMPARE_FILLER)
            )
            next_right_items = (
                _sanitize_items(right_items, fallback=DEFAULT_COMPARE_FILLER)
                if right_items is not None
                else _sanitize_items([str(x) for x in right.get("items", [])], fallback=DEFAULT_COMPARE_FILLER)
            )

            content["left"] = {
                "heading": left_title or DEFAULT_COMPARE_LEFT_HEADING,
                "items": next_left_items,
            }
            content["right"] = {
                "heading": right_title or DEFAULT_COMPARE_RIGHT_HEADING,
                "items": next_right_items,
            }

            deps.modifications.append(
                SlideModification(
                    slide_index=slide_index,
                    action="update_two_column_compare",
                    data={
                        "left_heading": content["left"]["heading"],
                        "right_heading": content["right"]["heading"],
                        "left_items_count": len(next_left_items),
                        "right_items_count": len(next_right_items),
                    },
                )
            )
            return (
                f"已更新第 {slide_index + 1} 页双栏内容："
                f"左栏 {len(next_left_items)} 条，右栏 {len(next_right_items)} 条"
            )

        @_agent.tool
        async def delete_slide(ctx: RunContext[ChatDeps], slide_index: int) -> str:
            """删除指定幻灯片。"""
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围"
            if len(deps.slides) <= 1:
                return "错误：至少保留一页幻灯片"
            removed = deps.slides.pop(slide_index)
            deps.modifications.append(SlideModification(
                slide_index=slide_index,
                action="delete_slide",
                data={"removed_slide_id": removed.get("slideId", "")},
            ))
            return f"已删除第 {slide_index + 1} 页"

        @_agent.tool
        async def get_slide_info(ctx: RunContext[ChatDeps], slide_index: int) -> str:
            """获取指定幻灯片的详细信息。"""
            deps = ctx.deps
            if slide_index < 0 or slide_index >= len(deps.slides):
                return f"错误：幻灯片索引 {slide_index} 超出范围"
            slide = deps.slides[slide_index]

            layout = slide.get("layoutId") or slide.get("layoutType", "unknown")
            info_parts = [f"第 {slide_index + 1} 页 (布局: {layout})"]

            if _is_new_format(slide):
                cd = slide["contentData"]
                if cd.get("title"):
                    info_parts.append(f"  [标题] {cd['title']}")
                for key in ("subtitle", "description", "quote"):
                    if cd.get(key):
                        info_parts.append(f"  [{key}] {str(cd[key])[:80]}")
                for key in ("items", "metrics", "bullets", "events", "steps"):
                    if cd.get(key) and isinstance(cd[key], list):
                        info_parts.append(f"  [{key}] {len(cd[key])} 项")
                if isinstance(cd.get("left"), dict):
                    left_heading = cd["left"].get("heading") or cd["left"].get("title") or "左栏"
                    left_items = cd["left"].get("items")
                    if isinstance(left_items, list):
                        info_parts.append(f"  [{left_heading}] {len(left_items)} 项")
                if isinstance(cd.get("right"), dict):
                    right_heading = cd["right"].get("heading") or cd["right"].get("title") or "右栏"
                    right_items = cd["right"].get("items")
                    if isinstance(right_items, list):
                        info_parts.append(f"  [{right_heading}] {len(right_items)} 项")
            else:
                for comp in slide.get("components", []):
                    info_parts.append(f"  [{comp.get('role', '?')}] {(comp.get('content', '') or '')[:80]}")

            if slide.get("speakerNotes"):
                info_parts.append(f"  [演讲者注释] {slide['speakerNotes'][:80]}")
            return "\n".join(info_parts)

    return _agent


def __getattr__(name):
    if name == "chat_agent":
        return get_chat_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
