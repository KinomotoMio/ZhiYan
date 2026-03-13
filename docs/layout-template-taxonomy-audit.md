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
- 如果模板尚未有稳定、可复用的设计扩散命名，则 `variant` 暂记为 `default`
- 除 narrative 试点外，本轮不主动为其他 group 发明新的 `sub-group` 或多维 `variant`
- 本轮审校只对 built-in template 给出人工归属结论，不改共享 metadata，也不改 selector

### 审校来源
本轮结论以以下现状为证据源：

- `shared/layout-metadata.json` 中当前的 `role / variant / usage`
- 前后端 registry 中当前已注册的 built-in layout 清单
- `/dev/layout-catalog` 中对每个 built-in layout 的 preview、Group、Variant、Usage 与 Notes 展示

## 全量审校结果

| layoutId | 当前系统归属 | 审校后 `group` | 审校后 `sub-group` | 审校后 `variant` | 结论类型 | 人工判断理由 |
|---|---|---|---|---|---|---|
| `intro-slide` | `cover / default` | `cover` | `default` | `default` | `保留归属` | 该页承担封面职责，当前没有第二种稳定的信息结构分流。 |
| `outline-slide` | `agenda / default` | `agenda` | `default` | `default` | `保留归属` | 该页负责目录导航，当前只有一种明确的章节骨架结构。 |
| `section-header` | `section-divider / default` | `section-divider` | `default` | `default` | `保留归属` | 该页承担章节过渡，不需要额外结构层细分。 |
| `bullet-with-icons` | `narrative / icon-points` | `narrative` | `icon-points` | `default` | `新增或调整 sub-group` | 图标分点是正文页的信息组织方式，属于结构层而不是设计扩散。 |
| `image-and-description` | `narrative / visual-explainer` | `narrative` | `visual-explainer` | `default` | `新增或调整 sub-group` | 主视觉加说明文字定义的是正文承载结构，应迁移为 `sub-group`。 |
| `bullet-icons-only` | `narrative / capability-grid` | `narrative` | `capability-grid` | `default` | `新增或调整 sub-group` | 能力矩阵/图标网格属于稳定的结构差异，不再作为旧 `variant` 继续保留。 |
| `metrics-slide` | `evidence / default` | `evidence` | `default` | `default` | `保留归属` | 当前仍可统一视为证据页下的默认结构，本轮不额外拆分指标型子结构。 |
| `metrics-with-image` | `evidence / default` | `evidence` | `default` | `default` | `保留归属` | 虽然包含视觉元素，但本轮尚不足以单独固化为稳定的 `sub-group`。 |
| `chart-with-bullets` | `evidence / default` | `evidence` | `default` | `default` | `保留归属` | 图表解读与其他证据页存在差异，但本轮先保持 evidence 默认结构，避免过早膨胀 taxonomy。 |
| `table-info` | `evidence / default` | `evidence` | `default` | `default` | `保留归属` | 表格页暂统一留在 evidence 默认结构，待后续实现 issue 再决定是否细分。 |
| `two-column-compare` | `comparison / default` | `comparison` | `default` | `default` | `保留归属` | 该页承担并列对比职责，但本轮不把对比结构继续拆成更多 `sub-group`。 |
| `challenge-outcome` | `comparison / default` | `comparison` | `default` | `default` | `保留归属` | 问题到方案的映射仍归在 comparison 组内，本轮先不单列结构子类。 |
| `numbered-bullets` | `process / default` | `process` | `default` | `default` | `保留归属` | 该页承担步骤/方法流程，本轮默认仍归于 process 默认结构。 |
| `timeline` | `process / default` | `process` | `default` | `default` | `保留归属` | 时间线存在潜在结构差异，但本轮暂不继续拆分 `process` 组。 |
| `quote-slide` | `highlight / default` | `highlight` | `default` | `default` | `保留归属` | 单点强调页当前只有一种稳定结构，无需新增层级。 |
| `thank-you` | `closing / default` | `closing` | `default` | `default` | `保留归属` | 收尾页继续作为 closing 默认结构，不为设计排版单独命名。 |

## 分组结论摘要

### `narrative`
本轮唯一明确需要从旧 `variant` 迁移出结构层的 group 仍然是 `narrative`。

最终结论：

- `icon-points` 作为 `bullet-with-icons` 的 `sub-group`
- `visual-explainer` 作为 `image-and-description` 的 `sub-group`
- `capability-grid` 作为 `bullet-icons-only` 的 `sub-group`
- narrative 组下当前所有 template 的 `variant` 统一暂记为 `default`

这意味着 narrative 原来的“多 variant 试点”，在新语义下应理解为“多 `sub-group` 试点”。

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
- 先把这些组统一记为 `sub-group=default`，可以避免在人工审校尚未完全收口时，把新的分类提前写死到实现层

### 关于 `variant`
本轮没有为任何 built-in template 输出新的正式 `variant` 命名。

统一结论：

- 当前所有 built-in template 的 `variant` 暂记为 `default`
- narrative 原来的三个旧 `variant` 名称已迁移为 `sub-group`
- “设计排版扩散”这一层继续保留给后续实现与 notes 线路，不在本轮提前发明命名体系

## 对后续实现的要求
- metadata / catalog / selector 后续只能消费本记录中的审校结论，不得继续直接沿用旧 `group + variant` 假设
- 若后续要为 `evidence / comparison / process` 增加新的 `sub-group`，应基于模板页的稳定结构差异另行决策
- `#68` 应把本记录中的 `group / sub-group / variant` 结论视为 notes 聚合的上游输入

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
