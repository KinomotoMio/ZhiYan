# Baseline 对齐计划（先消明显问题）

## 摘要
目标是先把系统拉回“单一可用基线”，只解决已确认的明显问题：字段不一致、渲染分叉、冗余接入、校验误判与超时。
本阶段不做“质量增强/视觉优化”，只做“对齐和稳定化”。

## 成功标准
1. 生成→预览→校验→PPTX/PDF 的内容语义一致。
2. `contentData` 非空时不再出现“空白页误报”。
3. 校验阶段 vision 超时不再导致整单失败。
4. 导出链路只有一条主路径，冗余路径冻结。

## 固定边界
- API 路径保持不变：`POST /api/v1/export/pptx`、`POST /api/v1/export/pdf`。
- 主数据契约固定为 `layoutId + contentData`。
- `components` 保留只读兼容，不作为新生成主路径。
- 本阶段不引入前端双模式切换。

## 实施批次
1. 字段规范化 + 生成上下文修复 + 单测。
2. 后端 HTML 渲染统一 + PDF/截图链路接入 + 空白页回归。
3. PPTX/reveal 字段对齐 + 冗余导出路径冻结。
4. verify 视觉评估超时降级 + 端到端回归。

## 验收
- 多页生成时，每页传给 slide generator 的 `source_content` 有差异且包含该页关键词。
- `components=[]` 且 `contentData` 非空时，PDF/截图仍有可见内容。
- vision 卡顿时，任务可完成并记录降级告警，不出现 `verify` 阶段超时失败。
