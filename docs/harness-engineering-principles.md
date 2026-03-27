# Generation Instructions Principles

## 1. 先隔离实验场，再扩大影响面

所以我们先让 instructions 成为可维护的控制面，而不是把所有策略都硬编码在 Python 里。

## 2. 工具契约比实现细节更重要

一个能力能否被 agent 安全调用，取决于：
- 名称是否清晰
- 输入输出是否稳定
- timeout 和错误是否可诊断

而不是它内部是不是“聪明”。

## 3. 自由必须绑定护栏

agentic loop 不是“随便跑”，而是：
- 可以选择下一步
- 但仍要映射回稳定 stage
- 仍要保留超时、取消、恢复、事件流

## 4. Policy 要尽量离代码远一点

如果只是想改“第几页更适合 agenda”，不应该要求开发者改 Python。

这类策略应优先落到：
- `backend/app/services/generation/instructions_assets/config.json`
- `backend/app/services/generation/instructions_assets/agents/*.md`

## 5. 团队可维护性是最终验收标准

真正的完成，不是“代码能跑”。

而是：
- 非传统开发者看得懂怎么改
- AI agent 改得动
- reviewer 看得清风险
- 出问题时能快速回滚
