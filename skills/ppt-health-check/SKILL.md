---
name: ppt-health-check
description: 检查 PPT 质量，基于专业评价标准分析信息密度、视觉平衡、叙事连贯性、配色一致性等维度，输出问题列表和改进建议。
version: 0.1.0
command: /ppt-health-check
---

# PPT Health Check

## 功能

对当前演示文稿的所有页面执行全面质量检查，输出结构化的问题列表和改进建议。

## 检查维度

1. **信息密度** — 每页文字量是否合理（标题 ≤ 10 字，要点 ≤ 6 条）
2. **视觉平衡** — 元素分布是否均匀，是否存在大面积留白或过度拥挤
3. **叙事连贯性** — 页面之间的逻辑衔接是否通顺
4. **配色一致性** — 是否偏离模板主题色
5. **字号层级** — 标题/正文/注释的字号是否形成清晰的视觉层级

## 输出格式

```json
{
  "overallScore": 85,
  "issues": [
    {
      "slideId": "slide-3",
      "severity": "warning",
      "dimension": "信息密度",
      "message": "第 3 页要点过多（8 条），建议精简至 5 条以内",
      "suggestion": "将相关要点合并，或拆分为两页"
    }
  ]
}
```

## Scripts

- `scripts/check.py` — 执行程序化检查（字数统计、布局分析）
