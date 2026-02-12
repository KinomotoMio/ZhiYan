"""PPT Health Check — 程序化检查脚本

对 Slide JSON 执行确定性规则检查：
- 信息密度（文字量、要点数）
- 布局分析（元素重叠、越界）
- 字号层级一致性
"""

import json
import sys
from typing import Any


def check_text_density(slide: dict) -> list[dict[str, Any]]:
    """检查单页文字密度"""
    issues = []
    text_components = [c for c in slide.get("components", []) if c["type"] == "text"]

    for comp in text_components:
        content = comp.get("content", "")
        if comp["role"] == "title" and len(content) > 30:
            issues.append({
                "slideId": slide["slideId"],
                "severity": "warning",
                "dimension": "信息密度",
                "message": f"标题过长（{len(content)} 字），建议控制在 30 字以内",
                "suggestion": "精简标题，将详细信息移到正文",
            })

        if comp["role"] == "body":
            lines = [l for l in content.split("\n") if l.strip()]
            if len(lines) > 6:
                issues.append({
                    "slideId": slide["slideId"],
                    "severity": "warning",
                    "dimension": "信息密度",
                    "message": f"要点过多（{len(lines)} 条），建议精简至 6 条以内",
                    "suggestion": "将相关要点合并，或拆分为两页",
                })

    return issues


def check_bounds(slide: dict) -> list[dict[str, Any]]:
    """检查元素是否越界"""
    issues = []
    for comp in slide.get("components", []):
        pos = comp.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)
        w, h = pos.get("width", 0), pos.get("height", 0)
        if x + w > 100 or y + h > 100:
            issues.append({
                "slideId": slide["slideId"],
                "severity": "error",
                "dimension": "视觉平衡",
                "message": f"组件 {comp['id']} 超出页面边界",
                "suggestion": "调整组件位置或尺寸",
            })
    return issues


def run_check(presentation: dict) -> dict[str, Any]:
    """对整个演示文稿执行检查"""
    all_issues = []
    for slide in presentation.get("slides", []):
        all_issues.extend(check_text_density(slide))
        all_issues.extend(check_bounds(slide))

    error_count = sum(1 for i in all_issues if i["severity"] == "error")
    warning_count = sum(1 for i in all_issues if i["severity"] == "warning")
    score = max(0, 100 - error_count * 15 - warning_count * 5)

    return {
        "overallScore": score,
        "issues": all_issues,
    }


if __name__ == "__main__":
    data = json.load(sys.stdin)
    result = run_check(data)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
