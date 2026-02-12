"""Layout Verifier Agent — 布局检查 + 审美评估

程序化检查优先，LLM 审美评估作为补充。
"""

import logging

from pydantic import BaseModel, Field

from app.models.slide import Slide

logger = logging.getLogger(__name__)


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


def _compute_overlap(
    x1: float, y1: float, w1: float, h1: float,
    x2: float, y2: float, w2: float, h2: float,
) -> float:
    """计算两个矩形的重叠面积占较小矩形面积的比例"""
    inter_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    inter_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
    inter_area = inter_x * inter_y
    if inter_area == 0:
        return 0.0
    area1 = w1 * h1
    area2 = w2 * h2
    smaller = min(area1, area2)
    if smaller == 0:
        return 0.0
    return inter_area / smaller


def verify_programmatic(slides: list[Slide]) -> list[VerificationIssue]:
    """程序化检查：越界、重叠、文字密度等确定性规则"""
    issues: list[VerificationIssue] = []

    for slide in slides:
        components = slide.components

        for comp in components:
            pos = comp.position
            # 越界检查
            if pos.x + pos.width > 105:  # 5% 容差
                issues.append(
                    VerificationIssue(
                        slide_id=slide.slide_id,
                        severity="error",
                        category="bounds",
                        message=f"组件 {comp.id} 水平越界 (x={pos.x}, w={pos.width})",
                        suggestion="减小宽度或左移组件",
                    )
                )
            if pos.y + pos.height > 105:
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

        # 重叠检测：检查同一页所有组件对
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                ci, cj = components[i], components[j]
                overlap = _compute_overlap(
                    ci.position.x, ci.position.y, ci.position.width, ci.position.height,
                    cj.position.x, cj.position.y, cj.position.width, cj.position.height,
                )
                if overlap > 0.3:  # 重叠面积 > 30% 告警
                    issues.append(
                        VerificationIssue(
                            slide_id=slide.slide_id,
                            severity="warning",
                            category="overlap",
                            message=f"组件 {ci.id} 与 {cj.id} 重叠 {overlap:.0%}",
                            suggestion="调整组件位置避免重叠",
                        )
                    )

    return issues


async def run_aesthetic_verification(slides: list[Slide]) -> VerificationResult | None:
    """可选的 LLM 审美评估（仅在有 API key 时运行）"""
    try:
        agent = _get_aesthetic_verifier_agent()
        slides_summary = "\n".join(
            f"- 第{i+1}页 [{s.layout_type.value}]: "
            f"{_extract_title_from_slide(s)} ({len(s.components)} 个组件)"
            for i, s in enumerate(slides)
        )
        result = await agent.run(
            f"请评估以下演示文稿的设计质量：\n{slides_summary}"
        )
        return result.output
    except Exception as e:
        logger.warning("Aesthetic verification skipped: %s", e)
        return None


def _extract_title_from_slide(slide: Slide) -> str:
    for comp in slide.components:
        if comp.role.value == "title" and comp.content:
            return comp.content
    return "(无标题)"


def _get_aesthetic_verifier_agent():
    """延迟创建 LLM 审美评估 Agent"""
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
