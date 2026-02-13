"""Speaker Notes Generator Agent — 批量生成演讲者注释

所有 slides 生成完毕后，一次 LLM 调用批量生成所有演讲者注释。
使用 fast_model。
"""

from pydantic import BaseModel, Field

_agent = None


class SlideNote(BaseModel):
    slide_number: int
    notes: str = Field(description="50-100 字的演讲者注释")


class AllSpeakerNotes(BaseModel):
    notes: list[SlideNote]


def get_speaker_notes_generator_agent():
    """延迟创建 Agent"""
    global _agent
    if _agent is None:
        from pydantic_ai import Agent

        from app.core.config import settings
        from app.core.model_resolver import resolve_model

        _agent = Agent(
            model=resolve_model(settings.fast_model or settings.default_model),
            output_type=AllSpeakerNotes,
            retries=1,
            instructions=(
                "你是演讲稿撰写助手。根据每页幻灯片的内容，"
                "为演讲者编写简洁的演讲提示。\n\n"
                "## 规则\n"
                "- 每页注释 50-100 字\n"
                "- 包含该页核心要传达的信息\n"
                "- 提供过渡语建议（如何从上一页过渡到这一页）\n"
                "- 标题页和致谢页的注释可以更短\n"
                "- 使用自然口语化的表达\n"
                "- 中文为主"
            ),
        )
    return _agent


def __getattr__(name):
    if name == "speaker_notes_generator_agent":
        return get_speaker_notes_generator_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
