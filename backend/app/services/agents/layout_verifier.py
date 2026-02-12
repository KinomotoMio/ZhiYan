"""Layout Verifier Agent — 布局检查 + 审美评估

程序化检查优先，LLM 审美评估作为补充。
"""

from pydantic import BaseModel, Field

from app.models.slide import Slide


class VerificationIssue(BaseModel):
    slide_id: str
    severity: str = Field(description="error | warning | info")
    category: str = Field(description="bounds | overlap | density | aesthetic")
    message: str
    suggestion: str


class VerificationResult(BaseModel):
    passed: bool
    issues: list[VerificationIssue]
    score: int = Field(ge=0, le=100, description="总体质量评分")


def verify_programmatic(slides: list[Slide]) -> list[VerificationIssue]:
    """程序化检查：越界、溢出、重叠等确定性规则"""
    issues: list[VerificationIssue] = []

    for slide in slides:
        for comp in slide.components:
            pos = comp.position
            # 越界检查
            if pos.x + pos.width > 100:
                issues.append(
                    VerificationIssue(
                        slide_id=slide.slide_id,
                        severity="error",
                        category="bounds",
                        message=f"组件 {comp.id} 水平越界 (x={pos.x}, w={pos.width})",
                        suggestion="减小宽度或左移组件",
                    )
                )
            if pos.y + pos.height > 100:
                issues.append(
                    VerificationIssue(
                        slide_id=slide.slide_id,
                        severity="error",
                        category="bounds",
                        message=f"组件 {comp.id} 垂直越界 (y={pos.y}, h={pos.height})",
                        suggestion="减小高度或上移组件",
                    )
                )

            # 文字密度检查
            if comp.type.value == "text" and comp.role.value == "body" and comp.content:
                lines = [l for l in comp.content.split("\n") if l.strip()]
                if len(lines) > 6:
                    issues.append(
                        VerificationIssue(
                            slide_id=slide.slide_id,
                            severity="warning",
                            category="density",
                            message=f"组件 {comp.id} 要点过多（{len(lines)} 条）",
                            suggestion="精简至 6 条以内，或拆分为两页",
                        )
                    )

    return issues


def get_aesthetic_verifier_agent():
    """延迟创建 LLM 审美评估 Agent（仅在程序化检查通过后调用）"""
    from pydantic_ai import Agent

    return Agent(
        model="openai:gpt-4o-mini",
        output_type=VerificationResult,
        instructions=(
            "你是一个演示文稿设计评审专家。评估幻灯片的视觉质量。\n"
            "检查维度：配色协调性、信息密度合理性、视觉层级清晰度。\n"
            "给出 0-100 的评分和具体改进建议。"
        ),
    )
