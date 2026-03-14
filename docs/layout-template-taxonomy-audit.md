# Built-in Template Taxonomy 审校定版

## 摘要
本记录用于承接 `#62`，对当前 16 个 built-in template 做一次完整的人工审校，
输出 `group / sub-group / variant` 三层归属结论与当前 built-in template 的基线示例。

本记录消费 `#67` 中已经固定的 taxonomy 语义，不重新定义三层概念。
它的目标是给后续 metadata、catalog、selector 与 notes 线路提供统一输入，
而不是直接修改运行时代码。

## 审校口径

### 上游语义
本记录以 [layout-taxonomy-decision.md](./layout-taxonomy-decision.md) 为唯一 taxonomy 口径：

- `group`：页面功能定位
- `sub-group`：单个 group 内的信息结构细分，单选
- `variant`：在 `group + sub-group` 已确定之后的设计排版扩散
- `usage`：位于 `variant` 之下的适配偏好层，不是新的硬 taxonomy 层
- `notes`：综合上游语义形成的解释层，不是新的分类层

### 当前阶段的默认规则
- 如果模板的主要差异体现在信息如何被组织，则优先记为 `sub-group`
- `variant` 的对象结构和值域以 [layout-variant-decision.md](./layout-variant-decision.md) 为准
- 本记录不再把 `variant` 一律暂记为 `default`，而是回写当前 16 个 built-in template 的当前基线归属
- 本轮明确回写 `evidence / comparison / process` 的正式 `sub-group`
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
| `metrics-slide` | `evidence / default` | `evidence` | `stat-summary` | `{ composition: stat-grid, tone: formal, style: data-first, density: medium }` | `新增或调整 sub-group + 定义 variant` | 指标卡片页的核心差异来自“少量 KPI 支撑结论”的承载结构，应正式升级为 evidence 的指标概览结构。 |
| `metrics-with-image` | `evidence / default` | `evidence` | `visual-evidence` | `{ composition: media-split, tone: assertive, style: data-first, density: medium }` | `新增或调整 sub-group + 定义 variant` | 数据与配图并置已经构成稳定结构，不应继续只留在 design 层。 |
| `chart-with-bullets` | `evidence / default` | `evidence` | `chart-analysis` | `{ composition: analysis-split, tone: formal, style: data-first, density: high }` | `新增或调整 sub-group + 定义 variant` | 图表主证据加右侧解读要点已经决定了阅读路径，属于正式结构层。 |
| `table-info` | `evidence / default` | `evidence` | `table-matrix` | `{ composition: table-dominant, tone: formal, style: data-first, density: high }` | `新增或调整 sub-group + 定义 variant` | 表格或矩阵主导的证据页属于稳定结构差异，应正式从 default 中拆出。 |
| `two-column-compare` | `comparison / default` | `comparison` | `side-by-side` | `{ composition: dual-columns, tone: formal, style: card-based, density: medium }` | `新增或调整 sub-group + 定义 variant` | 标准双栏对比页的核心差异在于稳定的左右并列对照结构。 |
| `challenge-outcome` | `comparison / default` | `comparison` | `response-mapping` | `{ composition: dual-columns, tone: assertive, style: minimal, density: medium }` | `新增或调整 sub-group + 定义 variant` | 问题到结果或方案的映射关系属于比较组内另一类稳定结构，而不是普通双栏对照。 |
| `numbered-bullets` | `process / default` | `process` | `step-flow` | `{ composition: step-list, tone: neutral, style: minimal, density: medium }` | `新增或调整 sub-group + 定义 variant` | 步骤、方法和执行路径的核心差异在于顺序步骤结构，应正式作为流程组的子类。 |
| `timeline` | `process / default` | `process` | `timeline-milestone` | `{ composition: timeline-band, tone: formal, style: minimal, density: medium }` | `新增或调整 sub-group + 定义 variant` | 时间轴与里程碑结构已经独立于步骤流，应正式从 process default 中拆出。 |
| `quote-slide` | `highlight / default` | `highlight` | `default` | `{ composition: quote-focus, tone: assertive, style: statement, density: low }` | `补充正式 variant` | 强调页的设计差异稳定落在单句聚焦和 statement 风格上。 |
| `thank-you` | `closing / default` | `closing` | `default` | `{ composition: closing-hero, tone: celebratory, style: minimal, density: low }` | `补充正式 variant` | 结尾页的正式 variant 应表达收束感与庆祝/致谢型气质，而不是继续停留在默认占位。 |

## 分组结论摘要

### `narrative`
`narrative` 继续保持第一轮已经确认的三个正式 `sub-group`。

最终结论：

- `icon-points` 作为 `bullet-with-icons` 的 `sub-group`
- `visual-explainer` 作为 `image-and-description` 的 `sub-group`
- `capability-grid` 作为 `bullet-icons-only` 的 `sub-group`
- narrative 组下三个模板都已经补足正式 variant 对象

### `evidence`
本轮正式确认 `evidence` 组内存在稳定结构层：

- `stat-summary` -> `metrics-slide`
- `visual-evidence` -> `metrics-with-image`
- `chart-analysis` -> `chart-with-bullets`
- `table-matrix` -> `table-info`

这意味着证据页的主问题不是再补一个更大的 `variant` 名词，而是承认“少量 KPI / 数据配图 / 图表解读 / 表格矩阵”已经是不同的结构承载方式。

### `comparison`
本轮正式确认 `comparison` 组内至少包含两种稳定结构：

- `side-by-side` -> `two-column-compare`
- `response-mapping` -> `challenge-outcome`

结论不是新增新的 `group`，而是在 comparison 组内承认“并列对照”和“问题到回应映射”是两类不同结构。

### `process`
本轮正式确认 `process` 组内至少包含两种稳定结构：

- `step-flow` -> `numbered-bullets`
- `timeline-milestone` -> `timeline`

这意味着流程页中的“步骤方法”和“时间里程碑”不再继续共用 `default`。

### 仍保留 `default` 的 group
本轮继续保持以下 group 为默认结构：

- `cover`
- `agenda`
- `section-divider`
- `highlight`
- `closing`

这些组当前 built-in 数量和结构差异都不足以支撑新的正式子类。

### 关于 `variant`
本轮已经为所有 built-in template 输出当前 `variant` 基线归属。

统一结论：

- 当前所有 built-in template 的 `variant` 都应视为四字段对象，而不再是单值 `default`
- `narrative / evidence / comparison / process` 都已经拥有正式的结构层 `sub-group`
- 当前表中的 `variant` 结果只代表 built-in template 的现阶段基线，不代表同一 `group + sub-group` 只能存在这一种设计变体
- 具体字段和值域以 [layout-variant-decision.md](./layout-variant-decision.md) 为准

## 对后续实现的要求
- metadata / catalog / selector 后续只能消费本记录中的审校结论，不得继续直接沿用旧 `group + variant` 假设
- 后续若继续为其他 group 增加新的 `sub-group`，应仍然基于模板页的稳定结构差异推进
- `#68` 应把本记录中的 `group / sub-group / variant` 结论视为 notes 聚合的上游输入
- 后续实现 issue 不得把 `variant` 重新降回单值字符串语义

## Template Notes 基线
本节承接 `#68`，把当前 16 个 built-in template 的首版 notes 基线固定为统一的 6 槽位合同。
所有 notes 槽位定义均以 [layout-notes-decision.md](./layout-notes-decision.md) 为准。

### `intro-slide`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于建立演示开场身份与主题，不负责展开正文内容。 |
| `structure_signal` | `cover / default` 适合单一主题入口，强调标题、身份与第一印象。 |
| `design_signal` | `hero-center + formal + editorial + low` 让注意力集中在标题和主题氛围上。 |
| `use_when` | 当你需要一个正式、清晰、有开场感的封面页时优先使用。 |
| `avoid_when` | 不适合承载多个并列信息点、目录导航或正文解释。 |
| `usage_bias` | 强偏 `academic-report`、`business-report`、`investor-pitch`，对其他 usage 为中等兼容。 |

### `outline-slide`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于交代整份演示的章节骨架，不负责深入解释单个章节内容。 |
| `structure_signal` | `agenda / default` 适合把 4-6 个章节块组织成统一目录视图。 |
| `design_signal` | `card-grid + formal + card-based + medium` 让目录既可扫读又保持章节边界。 |
| `use_when` | 当你需要在正文前建立叙事顺序和章节预期时使用。 |
| `avoid_when` | 不适合展示单一结论、图表分析或具体案例内容。 |
| `usage_bias` | 强偏 `academic-report`、`business-report`、`project-status`，对 `training-workshop` 也较友好。 |

### `section-header`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于大章节之间的切换与提示，不负责承载大量新信息。 |
| `structure_signal` | `section-divider / default` 只保留章节标题和简短引导，强调结构切换。 |
| `design_signal` | `section-break + assertive + minimal + low` 提供清晰的阶段切换感而不分散注意力。 |
| `use_when` | 当你需要在长 deck 中重置观众注意力、标记新章节时使用。 |
| `avoid_when` | 不适合放目录、证据、步骤或任何需要完整阅读的信息块。 |
| `usage_bias` | 强偏 `conference-keynote`、`business-report`、`product-demo`，其他 usage 为弱偏向。 |

### `bullet-with-icons`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于正文中分点说明 3-4 个能力、优势或结论，不负责复杂流程或大段图文。 |
| `structure_signal` | `narrative / icon-points` 适合将并列要点组织成易扫读的图标分点结构。 |
| `design_signal` | `icon-columns + assertive + icon-led + medium` 强化每个要点的视觉锚点与结论感。 |
| `use_when` | 当内容天然是 3-4 个并列卖点、能力点或结论点时使用。 |
| `avoid_when` | 不适合讲时间线、表格数据或需要主视觉主导的故事页。 |
| `usage_bias` | 强偏 `sales-pitch`、`product-demo`、`investor-pitch`，对 `business-report` 也很适用。 |

### `image-and-description`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于正文中的案例、场景或产品特性说明，不负责高密度信息压缩。 |
| `structure_signal` | `narrative / visual-explainer` 适合由一个主视觉承载情境，再配说明文字。 |
| `design_signal` | `media-split + approachable + editorial + medium` 让页面更适合讲解、展示和说明。 |
| `use_when` | 当一张图能承担主要情绪或理解入口时优先使用。 |
| `avoid_when` | 不适合没有视觉主体的纯要点页，也不适合高密度矩阵信息。 |
| `usage_bias` | 强偏 `product-demo`、`sales-pitch`、`conference-keynote`，对 `business-report` 为中偏向。 |

### `bullet-icons-only`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于正文中的能力矩阵、模块总览或功能地图，不负责线性叙事。 |
| `structure_signal` | `narrative / capability-grid` 适合把多个并列能力点组织成高密度网格。 |
| `design_signal` | `capability-grid + assertive + icon-led + high` 强调覆盖面、并列关系和快速扫读。 |
| `use_when` | 当你需要一页覆盖 4-8 个并列能力项时使用。 |
| `avoid_when` | 不适合需要详细解释每一点，或需要时间顺序和主次层级的内容。 |
| `usage_bias` | 强偏 `product-demo`、`training-workshop`、`business-report`，对 `conference-keynote` 为中偏向。 |

### `metrics-slide`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于展示少量核心 KPI 或指标摘要，不负责完整趋势解读。 |
| `structure_signal` | `evidence / stat-summary` 在证据页中以指标卡片作为主载体，突出关键数字。 |
| `design_signal` | `stat-grid + formal + data-first + medium` 适合用少量数据建立可信度和概览感。 |
| `use_when` | 当结论可以被 2-4 个核心数字直接支撑时使用。 |
| `avoid_when` | 不适合需要详细趋势分析、表格参数或图片说明并重的内容。 |
| `usage_bias` | 强偏 `business-report`、`investor-pitch`、`project-status`，对 `academic-report` 也适用。 |

### `metrics-with-image`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于同时展示关键指标和配图场景，不负责高密度表格或复杂图表分析。 |
| `structure_signal` | `evidence / visual-evidence` 以关键指标配合场景图像承载证据，同时补足语境和感知。 |
| `design_signal` | `media-split + assertive + data-first + medium` 让数据结论和场景视觉同时成立。 |
| `use_when` | 当你既需要展示 KPI，又希望让产品/场景画面增强说服力时使用。 |
| `avoid_when` | 不适合没有图像语境的纯数字概览，也不适合大量数据对比。 |
| `usage_bias` | 强偏 `sales-pitch`、`product-demo`、`investor-pitch`，对 `business-report` 为中偏向。 |

### `chart-with-bullets`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于图表趋势与文字解读并置，不负责单页概览或大表格参数罗列。 |
| `structure_signal` | `evidence / chart-analysis` 以图表作为主证据，并用右侧要点完成趋势解读和结论提炼。 |
| `design_signal` | `analysis-split + formal + data-first + high` 适合让图表阅读和观点提炼同时发生。 |
| `use_when` | 当一张图表需要 2-3 个明确 takeaways 时使用。 |
| `avoid_when` | 不适合只有一句结论的轻量证据页，也不适合纯表格信息。 |
| `usage_bias` | 强偏 `academic-report`、`business-report`、`project-status`，对 `investor-pitch` 为中偏向。 |

### `table-info`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于结构化参数、矩阵和行列对照，不负责情绪化展示或单点强调。 |
| `structure_signal` | `evidence / table-matrix` 以表格或矩阵作为主载体，适合行列清晰的结构化信息。 |
| `design_signal` | `table-dominant + formal + data-first + high` 强调信息完整度和严谨感。 |
| `use_when` | 当核心信息天然需要按行列展开比较时使用。 |
| `avoid_when` | 不适合需要图片主导、流程叙事或少量关键数字概览。 |
| `usage_bias` | 强偏 `academic-report`、`business-report`、`project-status`，对 `sales-pitch` 为弱到中偏向。 |

### `two-column-compare`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于并列比较两组对象或两种方案，不负责讲因果过程。 |
| `structure_signal` | `comparison / side-by-side` 适合稳定的左右对照结构，突出两侧差异。 |
| `design_signal` | `dual-columns + formal + card-based + medium` 让左右比较既清楚又有边界感。 |
| `use_when` | 当你需要让观众快速比较 A/B、现状/目标、手工/自动化时使用。 |
| `avoid_when` | 不适合讲问题到方案的映射链，也不适合多于两组对象的比较。 |
| `usage_bias` | 强偏 `business-report`、`sales-pitch`、`product-demo`，对 `investor-pitch` 为中偏向。 |

### `challenge-outcome`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于呈现问题到结果、挑战到方案的映射，不负责纯并列优劣对照。 |
| `structure_signal` | `comparison / response-mapping` 更偏问题到回应的映射关系，每组内容带有明显的前后因果。 |
| `design_signal` | `dual-columns + assertive + minimal + medium` 让问题与回应之间形成更强的推进感。 |
| `use_when` | 当内容是“痛点/挑战 -> 结果/方案”这类对应关系时优先使用。 |
| `avoid_when` | 不适合无因果关系的普通双栏比较，也不适合步骤型内容。 |
| `usage_bias` | 强偏 `business-report`、`sales-pitch`、`project-status`，对 `investor-pitch`、`product-demo` 为中偏向。 |

### `numbered-bullets`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于说明步骤、方法或执行路径，不负责表达真实时间里程碑。 |
| `structure_signal` | `process / step-flow` 以步骤清单承载方法或执行路径，强调顺序而非时间坐标。 |
| `design_signal` | `step-list + neutral + minimal + medium` 让执行步骤保持可读性和方法感。 |
| `use_when` | 当你要讲做法、流程、操作步骤或 rollout path 时使用。 |
| `avoid_when` | 不适合讲按日期推进的时间线，也不适合高密度并列能力页。 |
| `usage_bias` | 强偏 `training-workshop`、`project-status`、`business-report`，对 `product-demo` 为中偏向。 |

### `timeline`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于表达时间顺序、里程碑或发展节奏，不负责方法步骤说明。 |
| `structure_signal` | `process / timeline-milestone` 以时间轴承载阶段推进，将事件绑定到时间节点上。 |
| `design_signal` | `timeline-band + formal + minimal + medium` 强调时间推进与阶段变化，而不是操作方法。 |
| `use_when` | 当信息核心是时间、阶段、里程碑或发展历程时使用。 |
| `avoid_when` | 不适合没有时间语义的步骤说明，也不适合单点结论页。 |
| `usage_bias` | 强偏 `project-status`、`academic-report`、`conference-keynote`，对 `business-report` 为中偏向。 |

### `quote-slide`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于强调一句核心结论、引用或原则，不负责组织复杂信息。 |
| `structure_signal` | `highlight / default` 适合把注意力聚焦到一句话，而不是多元素阅读。 |
| `design_signal` | `quote-focus + assertive + statement + low` 让页面情绪和焦点都收束到单句表达上。 |
| `use_when` | 当你需要暂停叙事、突出原则、引用或关键结论时使用。 |
| `avoid_when` | 不适合承载列表、图表、双栏比较或复杂说明。 |
| `usage_bias` | 强偏 `conference-keynote`、`business-report`、`academic-report`，对 `investor-pitch` 为中偏向。 |

### `thank-you`

| 槽位 | 内容 |
|---|---|
| `purpose` | 用于收尾、致谢和结束，不负责引入新的分析或论证。 |
| `structure_signal` | `closing / default` 保持简单收束，让信息在结束感中自然落下。 |
| `design_signal` | `closing-hero + celebratory + minimal + low` 强调结束感、礼貌性和留白。 |
| `use_when` | 当 deck 需要明确结束并留出提问或联系方式时使用。 |
| `avoid_when` | 不适合继续承载新观点、数据、流程或目录信息。 |
| `usage_bias` | 对全部 usage 普遍兼容，其中 `conference-keynote`、`sales-pitch`、`investor-pitch` 的结束需求更强。 |

## 本记录不做什么
- 不修改 `shared/layout-metadata.json`
- 不修改 `frontend/src/lib/template-registry.ts`
- 不修改 `backend/app/models/layout_registry.py`
- 不修改 `/dev/layout-catalog`
- 不修改 selector prompt 或选择逻辑
- 不定义 notes runtime 字段落地或展示方式

## 状态
本记录构成 `#62` 的人工审校定版结论。
后续若需要进一步细化其他 group 的 `sub-group` 或扩展新的 built-in template，
应继续通过新的 issue 或决策记录推进，而不是在实现 PR 中静默改写 taxonomy。
