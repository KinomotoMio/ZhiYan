"""Slide generator agent for structured layout content."""

import logging
import time

from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    "## 图片（image）规则\n"
    "- 每张图片都必须显式输出 `source`，取值只能是 `ai`、`user`、`existing`\n"
    "- 当 `source='ai'`：使用简洁英文写图片 prompt，`url` 留空\n"
    "- 当 `source='user'`：使用中文写用户补图/上传说明，`url` 留空\n"
    "- 当 `source='existing'`：若已有可用链接则填入 `url`，否则保留 `url` 为空并说明待绑定的现有素材\n"
    "- 不要默认所有图片都是 AI 生成图\n"
    "- AI 图片风格偏商务/科技/极简\n"
    "- 例: 'modern office with digital screens showing analytics'\n"
)


def _get_agent_for_layout(layout_id: str, output_model: type[BaseModel]):
    """Get or create the cached agent for a layout."""
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
    source_references: list[str] | None = None,
    job_id: str | None = None,
    stage: str = "slides",
) -> dict:
    """Generate structured content for a single slide."""
    from app.models.layout_registry import get_output_model

    output_model = get_output_model(layout_id)
    agent = _get_agent_for_layout(layout_id, output_model)

    points_text = "\n".join(f"- {p}" for p in key_points) if key_points else "无"
    refs = [str(ref).strip() for ref in (source_references or []) if str(ref).strip()]
    refs = refs[:20]
    refs_text = "\n".join(f"- {ref}" for ref in refs) if refs else "无"
    prompt = (
        f"幻灯片 #{slide_number}\n"
        f"布局类型: {layout_id}\n"
        f"标题方向: {title}\n"
        f"内容简述: {content_brief}\n"
        f"核心要点:\n{points_text}\n\n"
        f"证据引用(source_references):\n{refs_text}\n\n"
        f"源文档内容:\n{source_content[:3000]}"
    )

    from app.core.config import settings

    t0 = time.monotonic()
    result = await agent.run(prompt)
    usage = result.usage()
    if usage.requests > 1:
        logger.warning(
            "Slide %d (layout=%s) required %d LLM requests (retries occurred)",
            slide_number,
            layout_id,
            usage.requests,
        )
    logger.info(
        "slide_generation_call",
        extra={
            "event": "slide_generation_call",
            "job_id": job_id,
            "stage": stage,
            "slide_index": max(0, slide_number - 1),
            "model": settings.strong_model,
            "provider": settings.strong_model.split(":", 1)[0],
            "attempt": usage.requests,
            "token_usage": str(usage),
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        },
    )
    return result.output.model_dump()


def invalidate_cache() -> None:
    """Clear cached layout agents after config changes."""
    _agent_cache.clear()


class SlideContent(BaseModel):
    """Legacy output model kept for backward compatibility."""

    title: str
    layout_type: str = "title-content"
    body_text: str | None = None
    speaker_notes: str = ""
    needs_image: bool = False
    image_description: str | None = None


_legacy_agent = None


def get_slide_generator_agent():
    """Return the legacy slide generator agent."""
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
