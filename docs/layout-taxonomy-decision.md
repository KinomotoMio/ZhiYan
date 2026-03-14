# Layout Taxonomy 决策记录

## 摘要
本记录固定 Zhiyan 模板体系中的三层 taxonomy 语义：`group / sub-group / variant`。
它是后续 built-in template 审校、shared metadata、catalog、selector 与兼容层实现改造的统一口径。

本记录只回答 taxonomy 总框架与变量关系，不直接承担具体代码实现，也不替代 `#102` 对 `variant` 表达能力的后续专项重审。

## 背景
当前系统已经正式使用 `group / sub-group / variant` 三层 taxonomy：

- `shared/layout-metadata.json` 维护 canonical 的 `groupOrder`、`subGroupsByGroup`、`variantAxes` 与 template 级归属
- `frontend/src/lib/layout-taxonomy.ts` 与 `backend/app/services/pipeline/layout_taxonomy.py` 共同暴露正式 taxonomy 读取接口
- `frontend/src/lib/template-registry.ts` 与 `backend/app/models/layout_registry.py` 已直接消费三层 taxonomy
- `backend/app/services/pipeline/graph.py` 的 selector 已根据 `group / sub_group / layout_id` 进行布局选择

第一轮迁移已经证明三层 taxonomy 比旧的 `group + variant` 更稳定，但 built-in template 的实际使用也暴露出新的问题：

1. 仅把 `narrative` 视为有正式 `sub-group` 的组仍然过于保守
2. 部分 `variant.composition` 的历史语义仍然混入了结构层差异
3. taxonomy 的主问题已经不再是 `group` 数量不足，而是多个 `group` 的结构层没有正式收口

## 决策

### 1. `group` 的定义
`group` 定义页面在整份 PPT 里的功能定位。

它回答的问题是：

- 这页在整份 deck 里负责干什么
- 它属于封面、目录、章节过渡、正文叙述、论据、对比、流程、强调还是结尾

它不回答的问题是：

- 这页采用哪种信息结构
- 这页在同一结构下采用哪种设计风格

### 2. `sub-group` 的定义
`sub-group` 定义单个 `group` 内的信息结构细分。

它回答的问题是：

- 在同样的页面功能定位下，这页主要靠什么结构承载信息
- 同一个 `group` 内，不同模板页之间的稳定结构差异应该如何被命名和复用

它不回答的问题是：

- 具体的视觉风格、色调或版式气质
- 同一结构下的设计扩散方向

默认规则：

- `sub-group` 是单选
- 只要差异改变了信息承载结构或阅读路径，就应优先进入 `sub-group`
- `sub-group` 需要人工审核收口
- 如果某个 `group` 暂时没有稳定的结构层分化，则 `sub-group` 可记为 `default`

### 3. `variant` 的定义
`variant` 定义在 `group + sub-group` 已经确定之后，对设计排版的扩散。

它回答的问题是：

- 同样的功能定位、同样的信息结构下，这一页具体长成哪一种设计变体
- 某些设计偏好是否会影响排序或候选优先级

它不回答的问题是：

- 页面的功能定位是什么
- 页面采用什么信息结构

当前阶段的默认规则：

- `variant` 优先按多维软约束理解
- `variant` 不立即被视为硬路由字段
- 若某个 `composition` 名称主要回答的是结构差异，应优先把该差异回收到 `sub-group`

### 4. `usage` 与 `notes` 的位置
`usage` 不是新的硬 taxonomy 层，而是位于 `variant` 之下的适配偏好层。

它回答的问题是：

- 在同样的功能定位、信息结构和设计变体下，这个方向更偏哪些使用场景
- 哪些 usage 会影响候选排序，但不应反向改写 `group / sub-group / variant`

默认规则：

- 一个 `variant` 可以偏向多个 `usage`
- `usage` 影响排序和适配偏好，不新增新的分类层级

`notes` 也不是新的 taxonomy 层，而是综合上游信息后形成的解释层。

它固定聚合：

- `group`
- `sub-group`
- `variant`
- `usage`

因此，本轮统一按以下主干理解变量关系：

`group -> sub-group -> variant -> usage`

`notes` 作为派生说明层，负责把这条主干转写成 agent 与人都能消费的解释信号。

## 第二轮校准结论

### `group`
本轮不新增 `group`。
当前 `cover / agenda / section-divider / narrative / evidence / comparison / process / highlight / closing`
对现有 16 个 built-in template 与当前已知的常见页面 archetype 足够。

本轮不直接宣称它们已经覆盖“绝大多数 PPT 页面场景”。
本轮的主问题不是 `group` 覆盖不足，而是多个 `group` 的正式结构层仍被压在 `default` 或 `variant.composition` 中。

### `sub-group`
本轮将“只有 `narrative` 有正式 `sub-group`”升级为多组正式结构层：

- `narrative`
  - `icon-points`
  - `visual-explainer`
  - `capability-grid`
- `evidence`
  - `stat-summary`
  - `visual-evidence`
  - `chart-analysis`
  - `table-matrix`
- `comparison`
  - `side-by-side`
  - `response-mapping`
- `process`
  - `step-flow`
  - `timeline-milestone`

其余 `group` 继续保留 `default`。

### `variant`
本轮明确收紧 `variant` 边界：

- `variant` 只保留同一 `group + sub-group` 下的设计扩散
- `tone / style / density` 继续稳定承担设计层职责
- `composition` 仍保留为设计骨架字段，但其历史上混入的结构语义应逐步弱化
- 若一个差异已经决定应匹配哪类模板页，它属于 `sub-group`，不属于 `variant`
- 当前结论只负责确认 `variant` 仍属于设计层，不在本轮给出其表达能力是否最终足够的结论

## 三层分别回答什么

| 层级 | 核心问题 | 示例句式 |
|---|---|---|
| `group` | 这页是拿来干什么的？ | “这是一页论据页 / 对比页 / 封面页” |
| `sub-group` | 这页用什么结构完成这个功能？ | “这是一页 evidence 下的图表解读结构” |
| `variant` | 在该功能与结构已确定后，这页具体长成哪种设计排版？ | “这是一页图表解读结构下的某种正式设计变体” |
| `usage` | 在该设计变体下，更偏哪些使用场景？ | “这是一页更偏 investor-pitch / business-report 的图表解读变体” |
| `notes` | 如何把前述层级解释给 agent 与人？ | “为什么该选它、何时该避开它、它更偏哪些 usage” |

## 每层不负责什么

| 层级 | 不负责回答的问题 |
|---|---|
| `group` | 不负责区分同组内的结构差异，不负责设计风格 |
| `sub-group` | 不负责设计扩散，不负责品牌气质或版式情绪 |
| `variant` | 不负责定义页面职责，不负责定义结构类型 |
| `usage` | 不负责定义 taxonomy 主干，不负责替代 `variant` 做设计分流 |
| `notes` | 不负责新增分类层，不负责替代 selector 或 metadata schema |

## 典型映射

| 页面 | `group` | `sub-group` | 说明 |
|---|---|---|---|
| 图标分点正文 | `narrative` | `icon-points` | 结构差异来自正文如何被分点组织。 |
| 指标摘要页 | `evidence` | `stat-summary` | 核心差异来自“少量数字支撑结论”的承载结构。 |
| 图表解读页 | `evidence` | `chart-analysis` | 核心差异来自“图表 + takeaway”并置的分析结构。 |
| 标准对照页 | `comparison` | `side-by-side` | 核心差异来自左右并列的横向对照。 |
| 问题回应页 | `comparison` | `response-mapping` | 核心差异来自挑战到回应的双栏映射。 |
| 步骤页 | `process` | `step-flow` | 核心差异来自顺序步骤而非时间节点。 |
| 时间线页 | `process` | `timeline-milestone` | 核心差异来自按时间推进的信息组织。 |

## 本记录不做什么
以下内容明确延期：

- 不直接修改 selector、registry 或 catalog 代码
- 不定义具体 prompt、fallback 或兼容层实现细节
- 不为当前 built-in 之外的未来模板预先发明新的 `group`
- 不在本记录中扩展新的 `variant` 字段或 wire shape

## 对后续 issue 的要求

### 对 built-in template 审校
built-in template 的正式归属必须消费本记录的边界：

- `group` 本轮保持稳定，不额外新增
- `evidence / comparison / process` 的结构层要正式回写为 `sub-group`
- 不能继续把明显的结构差异只记录在 `variant.composition`

### 对 selector / metadata / catalog 实现
后续实现只能消费本记录与 template 审校结论：

- selector 应先定 `group`，再定 `sub-group`，最后落到 `layout_id`
- shared metadata 应把新增的 `sub-group` 作为 canonical 结果回写
- catalog 或兼容视图若继续展示旧的 `variant` 词汇，必须明确它只是过渡接口

## 当前默认假设

- `group` 继续作为页面功能定位层
- `sub-group` 继续作为单选结构层
- `variant` 继续作为对象型设计层
- 当前 built-in 已足以证明 `evidence / comparison / process` 需要正式 `sub-group`
- 若后续发现更多组也需正式 `sub-group`，仍按“结构承载优先”的规则推进，而不是直接扩 `group`

## 状态
本记录是 `#98` 之后的最新 taxonomy 决策基线。
`variant` 的对象结构和值域仍由 [layout-variant-decision.md](./layout-variant-decision.md) 承接，
built-in template 的正式归属与 notes 基线由 [layout-template-taxonomy-audit.md](./layout-template-taxonomy-audit.md) 承接。
`variant` 的多设计风格扩展能力，以及四轴是否足以长期承载这种扩展，继续由 `#102` 承接。
