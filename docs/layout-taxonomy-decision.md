# Layout Taxonomy 决策记录

## 摘要
本记录用于固定 Zhiyan 模板体系中的三层 taxonomy 语义：`group / sub-group / variant`。
它是后续 `#62` 人工审校 template 归属、以及 metadata / catalog / selector 实现改造的前置依据。

本记录只回答分类语义问题，不直接修改运行时代码，也不替代具体实现 issue。

## 背景
当前系统已经围绕 `group + variant` 建立了一条可运行链路：

- `shared/layout-metadata.json` 维护 `roleDescriptions`、`variantPilotRoles`、`variantsByRole`
- `frontend/src/lib/layout-role.ts` 暴露页面角色语义
- `frontend/src/lib/layout-variant.ts` 暴露变体语义
- `frontend/src/lib/template-registry.ts` 与 `backend/app/models/layout_registry.py` 都直接消费 `group + variant`
- `frontend/src/app/dev/layout-catalog/LayoutCatalogClient.tsx` 在页面上展示 `Role Contract` 和 `Narrative Variant Pilot`

这套结构已经足够支持 narrative 试点，但在实践中暴露出一个核心混淆：
当前 `variant` 同时承担了两类不同问题。

1. 单个 `group` 内的信息结构细分
2. 在某个结构已经确定后的设计排版扩散

以 narrative 试点为例，当前的 `icon-points / visual-explainer / capability-grid` 更像是在回答“正文页用什么结构来讲”，而不是“同一结构下采用哪种设计变体”。

如果不先拆开这两类职责，后续无论是人工审校、notes 聚合，还是 selector 决策，都会继续建立在一个语义混杂的 taxonomy 上。

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

- 在同样的页面功能定位下，这页是用什么结构来承载信息的
- 同一个 `group` 内，不同模板页之间的结构差异应该如何被命名和复用

它不回答的问题是：

- 具体的视觉风格、色调或版式气质
- 同一结构下的设计扩散方向

默认规则：

- `sub-group` 是单选
- `sub-group` 需要人工审核收口
- 如果某个 `group` 暂时不需要再细分，则 `sub-group` 可暂记为 `default`

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
- `variant` 的细化范围晚于 `sub-group`

## 三层分别回答什么

| 层级 | 核心问题 | 示例句式 |
|---|---|---|
| `group` | 这页是拿来干什么的？ | “这是一页论据页 / 对比页 / 封面页” |
| `sub-group` | 这页用什么结构完成这个功能？ | “这是一页 narrative 下的图文说明结构” |
| `variant` | 在该功能与结构已确定后，这页具体长成哪种设计排版？ | “这是一页图文说明结构下的某种设计变体” |

## 每层不负责什么

| 层级 | 不负责回答的问题 |
|---|---|
| `group` | 不负责区分同组内的结构差异，不负责设计风格 |
| `sub-group` | 不负责设计扩散，不负责品牌气质或版式情绪 |
| `variant` | 不负责定义页面职责，不负责定义结构类型 |

## 旧语义到新语义的最小映射
本轮只覆盖已经明确存在混淆、且已在 narrative 试点中落地的旧语义。
不扩展到 evidence / comparison / process 的候选清单。

| 当前写法 | 旧层级理解 | 新层级理解 | 说明 |
|---|---|---|---|
| `narrative -> icon-points` | `variant` | `sub-group` 候选 | 回答的是“用图标分点讲正文”，属于结构差异 |
| `narrative -> visual-explainer` | `variant` | `sub-group` 候选 | 回答的是“用主视觉 + 说明讲正文”，属于结构差异 |
| `narrative -> capability-grid` | `variant` | `sub-group` 候选 | 回答的是“用能力矩阵讲正文”，属于结构差异 |

这里的“候选”含义是：
它们已经足以被确认为 `sub-group` 语义，但本记录不直接替后续实现决定最终字段形态，也不替 `#62` 完成逐页归属。

## 为什么 narrative 试点中的旧 `variant` 应迁移为 `sub-group`
判断原则如下：

1. 如果一个名字主要在回答“信息怎么排布成一种稳定结构”，它属于 `sub-group`
2. 如果一个名字主要在回答“同一结构下长成什么设计风格”，它属于 `variant`

按照这个标准，`icon-points / visual-explainer / capability-grid` 都明显更接近结构层：

- 它们改变的是正文信息如何组织
- 它们能直接决定应匹配哪类模板页
- 它们不只是视觉上的轻微差别

因此，这三个 narrative 试点名词不应再被描述为“纯设计变体”。

## 本记录不做什么
以下内容明确延期：

- 不逐页决定每个 built-in template 的最终 `group / sub-group / variant` 归属
  - 这件事留给 `#62`
- 不定义 notes 聚合格式和最终文案结构
  - 这件事留给 `#68`
- 不修改 `shared/layout-metadata.json` 的运行时结构
- 不修改前后端 registry 的类型与字段
- 不修改 selector 逻辑
- 不为非 narrative 组预先发明新的 `sub-group` 名单

## 对后续 issue 的要求

### 对 `#62`
`#62` 应以本记录为唯一口径，逐页审校所有 built-in template 的三层归属。
它可以为非 narrative 组提出新的 `sub-group` 候选，但这些候选应基于模板页实际结构，而不是在本记录里预先发明。

### 对 `#68`
`#68` 应把 `group`、`sub-group`、`variant` 视为 notes 的上游语义输入，而不是继续只围绕 layout 级 description 展开。

### 对后续实现 issue
后续 metadata / catalog / selector 改造只能消费本记录与 `#62` 的结论，不能绕过这两层直接扩展旧 `group + variant` 语义。

## 当前默认假设

- `group` 继续作为页面功能定位层
- `sub-group` 默认为单选结构层
- `variant` 当前阶段默认为多维软约束
- narrative 是当前唯一已明确存在结构层混淆的试点组
- 其它组是否需要 `sub-group`，留到 `#62` 再基于实际模板页判断

## 状态
本记录是当前阶段的决策依据。
若后续在 `#62` 审校中发现需要调整个别命名或边界，应通过新的决策记录或 issue 更新，而不是在实现 PR 中静默改写。
