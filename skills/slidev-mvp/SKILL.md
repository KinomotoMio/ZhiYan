---
name: slidev-mvp
description: 将知演大纲渲染为 Slidev Markdown，用于 agentic loop + skill 系统的 dev-only 验证。
version: 0.1.0
command: /slidev-mvp
---

# Slidev MVP Renderer

## 功能

把结构化大纲转换为可被 Slidev 渲染的 Markdown 文档，便于快速验证 harness 控制面。

## 输入

- `parameters.title` — 演示标题
- `parameters.topic` — 主题
- `parameters.outline` — 大纲对象，包含 `items`
- `parameters.theme` — Slidev theme
- `parameters.paginate` — 是否启用分页

## 输出

```json
{
  "markdown": "---\\ntheme: default\\n---\\n# 标题\\n..."
}
```
