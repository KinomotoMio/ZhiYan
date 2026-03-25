# Harness Engineering Workflow

## 为什么要做这件事

我们把生成系统从“固定 pipeline”升级为“tool registry + loop + harness config”的目标，不是为了追求抽象层数，而是为了把产品行为的调整成本从“改代码”下降到“调控制面”。

一句话：

> 模型负责决策，工具负责执行，harness 负责约束、观测和让团队可维护。

## 三类变更

### 1. 指令变更

适用场景：
- 想改变大纲偏好、叙事语气、规划策略
- 想让 planner 更保守或更激进

改动位置：
- `harness/generation/agents/*.md`
- `harness/generation/config.json`

Review 清单：
- 改的是 policy，不是机制
- 是否说明了想影响哪一类行为
- 是否会影响稳定性或造成工具反复调用

验证 recipe：
1. 运行 `cd /Users/qizhi_dong/Projects/Zhiyan-harness/backend && uv run pytest tests/test_harness_config.py -q`
2. 跑一次 `/api/v2/harness/slidev-mvp`，确认输出仍可渲染
3. 对比变更前后的大纲差异，确认是预期变化

回滚方式：
- 直接回退对应的 `.md` / `.json` 变更

### 2. Skill 变更

适用场景：
- 想新增一个外部能力，如 Slidev Markdown 渲染
- 想替换某个辅助脚本，而不动主循环

改动位置：
- `skills/<skill-name>/SKILL.md`
- `skills/<skill-name>/scripts/*.py`

Review 清单：
- skill 输入/输出是否稳定
- 是否能在不改 loop 代码的前提下接入
- 脚本失败时是否可诊断

验证 recipe：
1. 调 `GET /api/v1/skills` 确认 skill 被发现
2. 跑 skill 对应的单元测试
3. 若是 dev-only skill，确认不会接管生产 API

回滚方式：
- 删除或回退 skill 目录变更

### 3. 工具变更

适用场景：
- 想新增 generation tool
- 想修改现有 parse / outline / layout / slides / assets / verify 的执行边界

改动位置：
- `backend/app/services/generation/tool_registry.py`
- `backend/app/services/generation/runner.py`
- `backend/app/services/pipeline/graph.py`

Review 清单：
- 工具契约是否明确（名字、描述、timeout、执行函数）
- 是否保持 `StageStatus` / SSE 兼容
- 是否引入了不可观测的隐式状态

验证 recipe：
1. 运行
   ```bash
   cd /Users/qizhi_dong/Projects/Zhiyan-harness/backend && uv run pytest tests/test_generation_v2_runtime.py tests/test_generation_v2_stream_protocol.py tests/test_generation_loop_planner.py -q
   ```
2. 确认失败可归因到具体 tool / stage
3. 检查是否仍支持 cancel / resume / outline review

回滚方式：
- `git revert <commit>`

## 非传统开发者 + AI agent 演练

目标：在不改 Python orchestration 机制代码的前提下，完成一次行为调整。

建议演练题：
- 把 `harness/generation/config.json` 中的 `outline.agenda_page_index` 改成 `3`
- 重新运行一次大纲生成或 Slidev MVP
- 观察 agenda 是否更倾向于出现在第 3 页

如果做不到，优先排查：
1. prompt 是否真正从 harness 文件加载
2. 新配置是否被测试覆盖
3. 变更是否误落到机制层而非 policy 层

## 结对时固定复盘问题

每次改动后都回答这 3 个问题：

1. 这次把什么控制面从代码移到了 harness？
2. 模型因此多获得了什么决策权？
3. 我们增加了什么护栏，避免自由变成失控？
