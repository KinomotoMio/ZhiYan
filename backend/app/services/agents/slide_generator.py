"""Slide Generator Agent — 按 layout schema 生成结构化内容

新版：动态创建 Agent 实例，每个 slide 使用其 layout 对应的 Pydantic output_type。
输出严格匹配 layout schema，前端直接用对应 React 组件渲染。
"""

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Agent 缓存：layout_id → Agent 实例
_agent_cache: dict[str, object] = {}


SLIDE_GEN_INSTRUCTIONS = (
    "你是幻灯片内容撰写专家。根据大纲和源文档，为指定布局生成结构化内容。\n\n"
    "## 核心规则\n"
    "- 严格按照输出 schema 的字段和约束生成内容\n"
    "- 标题简洁有力（不超过 15 个字为佳）\n"
    "- 要点精炼，每条不超过 20 个字\n"
    "- 数字要具体、有对比性（如 97.3% vs 94.5%）\n"
    "- 中文为主，专业术语保留英文原文\n"
    "- 不要编造数据，基于源文档内容\n\n"
    "## 图标（icon.query）规则\n"
    "- 使用英文关键词描述图标语义\n"
    "- 常见映射: speed/zap, security/shield, target/goal, users/team, "
    "chart/data, globe/world, lightbulb/idea, rocket/growth, "
    "heart/care, star/quality, check/success, clock/time, "
    "code/tech, cloud/saas, lock/privacy\n\n"
    "## 图片（image.prompt）规则\n"
    "- 用简洁的英文描述图片内容\n"
    "- 风格偏商务/科技/极简\n"
    "- 例: 'modern office with digital screens showing analytics'\n"
)


def _get_agent_for_layout(layout_id: str, output_model: type[BaseModel]):
    """获取或创建指定 layout 的 Agent 实例"""
    if layout_id not in _agent_cache:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent_cache[layout_id] = Agent(
            model=resolve_model(settings.strong_model),
            output_type=output_model,
            instructions=SLIDE_GEN_INSTRUCTIONS,
        )
    return _agent_cache[layout_id]


async def generate_slide_content(
    layout_id: str,
    slide_number: int,
    title: str,
    content_brief: str,
    key_points: list[str],
    source_content: str,
) -> dict:
    """为单页幻灯片生成结构化内容

    Args:
        layout_id: 布局 ID（从 layout_registry 查找 output_model）
        slide_number: 页码
        title: 标题方向
        content_brief: 内容简述
        key_points: 核心要点
        source_content: 关联的源文档内容

    Returns:
        结构化内容 dict（匹配 layout 的 Pydantic schema）
    """
    from app.models.layout_registry import get_output_model

    output_model = get_output_model(layout_id)
    agent = _get_agent_for_layout(layout_id, output_model)

    points_text = "\n".join(f"- {p}" for p in key_points) if key_points else "无"
    prompt = (
        f"幻灯片 #{slide_number}\n"
        f"布局类型: {layout_id}\n"
        f"标题方向: {title}\n"
        f"内容简述: {content_brief}\n"
        f"核心要点:\n{points_text}\n\n"
        f"源文档内容:\n{source_content[:3000]}"
    )

    result = await agent.run(prompt)
    usage = result.usage()
    if usage.requests > 1:
        logger.warning(
            "Slide %d (layout=%s) required %d LLM requests (retries occurred)",
            slide_number, layout_id, usage.requests,
        )
    return result.output.model_dump()


def invalidate_cache() -> None:
    """清除 Agent 缓存（设置变更时调用）"""
    _agent_cache.clear()


# 向后兼容：保留旧 Agent 接口（供 chat_agent 等可能的引用）
class SlideContent(BaseModel):
    """旧版内容模型 — 向后兼容"""

    title: str
    layout_type: str = "title-content"
    body_text: str | None = None
    speaker_notes: str = ""
    needs_image: bool = False
    image_description: str | None = None


_legacy_agent = None


def get_slide_generator_agent():
    """向后兼容的旧版 Agent"""
    global _legacy_agent
    if _legacy_agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _legacy_agent = Agent(
            model=resolve_model(settings.strong_model),
            output_type=SlideContent,
            instructions=SLIDE_GEN_INSTRUCTIONS,
        )
    return _legacy_agent


def __getattr__(name):
    if name == "slide_generator_agent":
        return get_slide_generator_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
