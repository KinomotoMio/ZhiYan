# Built-in Template Taxonomy 审校定版

## 摘要
本记录用于承接 `#62`，对当前 16 个 built-in template 做一次完整的人工审校，
输出 `group / sub-group / variant` 三层归属结论。

本记录消费 `#67` 中已经固定的 taxonomy 语义，不重新定义三层概念。
它的目标是给后续 metadata、catalog、selector 与 notes 线路提供统一输入，
而不是直接修改运行时代码。

## 审校口径

### 上游语义
本记录以 [layout-taxonomy-decision.md](./layout-taxonomy-decision.md) 为唯一 taxonomy 口径：

- `group`：页面功能定位
- `sub-group`：单个 group 内的信息结构细分，单选
- `variant`：在 `group + sub-group` 已确定之后的设计排版扩散

### 当前阶段的默认规则
- 如果模板的主要差异体现在信息如何被组织，则优先记为 `sub-group`
- `variant` 的对象结构和值域以 [layout-variant-decision.md](./layout-variant-decision.md) 为准
- 本记录不再把 `variant` 一律暂记为 `default`，而是回写当前 16 个 built-in template 的正式 variant 归属
- 除 narrative 试点外，本轮仍不主动为其他 group 发明新的 `sub-group`
- 本轮审校只对 built-in template 给出人工归属结论，不改共享 metadata，也不改 selector

### 审校来源
本轮结论以以下现状为证据源：

- `shared/layout-metadata.json` 中当前的 `role / variant / usage`
- 前后端 registry 中当前已注册的 built-in layout 清单
- `/dev/layout-catalog` 中对每个 built-in layout 的 preview、Group、Variant、Usage 与 Notes 展示

## 全量审校结果

| `layoutId` | 当前系统归属 | 审校后 `group` | 审校后 `sub-group` | 审校后 `variant` | 结论类型 | 人工判断理由 |
|---|---|---|---|---|---|---|
| `intro-slide` | `cover / default` | `cover` | `default` | `{ composition: hero-center, tone: formal, style: editorial, density: low }` | `补充正式 variant` | 该页承担封面职责，结构层保持默认，设计层以开场式主视觉与低密度编排定版。 |
| `outline-slide` | `agenda / default` | `agenda` | `default` | `{ composition: card-grid, tone: formal, style: card-based, density: medium }` | `补充正式 variant` | 目录页的稳定设计差异体现在卡片网格骨架和中等承载度。 |
| `section-header` | `section-divider / default` | `section-divider` | `default` | `{ composition: section-break, tone: assertive, style: minimal, density: low }` | `补充正式 variant` | 章节过渡页继续保留默认结构，但设计层已能明确为切换感强、低密度的分隔骨架。 |
| `bullet-with-icons` | `narrative / icon-points` | `narrative` | `icon-points` | `{ composition: icon-columns, tone: assertive, style: icon-led, density: medium }` | `新增或调整 sub-group + 定义 variant` | 图标分点属于结构层，同时其多列图标化编排和强调型气质可稳定沉淀为正式 variant。 |
| `image-and-description` | `narrative / visual-explainer` | `narrative` | `visual-explainer` | `{ composition: media-split, tone: approachable, style: editorial, density: medium }` | `新增或调整 sub-group + 定义 variant` | 主视觉加说明文字继续作为 `sub-group`，设计层则定版为图文分栏、亲和讲解型 variant。 |
| `bullet-icons-only` | `narrative / capability-grid` | `narrative` | `capability-grid` | `{ composition: capability-grid, tone: assertive, style: icon-led, density: high }` | `新增或调整 sub-group + 定义 variant` | 能力矩阵属于结构层，同时其高密度、图标驱动的网格呈现已具备稳定的设计变体语义。 |
| `metrics-slide` | `evidence / default` | `evidence` | `default` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` | `补充正式 variant` | 指标卡片页在默认 evidence 结构下，可明确沉淀为数据优先、指标网格型 variant。 |
| `metrics-with-image` | `evidence / default` | `evidence` | `default` | `{ composition: media-split, tone: assertive, style: data-first, density: medium }` | `补充正式 variant` | 虽仍归 evidence 默认结构，但设计层已稳定体现为数据与配图并置的分栏 variant。 |
| `chart-with-bullets` | `evidence / default` | `evidence` | `default` | `{ composition: analysis-split, tone: formal, style: data-first, density: high }` | `补充正式 variant` | 图表与解读并置的分析骨架足以作为正式 variant，而不必先升级为新的 `sub-group`。 |
| `table-info` | `evidence / default` | `evidence` | `default` | `{ composition: table-dominant, tone: formal, style: data-first, density: high }` | `补充正式 variant` | 表格主导的证据页目前仍可留在 evidence 默认结构，但设计层已能明确为高密度表格型 variant。 |
| `two-column-compare` | `comparison / default` | `comparison` | `default` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` | `补充正式 variant` | 标准双栏对比页的设计特征主要体现在卡片化双栏骨架。 |
| `challenge-outcome` | `comparison / default` | `comparison` | `default` | `{ composition: dual-columns, tone: assertive, style: minimal, density: medium }` | `补充正式 variant` | 问题到方案映射仍属 comparison 默认结构，但设计层气质和视觉语言已与标准对比页拉开差异。 |
| `numbered-bullets` | `process / default` | `process` | `default` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` | `补充正式 variant` | 步骤页的稳定差异集中在顺序清单骨架和中性说明气质。 |
| `timeline` | `process / default` | `process` | `default` | `{ composition: timeline-band, tone: formal, style: minimal, density: medium }` | `补充正式 variant` | 时间线虽然仍保留 process 默认结构，但设计层已经形成清晰的带状时间轴 variant。 |
| `quote-slide` | `highlight / default` | `highlight` | `default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` | `补充正式 variant` | 强调页的设计差异稳定落在单句聚焦和 statement 风格上。 |
| `thank-you` | `closing / default` | `closing` | `default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` | `补充正式 variant` | 结尾页的正式 variant 应表达收束感与庆祝/致谢型气质，而不是继续停留在默认占位。 |

## 分组结论摘要

### `narrative`
本轮唯一明确需要从旧 `variant` 迁移出结构层的 `group` 仍然是 `narrative`。

最终结论：

- `icon-points` 作为 `bullet-with-icons` 的 `sub-group`
- `visual-explainer` 作为 `image-and-description` 的 `sub-group`
- `capability-grid` 作为 `bullet-icons-only` 的 `sub-group`
- narrative 组下三个模板都已经补足正式 variant 对象

这意味着 `narrative` 原来的“多 `variant` 试点”，在新语义下应理解为“多 `sub-group` 试点”。

### 其余 group
本轮继续保持以下 group 为默认结构：

- `cover`
- `agenda`
- `section-divider`
- `evidence`
- `comparison`
- `process`
- `highlight`
- `closing`

原因不是这些组永远不需要细分，而是：

- 当前 taxonomy 的首要目标是先让三层语义稳定
- 除 narrative 外，其余 built-in template 虽然存在结构差异的讨论空间，但还不足以在本轮直接固化为正式 `sub-group`
- 先把这些组统一记为 `sub-group=default`，可以避免在人工审校尚未完全收口时，把新的结构分类提前写死到实现层
- 但这些组下的模板已经补足正式 `variant` 对象，用于表达设计排版扩散

### 关于 `variant`
本轮已经为所有 built-in template 输出正式 `variant` 对象归属。

统一结论：

- 当前所有 built-in template 的 `variant` 都应视为四字段对象，而不再是单值 `default`
- narrative 原来的三个旧 `variant` 名称已迁移为 `sub-group`
- 具体字段和值域以 [layout-variant-decision.md](./layout-variant-decision.md) 为准

## 对后续实现的要求
- metadata / catalog / selector 后续只能消费本记录中的审校结论，不得继续直接沿用旧 `group + variant` 假设
- 若后续要为 `evidence / comparison / process` 增加新的 `sub-group`，应基于模板页的稳定结构差异另行决策
- `#68` 应把本记录中的 `group / sub-group / variant` 结论视为 notes 聚合的上游输入
- 后续实现 issue 不得把 `variant` 重新降回单值字符串语义

## 本记录不做什么
- 不修改 `shared/layout-metadata.json`
- 不修改 `frontend/src/lib/template-registry.ts`
- 不修改 `backend/app/models/layout_registry.py`
- 不修改 `/dev/layout-catalog`
- 不修改 selector prompt 或选择逻辑
- 不定义 notes 最终格式

## 状态
本记录构成 `#62` 的人工审校定版结论。
后续若需要进一步细化其他 group 的 `sub-group` 或为某些模板正式命名 `variant`，
应通过新的 issue 或决策记录推进，而不是在实现 PR 中静默扩写。
