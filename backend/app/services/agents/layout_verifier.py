"""Layout Verifier Agent — 布局检查 + 多模态审美评估

程序化检查优先，LLM 审美评估作为补充。
支持 vision：有截图时用 BinaryContent 发送图片给多模态 LLM，否则回退到文本摘要。

支持两种 Slide 格式：
- 新版：layoutId + contentData（模板系统，检查内容合理性）
- 旧版：components 列表（检查位置越界、重叠、密度）
"""

import asyncio
import json
import logging
import re

from pydantic import BaseModel, Field

from app.models.slide import Slide

logger = logging.getLogger(__name__)

_agent = None


class VerificationIssue(BaseModel):
    slide_id: str
    severity: str = Field(description="error | warning | info")
    category: str = Field(description="bounds | overlap | density | content | aesthetic")
    message: str
    suggestion: str
    source: str | None = None
    tier: str | None = None


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


def _verify_content_data(slide: Slide) -> list[VerificationIssue]:
    """新版 contentData slide 的内容合理性检查"""
    issues: list[VerificationIssue] = []
    data = slide.content_data or {}
    sid = slide.slide_id

    # 标题长度检查
    title = data.get("title", "")
    if isinstance(title, str) and len(title) > 40:
        issues.append(VerificationIssue(
            slide_id=sid,
            severity="warning",
            category="content",
            message=f"标题过长（{len(title)} 字）",
            suggestion="精简标题至 40 字以内",
        ))

    # 列表项数量检查
    for key in ("items", "metrics", "bullets", "events", "steps", "features"):
        items = data.get(key)
        if isinstance(items, list) and len(items) > 6:
            issues.append(VerificationIssue(
                slide_id=sid,
                severity="warning",
                category="content",
                message=f"'{key}' 项目过多（{len(items)} 条）",
                suggestion="精简至 6 条以内，或拆分为两页",
            ))

    # 表格行数检查
    rows = data.get("rows")
    if isinstance(rows, list) and len(rows) > 8:
        issues.append(VerificationIssue(
            slide_id=sid,
            severity="warning",
            category="content",
            message=f"表格行数过多（{len(rows)} 行）",
            suggestion="精简至 8 行以内",
        ))

    return issues


def _verify_components(slide: Slide) -> list[VerificationIssue]:
    """旧版 components slide 的位置检查"""
    issues: list[VerificationIssue] = []
    components = slide.components
    sid = slide.slide_id

    for comp in components:
        pos = comp.position
        if pos.x + pos.width > 105:
            issues.append(VerificationIssue(
                slide_id=sid,
                severity="error",
                category="bounds",
                message=f"组件 {comp.id} 水平越界 (x={pos.x}, w={pos.width})",
                suggestion="减小宽度或左移组件",
            ))
        if pos.y + pos.height > 105:
            issues.append(VerificationIssue(
                slide_id=sid,
                severity="error",
                category="bounds",
                message=f"组件 {comp.id} 垂直越界 (y={pos.y}, h={pos.height})",
                suggestion="减小高度或上移组件",
            ))

        if comp.type.value == "text" and comp.role.value == "body" and comp.content:
            lines = [line for line in comp.content.split("\n") if line.strip()]
            if len(lines) > 6:
                issues.append(VerificationIssue(
                    slide_id=sid,
                    severity="warning",
                    category="density",
                    message=f"组件 {comp.id} 要点过多（{len(lines)} 条）",
                    suggestion="精简至 6 条以内，或拆分为两页",
                ))

    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            ci, cj = components[i], components[j]
            overlap = _compute_overlap(
                ci.position.x, ci.position.y, ci.position.width, ci.position.height,
                cj.position.x, cj.position.y, cj.position.width, cj.position.height,
            )
            if overlap > 0.3:
                issues.append(VerificationIssue(
                    slide_id=sid,
                    severity="warning",
                    category="overlap",
                    message=f"组件 {ci.id} 与 {cj.id} 重叠 {overlap:.0%}",
                    suggestion="调整组件位置避免重叠",
                ))

    return issues


def verify_programmatic(slides: list[Slide]) -> list[VerificationIssue]:
    """程序化检查：根据 slide 类型分派不同检查逻辑"""
    issues: list[VerificationIssue] = []

    for slide in slides:
        if slide.content_data and slide.layout_id:
            issues.extend(_verify_content_data(slide))
        else:
            issues.extend(_verify_components(slide))

    return issues


def _extract_title_from_slide(slide: Slide) -> str:
    """从 slide 提取标题（兼容新旧格式）"""
    if slide.content_data:
        title = slide.content_data.get("title")
        if isinstance(title, str) and title:
            return title
    for comp in slide.components:
        if comp.role.value == "title" and comp.content:
            return comp.content
    return "(无标题)"


async def run_aesthetic_verification(
    slides: list[Slide],
    presentation_dict: dict | None = None,
    vision_timeout_seconds: float | None = None,
) -> VerificationResult | None:
    """LLM 审美评估 — 优先使用截图多模态，回退到文本摘要"""
    vision_timed_out = False
    try:
        agent = _get_aesthetic_verifier_agent()

        if presentation_dict is not None:
            try:
                if vision_timeout_seconds and vision_timeout_seconds > 0:
                    raw_text = await asyncio.wait_for(
                        _run_vision_verification(agent, slides, presentation_dict),
                        timeout=vision_timeout_seconds,
                    )
                else:
                    raw_text = await _run_vision_verification(agent, slides, presentation_dict)
                return _parse_aesthetic_text(raw_text, slides)
            except asyncio.TimeoutError:
                vision_timed_out = True
                logger.warning(
                    "Vision verification timed out after %.1fs, falling back to text",
                    vision_timeout_seconds or 0.0,
                )
            except Exception as e:
                logger.warning("Vision verification failed, falling back to text: %s", e)

        slides_summary = "\n".join(
            f"- 第{i+1}页 [{slide.layout_id or slide.layout_type}]: "
            f"{_extract_title_from_slide(slide)}"
            f"{' (' + str(len(slide.components)) + ' 个组件)' if slide.components else ''}"
            for i, slide in enumerate(slides)
        )
        result = await agent.run(
            f"请评估以下演示文稿的设计质量：\n{slides_summary}"
        )
        output = _parse_aesthetic_text(str(result.output), slides)
        if vision_timed_out and slides:
            output.issues.append(
                VerificationIssue(
                    slide_id=slides[0].slide_id,
                    severity="warning",
                    category="aesthetic",
                    message="视觉截图评估超时，已降级为文本审美评估",
                    suggestion="减少页数、降低视觉评估复杂度，或延长 verify 超时预算",
                    source="vision_timeout_fallback",
                    tier="advisory",
                )
            )
        return output
    except Exception as e:
        logger.warning("Aesthetic verification skipped: %s", e)
        return None


async def _run_vision_verification(
    agent, slides: list[Slide], presentation_dict: dict
) -> str:
    """使用截图 + BinaryContent 进行多模态审美评估"""
    from pydantic_ai import BinaryContent

    from app.services.export.slide_screenshot import capture_slide_screenshots

    screenshots = await capture_slide_screenshots(presentation_dict)
    if not screenshots:
        raise ValueError("No screenshots captured")

    logger.info("Captured %d slide screenshots for vision verification", len(screenshots))

    user_prompt: list[str | BinaryContent] = [
        f"请评估以下演示文稿（共 {len(screenshots)} 页）的视觉设计质量。"
        f"以下是每页渲染后的截图：",
    ]
    for i, ss in enumerate(screenshots):
        user_prompt.append(f"第 {i + 1} 页 (ID: {ss.slide_id}):")
        user_prompt.append(BinaryContent(data=ss.png_bytes, media_type="image/png"))

    result = await agent.run(user_prompt)
    return str(result.output)


def _get_aesthetic_verifier_agent():
    """延迟创建 LLM 审美评估 Agent（使用 vision_model）"""
    global _agent
    if _agent is not None:
        return _agent

    from pydantic_ai import Agent

    from app.core.config import settings
    from app.core.model_resolver import resolve_model

    _agent = Agent(
        model=resolve_model(settings.vision_model),
        output_type=str,
        instructions=(
            "你是一个演示文稿设计评审专家。评估幻灯片的视觉质量。\n"
            "检查维度：配色协调性、信息密度合理性、视觉层级清晰度、留白是否充足、排版整洁度。\n"
            "如果收到截图，请基于实际视觉效果进行评估。\n"
            "请优先输出 JSON，格式如下：\n"
            '{"score": 0-100, "issues": [{"slide_id":"slide-1","severity":"warning","category":"aesthetic","message":"问题描述","suggestion":"修改建议"}]}\n'
            "无法输出 JSON 时，也请至少给出评分和可执行建议。"
        ),
    )
    return _agent


def _parse_aesthetic_text(raw_text: str, slides: list[Slide]) -> VerificationResult:
    text = (raw_text or "").strip()
    if not text:
        return VerificationResult(passed=True, issues=[], score=80)

    json_candidate = _extract_json_block(text)
    if json_candidate is not None:
        parsed = _parse_json_result(json_candidate, slides)
        if parsed is not None:
            return parsed

    score = _extract_score(text)
    return VerificationResult(passed=True, issues=[], score=score)


def _extract_json_block(text: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    direct = re.search(r"(\{[\s\S]*\})", text)
    if direct:
        return direct.group(1)
    return None


def _parse_json_result(payload: str, slides: list[Slide]) -> VerificationResult | None:
    try:
        obj = json.loads(payload)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    score_raw = obj.get("score")
    try:
        score = int(score_raw)
    except Exception:
        score = 80
    score = max(0, min(score, 100))

    issues_raw = obj.get("issues", [])
    issues: list[VerificationIssue] = []
    default_slide_id = slides[0].slide_id if slides else "slide-1"
    valid_slide_ids = {slide.slide_id for slide in slides}
    for entry in issues_raw if isinstance(issues_raw, list) else []:
        if not isinstance(entry, dict):
            continue
        slide_id = str(entry.get("slide_id") or default_slide_id)
        if valid_slide_ids and slide_id not in valid_slide_ids:
            slide_id = default_slide_id

        severity = str(entry.get("severity") or "warning").lower()
        if severity not in {"warning", "info"}:
            severity = "warning"

        category = str(entry.get("category") or "aesthetic").lower()
        message = str(entry.get("message") or "").strip()
        suggestion = str(entry.get("suggestion") or "").strip()
        if not message or not suggestion:
            continue

        issues.append(
            VerificationIssue(
                slide_id=slide_id,
                severity=severity,
                category=category,
                message=message,
                suggestion=suggestion,
                source="vision",
                tier="advisory",
            )
        )

    return VerificationResult(passed=True, issues=issues, score=score)


def _extract_score(text: str) -> int:
    candidates = re.findall(r"(\d{1,3})\s*(?:/|分|score)?\s*100?", text, flags=re.IGNORECASE)
    if candidates:
        try:
            score = int(candidates[0])
            return max(0, min(score, 100))
        except Exception:
            pass
    return 80
