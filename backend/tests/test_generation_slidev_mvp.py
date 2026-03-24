from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai.exceptions import IncompleteToolCall, ModelHTTPError, UnexpectedModelBehavior

from app.core.config import settings
from app.main import app
from app.services.generation.agentic.types import AgenticMessage, AgenticModelClient, AssistantMessage, ToolCall, ToolResult, UserMessage
from app.services.generation.slidev_mvp import (
    SlidevMvpArtifacts,
    SlidevMvpProviderError,
    SlidevMvpService,
    SlidevMvpValidationError,
)
from app.services.skill_runtime.executor import execute_skill
from app.services.skill_runtime.registry import SkillRegistry


@dataclass
class StubModel(AgenticModelClient):
    responses: list[AssistantMessage]
    seen_messages: list[list[AgenticMessage]] | None = None

    async def complete(self, messages, tools) -> AssistantMessage:
        if self.seen_messages is not None:
            self.seen_messages.append(list(messages))
        return self.responses.pop(0)


class FakeSessionStore:
    def __init__(
        self,
        *,
        session_exists: bool = True,
        source_metas: list[dict] | None = None,
        source_content: str = "",
    ) -> None:
        self.session_exists = session_exists
        self.source_metas = source_metas or []
        self.source_content = source_content
        self.ensure_workspace_calls: list[str] = []
        self.session_calls: list[tuple[str, str]] = []
        self.source_lookup_calls: list[tuple[str, list[str]]] = []
        self.source_content_calls: list[tuple[str, str, list[str]]] = []

    async def ensure_workspace(self, workspace_id: str) -> None:
        self.ensure_workspace_calls.append(workspace_id)

    async def get_session(self, workspace_id: str, session_id: str) -> dict:
        self.session_calls.append((workspace_id, session_id))
        if not self.session_exists:
            raise ValueError("session not found")
        return {"id": session_id}

    async def get_workspace_sources_by_ids(self, workspace_id: str, source_ids: list[str]) -> list[dict]:
        self.source_lookup_calls.append((workspace_id, list(source_ids)))
        return list(self.source_metas)

    async def get_combined_source_content(self, workspace_id: str, session_id: str, source_ids: list[str]) -> str:
        self.source_content_calls.append((workspace_id, session_id, list(source_ids)))
        return self.source_content


def _slidev_markdown() -> str:
    return """---
theme: default
title: AI Product Architecture Evolution
layout: cover
class: deck-cover
---

# AI Product Architecture Evolution

Harness drives Slidev through a layered control plane

---
class: deck-context
---

## Why This Matters

- Cost pressure
- UX pressure

---
class: deck-framework
---

## Harness Layers

```mermaid
graph TD
  A[loop] --> B[tools]
  B --> C[context]
```

Core takeaway: structure should stay in the harness, not in ad-hoc prompt glue.

---
layout: two-cols
class: deck-comparison
---

## MVP Path

::left::

- markdown artifact
- local preview
- fast feedback

::right::

- no UI coupling
- no job/SSE changes
- keeps renderer boundary clear

---
layout: end
class: deck-closing
---

## Next Step

1. Validate locally
2. Decide migration boundary

Ship the contract first, polish the deck second.
"""


def _simple_markdown() -> str:
    return """---
theme: default
title: Mini Deck
layout: cover
class: deck-cover
---

# Cover

Short subtitle

---
layout: end
class: deck-closing
---

## Closing

- done
"""


def _comparison_mismatch_markdown() -> str:
    return """---
theme: default
title: Contract Drift
---

# Contract Drift

---

## Supposed Comparison

- option A
- option B
- option C

---

## Next Step

- decide
"""


def _native_layout_markdown() -> str:
    return """---
theme: default
title: Native Mapping Deck
layout: cover
class: deck-cover
---

# Native Mapping Deck

Contract-first Slidev output

---
class: deck-context
---

## Why Native Patterns Matter

> Use built-in layouts when the semantic fit is stable.

---
layout: two-cols
class: deck-comparison
---

## High Fidelity

::left::

- explicit layout mapping
- stable compare structure

::right::

- less prompt ambiguity
- better preview consistency

---
layout: end
class: deck-closing
---

# Next Steps

Adopt the stable mappings first.
"""


def _blank_first_slide_markdown() -> str:
    return """---
theme: default
title: Blank Cover Bug
---

---
layout: cover
class: deck-cover
---

# Blank Cover Bug

This cover should not create an empty slide first.

---

## Closing

- done
"""


def _unfenced_frontmatter_markdown() -> str:
    return """---
theme: default
title: Unfenced Frontmatter
layout: cover
class: deck-cover
---

# Unfenced Frontmatter

Looks fine at first glance

---

layout: two-cols
class: deck-comparison

## Compare

- left
- right

---

layout: end
class: deck-closing

## Closing

- done
"""


def _double_separator_frontmatter_markdown() -> str:
    return """---
theme: seriph
title: Double Separator
---

# Double Separator

This deck should not render blank slides between pages.

---

---
layout: two-cols
class: deck-comparison
---

## Compare

- left
- right

---

---
layout: end
class: deck-closing
---

# Closing

Ship the normalized composition only once.
"""


def _quality_outline_items() -> list[dict[str, str | int]]:
    return [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "建立主题定位"},
        {"slide_number": 2, "title": "为什么现在要做", "slide_role": "context", "content_shape": "problem-bullets", "goal": "说明问题背景"},
        {"slide_number": 3, "title": "Harness 分层", "slide_role": "framework", "content_shape": "two-column-framework", "goal": "解释分层职责"},
        {"slide_number": 4, "title": "Slidev MVP 闭环", "slide_role": "detail", "content_shape": "diagram-callout", "goal": "说明实现闭环"},
        {"slide_number": 5, "title": "迁移边界", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "澄清保留与迁移"},
        {"slide_number": 6, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "总结行动方向"},
    ]


def _quality_outline_items_five() -> list[dict[str, str | int]]:
    return [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "建立主题定位"},
        {"slide_number": 2, "title": "为什么现在要做", "slide_role": "context", "content_shape": "problem-bullets", "goal": "说明问题背景"},
        {"slide_number": 3, "title": "Harness 分层", "slide_role": "framework", "content_shape": "two-column-framework", "goal": "解释分层职责"},
        {"slide_number": 4, "title": "Slidev MVP 闭环", "slide_role": "detail", "content_shape": "diagram-callout", "goal": "说明实现闭环"},
        {"slide_number": 5, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "总结行动方向"},
    ]


def _quality_outline_items_twelve() -> list[dict[str, str | int]]:
    return [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "建立主题定位"},
        {"slide_number": 2, "title": "工作版图为什么在变", "slide_role": "context", "content_shape": "problem-bullets", "goal": "说明宏观背景"},
        {"slide_number": 3, "title": "变化的三股力量", "slide_role": "framework", "content_shape": "framework-grid", "goal": "给出结构模型"},
        {"slide_number": 4, "title": "重复性任务先被重写", "slide_role": "detail", "content_shape": "detail-callout", "goal": "解释低复杂度岗位变化"},
        {"slide_number": 5, "title": "知识工作会被协同增强", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "对比增强与替代"},
        {"slide_number": 6, "title": "岗位重构而非简单消失", "slide_role": "detail", "content_shape": "diagram-callout", "goal": "描述岗位重构"},
        {"slide_number": 7, "title": "个人能力模型如何变化", "slide_role": "framework", "content_shape": "framework-grid", "goal": "解释新能力结构"},
        {"slide_number": 8, "title": "企业组织会如何调整", "slide_role": "comparison", "content_shape": "table-compare", "goal": "对比旧组织与新组织"},
        {"slide_number": 9, "title": "风险与不确定性", "slide_role": "context", "content_shape": "quote-callout", "goal": "提示风险"},
        {"slide_number": 10, "title": "个人应该怎么准备", "slide_role": "recommendation", "content_shape": "action-list", "goal": "给出行动建议"},
        {"slide_number": 11, "title": "团队应该怎么准备", "slide_role": "recommendation", "content_shape": "action-list", "goal": "给出团队建议"},
        {"slide_number": 12, "title": "结论与下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "完成收束"},
    ]


def _chunk_fragment(chunk_number: int) -> str:
    chunk_map = {
        1: """---
layout: cover
class: deck-cover
---

# 人工智能对未来工作影响

一次关于岗位重构、能力迁移与组织响应的结构化梳理

---
class: deck-context
---

## 工作版图为什么在变

> 自动化、协作智能与组织压力正在同时发生。

- 成本曲线改变
- 交付速度加快
- 能力要求重排

---
class: deck-framework
---

## 变化的三股力量

```mermaid
graph TD
  A[自动化] --> D[工作重构]
  B[协作智能] --> D
  C[组织效率压力] --> D
```

**Takeaway**: 未来工作的变化不是单点替代，而是多因素叠加。
""",
        2: """## 重复性任务先被重写

- 标准化流程先被 AI 接管
- 人类转向异常处理与判断
- 价值从执行迁移到定义问题

---
layout: two-cols
class: deck-comparison
---

## 知识工作会被协同增强

::left::

### 增强

- 更快搜索与归纳
- 更强初稿生成
- 更低试错成本

::right::

### 替代风险

- 低门槛内容生产
- 同质化分析任务
- 可脚本化沟通工作

---
class: deck-detail
---

## 岗位重构而非简单消失

<div class="grid grid-cols-2 gap-4">
<div>

### 被压缩

- 机械执行
- 低判断复核

</div>
<div>

### 被放大

- 需求定义
- 结果判断

</div>
</div>
""",
        3: """## 个人能力模型如何变化

| 能力层 | 过去重点 | 新重点 |
|---|---|---|
| 执行 | 手工完成 | 与 AI 协同完成 |
| 判断 | 经验复核 | 提示词与结果评估 |
| 学习 | 领域积累 | 快速迁移与组合 |

**Takeaway**: 竞争力从“会做”转向“会定义、会判断、会整合”。

---
layout: two-cols
class: deck-comparison
---

## 企业组织会如何调整

::left::

### 旧组织

- 严格岗位分工
- 信息逐层传递
- 决策链条更长

::right::

### 新组织

- 小团队高密度协同
- 人机混合交付
- 决策更靠近问题现场

---
class: deck-context
---

## 风险与不确定性

> 如果治理、培训与岗位设计跟不上，效率收益会被新的组织摩擦吞掉。

- 技能分化加剧
- 评价体系失真
- 责任边界模糊
""",
        4: """## 个人应该怎么准备

**Decision**: 把自己从“执行者”升级为“问题定义者 + 协同者”。

- 训练 AI 协同工作流
- 提升判断与复盘能力
- 建立跨领域迁移能力

---
class: deck-recommendation
---

## 团队应该怎么准备

**Decision**: 先重写流程，再重写岗位。

- 识别高重复环节
- 重新定义人机边界
- 建立新的质量与责任机制

---
layout: end
class: deck-closing
---

## 结论与下一步

**Takeaway**: AI 改变的不是单个岗位，而是工作的组织方式。

1. 先识别高重复工作
2. 再设计人机协同流程
3. 最后重构岗位与能力模型
""",
    }
    return chunk_map[chunk_number]


def _copy_slidev_skills(tmp_path, monkeypatch) -> SkillRegistry:
    skills_dir = tmp_path / "skills"
    for skill_name in ("slidev-syntax", "slidev-deck-quality", "slidev-design-system"):
        source_skill_dir = settings.project_root / "skills" / skill_name
        target_dir = skills_dir / skill_name / "scripts"
        target_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / skill_name / "SKILL.md").write_text(
            (source_skill_dir / "SKILL.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        scripts_dir = source_skill_dir / "scripts"
        if scripts_dir.exists():
            for script_path in scripts_dir.glob("*.py"):
                (target_dir / script_path.name).write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(settings, "skills_dir", skills_dir)
    return SkillRegistry(skills_dir)


def test_slidev_mvp_service_generates_artifact_with_visible_harness(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    fake_store = FakeSessionStore()
    monkeypatch.setattr(slidev_mvp_mod, "session_store", fake_store)

    markdown = _slidev_markdown()
    seen_messages: list[list[AgenticMessage]] = []
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={
                            "items": [
                                {"id": 1, "task": "规划 deck", "status": "in_progress"},
                                {"id": 2, "task": "校验并保存", "status": "pending"},
                            ]
                        },
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-3b")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={"items": _quality_outline_items_five()},
                        tool_call_id="call-4",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="dispatch_subagent",
                        args={"task": "起草第 3-4 页的关键 bullet，保持每页 2-3 个要点。"},
                        tool_call_id="call-5",
                    )
                ]
            ),
            AssistantMessage(parts=["第 3-4 页建议聚焦分层职责与 MVP 路径。"]),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="review_slidev_outline",
                            args={},
                            tool_call_id="call-6",
                        )
                    ]
                ),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="select_slidev_references",
                            args={},
                            tool_call_id="call-6b",
                        )
                    ]
                ),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="review_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-7",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="validate_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-8",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="save_slidev_artifact",
                        args={"title": "AI Product Architecture Evolution", "markdown": markdown},
                        tool_call_id="call-9",
                    )
                ]
            ),
        ],
        seen_messages=seen_messages,
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="AI 产品架构演进",
            content="围绕 harness 如何驱动 Slidev 生成离线 deck。",
            num_pages=5,
            build=False,
        )
    )

    assert artifact.slides_path.exists()
    assert artifact.validation["ok"] is True
    assert artifact.validation["native_usage_summary"]["plain_slide_count"] == 0
    assert artifact.validation["native_usage_summary"]["recipe_classes"]["deck-cover"] == 1
    assert artifact.quality["outline_review"]["ok"] is True
    assert artifact.quality["deck_review"]["ok"] is True
    assert artifact.quality["pattern_hints"][0]["slide_role"] == "cover"
    assert artifact.quality["visual_hints"][0]["recipe_name"] == "cover-hero"
    assert "cover" in artifact.quality["mapping_summary"]["recommended_layouts"]
    assert artifact.quality["visual_recipe_summary"]["matched_recipe_count"] >= 3
    assert artifact.quality["blank_first_slide_detected"] is False
    assert artifact.agentic["used_subagent"] is True
    assert artifact.agentic["loaded_skills"] == ["slidev-deck-quality", "slidev-design-system", "slidev-syntax"]
    assert "大纲已生成：5 页 - 封面(cover)；为什么现在要做(context)；Harness 分层(framework)" in artifact.agentic["final_state_summary"]
    assert "大纲审查：通过" in artifact.agentic["final_state_summary"]
    assert service.last_loop_result is not None
    assert service.last_loop_result.stop_reason == "slidev-artifact-saved"
    first_assistant = service.last_loop_result.messages[1]
    assert isinstance(first_assistant, AssistantMessage)
    assert isinstance(first_assistant.parts[0], ToolCall)
    assert first_assistant.parts[0].tool_name == "update_todo"
    state_summary_seen = False
    for message in service.last_loop_result.messages:
        if not isinstance(message, UserMessage):
            continue
        for part in message.parts:
            if isinstance(part, ToolResult) and "大纲已生成：5 页" in str(part.metadata.get("state_summary") or ""):
                state_summary_seen = True
                break
    assert state_summary_seen is True
    assert fake_store.ensure_workspace_calls == ["workspace-slidev"]


def test_slidev_mvp_service_combines_sources_and_runs_build(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    fake_store = FakeSessionStore(
        source_metas=[{"id": "src-1", "fileCategory": "pdf"}],
        source_content="Source content from uploaded material.",
    )
    monkeypatch.setattr(slidev_mvp_mod, "session_store", fake_store)

    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    (sandbox_dir / "package.json").write_text('{"name":"slidev-mvp"}', encoding="utf-8")

    commands: list[tuple[list[str], Path]] = []

    async def fake_shell_runner(command, cwd):
        commands.append((list(command), cwd))
        return subprocess.CompletedProcess(list(command), 0, stdout="ok", stderr="")

    markdown = _simple_markdown()
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={"items": [{"id": 1, "task": "生成 deck", "status": "done"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-3b")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={
                            "items": [
                                {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                                {"slide_number": 2, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
                            ]
                        },
                        tool_call_id="call-4",
                    )
                ]
            ),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="review_slidev_outline",
                            args={},
                            tool_call_id="call-5",
                        )
                    ]
                ),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="select_slidev_references",
                            args={},
                            tool_call_id="call-5b",
                        )
                    ]
                ),
                AssistantMessage(
                    parts=[
                        ToolCall(
                            tool_name="review_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-6",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="validate_slidev_deck",
                        args={"markdown": markdown},
                        tool_call_id="call-7",
                    )
                ]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="save_slidev_artifact",
                        args={"title": "Mini Deck", "markdown": markdown},
                        tool_call_id="call-8",
                    )
                ]
            ),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=sandbox_dir,
        shell_runner=fake_shell_runner,
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="",
            content="Operator notes.",
            session_id="session-1",
            source_ids=["src-1"],
            num_pages=2,
            build=True,
        )
    )

    assert service.last_state is not None
    assert "Source content from uploaded material." in service.last_state.raw_content
    assert "Operator notes." in service.last_state.raw_content
    assert artifact.build_output_dir == artifact.artifact_dir / "dist"
    assert (artifact.artifact_dir / "node_modules").is_symlink()
    assert commands == [
        (["pnpm", "install"], sandbox_dir),
        (
            [
                "./node_modules/.bin/slidev",
                "build",
                artifact.slides_path.name,
                "--out",
                artifact.build_output_dir.name,
            ],
            artifact.artifact_dir,
        ),
    ]
    assert fake_store.session_calls == [("workspace-slidev", "session-1")]
    assert fake_store.source_lookup_calls == [("workspace-slidev", ["src-1"])]
    assert fake_store.source_content_calls == [("workspace-slidev", "session-1", ["src-1"])]


def test_slidev_mvp_service_rejects_missing_inputs(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )

    try:
        asyncio.run(service.generate_deck(topic="", content="", source_ids=[], num_pages=3))
    except SlidevMvpValidationError as exc:
        assert "请提供 topic、content 或 source_ids" in str(exc)
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_slidev_mvp_service_classifies_malformed_provider_responses(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    @dataclass
    class MalformedProviderModel(AgenticModelClient):
        async def complete(self, messages, tools) -> AssistantMessage:
            raise IncompleteToolCall("tool call truncated")

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=MalformedProviderModel(),
    )

    try:
        asyncio.run(service.generate_deck(topic="AI Deck", content="offline slidev", num_pages=2))
    except SlidevMvpProviderError as exc:
        assert exc.reason_code == "provider_malformed_response"
        assert "tool call truncated" in str(exc)
    else:
        raise AssertionError("expected SlidevMvpProviderError")


def test_slidev_mvp_service_classifies_non_malformed_unexpected_provider_behavior(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    @dataclass
    class UnexpectedProviderModel(AgenticModelClient):
        async def complete(self, messages, tools) -> AssistantMessage:
            raise UnexpectedModelBehavior("unexpected provider behavior")

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=UnexpectedProviderModel(),
    )

    try:
        asyncio.run(service.generate_deck(topic="AI Deck", content="offline slidev", num_pages=2))
    except SlidevMvpProviderError as exc:
        assert exc.reason_code == "provider_unexpected_behavior"
        assert "unexpected provider behavior" in str(exc)
        assert "provider_malformed_response" not in str(exc)
    else:
        raise AssertionError("expected SlidevMvpProviderError")


def test_slidev_mvp_counts_slides_with_per_slide_frontmatter():
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    assert slidev_mvp_mod._count_slidev_slides(_native_layout_markdown()) == 4


def test_slidev_mvp_normalizes_blank_first_slide_frontmatter():
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    normalized, metadata = slidev_mvp_mod._normalize_leading_first_slide_frontmatter(_blank_first_slide_markdown())

    assert metadata["blank_first_slide_detected"] is True
    assert "layout: cover" in normalized.split("---", 2)[1]
    assert normalized.strip().startswith("---\ntheme: default")
    assert slidev_mvp_mod._count_slidev_slides(normalized) == 2


def test_slidev_mvp_normalizes_double_separator_slide_frontmatter():
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    normalized, metadata = slidev_mvp_mod._normalize_slidev_composition(_double_separator_frontmatter_markdown())

    assert metadata["double_separator_frontmatter_detected"] is True
    assert metadata["normalized_double_separator_frontmatter_count"] == 2
    assert "\n---\n\n---\nlayout: two-cols" not in normalized
    assert "\n---\nlayout: two-cols" in normalized
    assert slidev_mvp_mod._count_slidev_slides(normalized) == 3


def test_slidev_mvp_user_prompt_requires_design_system_and_seriph_theme():
    from app.services.generation.slidev_mvp import SlidevMvpService, _ResolvedInputs

    service = SlidevMvpService(workspace_id="workspace-slidev")
    prompt = service._build_user_prompt(
        _ResolvedInputs(
            topic="AI Strategy",
            material="准备一份 deck",
            num_pages=5,
            title_hint="AI Strategy",
            source_hints={"total_sources": 0, "by_file_category": {}},
        )
    )

    assert "slidev-design-system" in prompt
    assert "theme: seriph" in prompt
    assert "不要生成“像 markdown 文档章节”的页面" in prompt


def test_slidev_syntax_validate_deck_returns_structured_results(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    valid = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _simple_markdown(), "expected_pages": 2}},
        )
    )
    invalid = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": "# only one slide", "expected_pages": 2}},
        )
    )

    assert valid["ok"] is True
    assert valid["slide_count"] == 2
    assert valid["blank_first_slide_detected"] is False
    assert invalid["ok"] is False
    assert {issue["code"] for issue in invalid["issues"]} >= {
        "missing_frontmatter",
        "missing_separator",
        "too_few_slides",
    }


def test_slidev_syntax_validate_deck_warns_when_native_layouts_are_missing(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)
    flat_markdown = """---
theme: default
title: Flat Deck
---

# Flat Deck

---

## Page 2

- one
- two
- three

---

## Page 3

- one
- two
- three

---

## Closing

- wrap
- up
- now
"""

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": flat_markdown, "expected_pages": 4}},
        )
    )

    assert result["ok"] is True
    warning_codes = {warning["code"] for warning in result["warnings"]}
    assert "low_slidev_native_usage" in warning_codes


def test_slidev_syntax_validate_deck_reports_native_usage_summary(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _native_layout_markdown(), "expected_pages": 4}},
        )
    )

    assert result["ok"] is True
    native_usage = result["native_usage_summary"]
    assert native_usage["layouts"] == ["cover", "end", "two-cols"]
    assert native_usage["native_slide_count"] == 4
    assert native_usage["plain_slide_count"] == 0
    assert native_usage["recipe_classes"]["deck-cover"] == 1
    assert native_usage["visual_recipe_slide_count"] >= 3


def test_slidev_syntax_validate_deck_counts_callout_usage(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    markdown = """---
theme: default
title: Callout Deck
layout: cover
class: deck-cover
---

# Callout Deck

Deck with a callout block.

---
class: deck-context
---

## Context

::note::
This slide should count as callout usage.
::"""

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": markdown, "expected_pages": 2}},
        )
    )

    assert result["ok"] is True
    assert result["native_usage_summary"]["pattern_counts"]["callout"] == 1


def test_slidev_syntax_validate_deck_detects_blank_first_slide_pattern(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _blank_first_slide_markdown(), "expected_pages": 2}},
        )
    )

    assert result["ok"] is True
    assert result["blank_first_slide_detected"] is True
    assert {warning["code"] for warning in result["warnings"]} >= {"blank_first_slide_normalized"}


def test_slidev_syntax_validate_deck_detects_double_separator_frontmatter_pattern(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _double_separator_frontmatter_markdown(), "expected_pages": 3}},
        )
    )

    assert result["ok"] is True
    assert {warning["code"] for warning in result["warnings"]} >= {"double_separator_frontmatter_normalized"}
    assert result["slide_count"] == 3


def test_slidev_syntax_validate_deck_rejects_unfenced_slide_frontmatter(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    result = asyncio.run(
        execute_skill(
            "slidev-syntax",
            "validate_deck.py",
            {"slides": [], "parameters": {"markdown": _unfenced_frontmatter_markdown(), "expected_pages": 3}},
        )
    )

    assert result["ok"] is False
    assert {issue["code"] for issue in result["issues"]} >= {"unfenced_slide_frontmatter"}


def test_slidev_deck_quality_scripts_return_structured_results(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_outline.py",
            {"slides": [], "parameters": {"outline_items": _quality_outline_items()[:4], "expected_pages": 4}},
        )
    )
    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _simple_markdown(), "outline_items": _quality_outline_items()[:2]}},
        )
    )

    assert outline_review["ok"] is False
    assert {issue["code"] for issue in outline_review["issues"]} >= {"missing_closing"}
    assert deck_review["ok"] is True
    assert isinstance(deck_review["warnings"], list)


def test_slidev_outline_review_enforces_contract_boundaries(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_outline.py",
            {
                "slides": [],
                "parameters": {
                    "outline_items": [
                        {
                            "slide_number": 1,
                            "title": "背景",
                            "slide_role": "context",
                            "content_shape": "problem-bullets",
                            "goal": "说明问题",
                        },
                        {
                            "slide_number": 2,
                            "title": "建议",
                            "slide_role": "recommendation",
                            "content_shape": "decision",
                            "goal": "提出动作",
                        },
                        {
                            "slide_number": 3,
                            "title": "结尾",
                            "slide_role": "closing",
                            "content_shape": "next-step",
                            "goal": "收束",
                        },
                    ],
                    "expected_pages": 5,
                },
            },
        )
    )

    assert outline_review["ok"] is False
    assert {issue["code"] for issue in outline_review["issues"]} >= {
        "missing_cover",
        "first_slide_not_cover",
        "outline_page_budget_mismatch",
    }
    assert outline_review["contract_summary"]["expected_pages"] == 5
    assert outline_review["contract_summary"]["actual_pages"] == 3
    assert outline_review["contract_summary"]["first_role"] == "context"
    assert outline_review["contract_summary"]["last_role"] == "closing"


def test_slidev_deck_review_returns_slide_reports_and_blocks_contract_mismatches(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
        {"slide_number": 2, "title": "方案对比", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "对比路径"},
        {"slide_number": 3, "title": "下一步", "slide_role": "closing", "content_shape": "next-step", "goal": "收束"},
    ]
    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _comparison_mismatch_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is False
    assert {issue["code"] for issue in deck_review["issues"]} >= {"comparison_role_mismatch"}
    assert deck_review["contract_summary"]["expected_slide_count"] == 3
    assert deck_review["contract_summary"]["actual_slide_count"] == 3
    assert deck_review["slide_reports"][1]["role"] == "comparison"
    assert deck_review["slide_reports"][1]["status"] == "failed"
    assert {finding["code"] for finding in deck_review["slide_reports"][1]["findings"]} == {"comparison_role_mismatch"}


def test_slidev_deck_review_observes_native_layout_mapping(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {
            "slide_number": 1,
            "title": "封面",
            "slide_role": "cover",
            "content_shape": "title-subtitle",
            "goal": "开场",
            "slidev_pattern_hint": {"preferred_layouts": ["cover", "center"], "preferred_patterns": ["hero-title"]},
            "slidev_visual_hint": {"name": "cover-hero", "preferred_classes": ["deck-cover"], "required_signals": ["hero-title", "short-subtitle"]},
        },
        {
            "slide_number": 2,
            "title": "背景",
            "slide_role": "context",
            "content_shape": "quote-callout",
            "goal": "背景",
            "slidev_pattern_hint": {"preferred_layouts": [], "preferred_patterns": ["quote", "callout"]},
            "slidev_visual_hint": {"name": "context-brief", "preferred_classes": ["deck-context"], "required_signals": ["quote-or-callout"]},
        },
        {
            "slide_number": 3,
            "title": "方案对比",
            "slide_role": "comparison",
            "content_shape": "compare-grid",
            "goal": "对比路径",
            "slidev_pattern_hint": {"preferred_layouts": ["two-cols"], "preferred_patterns": ["two-cols", "table"]},
            "slidev_visual_hint": {"name": "comparison-split", "preferred_classes": ["deck-comparison"], "required_signals": ["split-compare", "contrast-labels"]},
        },
        {
            "slide_number": 4,
            "title": "下一步",
            "slide_role": "closing",
            "content_shape": "next-step",
            "goal": "收束",
            "slidev_pattern_hint": {"preferred_layouts": ["end", "center"], "preferred_patterns": ["next-step"]},
            "slidev_visual_hint": {"name": "closing-takeaway", "preferred_classes": ["deck-closing"], "required_signals": ["next-step-or-takeaway"]},
        },
    ]
    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _native_layout_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is True
    assert deck_review["slide_reports"][0]["observed_layout"] == "cover"
    assert deck_review["slide_reports"][2]["observed_layout"] == "two-cols"
    assert deck_review["slide_reports"][3]["observed_layout"] == "end"
    assert deck_review["slide_reports"][0]["preferred_layouts"] == ["cover", "center"]
    assert deck_review["slide_reports"][0]["visual_recipe_status"] == "matched"
    assert deck_review["visual_recipe_summary"]["matched_recipe_count"] >= 3


def test_slidev_deck_review_reports_blank_first_slide_normalization(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {
            "slide_number": 1,
            "title": "封面",
            "slide_role": "cover",
            "content_shape": "title-subtitle",
            "goal": "开场",
            "slidev_pattern_hint": {"preferred_layouts": ["cover", "center"], "preferred_patterns": ["hero-title"]},
            "slidev_visual_hint": {"name": "cover-hero", "preferred_classes": ["deck-cover"], "required_signals": ["hero-title", "short-subtitle"]},
        },
        {
            "slide_number": 2,
            "title": "收尾",
            "slide_role": "closing",
            "content_shape": "next-step",
            "goal": "收束",
            "slidev_pattern_hint": {"preferred_layouts": ["end", "center"], "preferred_patterns": ["next-step"]},
            "slidev_visual_hint": {"name": "closing-takeaway", "preferred_classes": ["deck-closing"], "required_signals": ["next-step-or-takeaway"]},
        },
    ]

    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _blank_first_slide_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is True
    assert deck_review["blank_first_slide_detected"] is True
    assert {warning["code"] for warning in deck_review["warnings"]} >= {"blank_first_slide_normalized"}


def test_slidev_deck_review_warns_when_cover_is_document_like(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    markdown = """---
theme: seriph
title: Document Like Cover
---

# Document Like Cover

Short subtitle

---

## Next Step

- decide
"""
    outline_items = [
        {
            "slide_number": 1,
            "title": "封面",
            "slide_role": "cover",
            "content_shape": "title-subtitle",
            "goal": "开场",
            "slidev_pattern_hint": {"preferred_layouts": ["cover", "center"], "preferred_patterns": ["hero-title"]},
            "slidev_visual_hint": {"name": "cover-hero", "preferred_classes": ["deck-cover"], "required_signals": ["hero-title", "short-subtitle"]},
        },
        {
            "slide_number": 2,
            "title": "收尾",
            "slide_role": "closing",
            "content_shape": "next-step",
            "goal": "收束",
            "slidev_pattern_hint": {"preferred_layouts": ["end", "center"], "preferred_patterns": ["next-step"]},
            "slidev_visual_hint": {"name": "closing-takeaway", "preferred_classes": ["deck-closing"], "required_signals": ["next-step-or-takeaway"]},
        },
    ]

    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": markdown, "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is True
    assert {warning["code"] for warning in deck_review["warnings"]} >= {"document_like_cover"}
    assert "cover_native_layout_missing" not in {warning["code"] for warning in deck_review["warnings"]}


def test_slidev_deck_review_reports_double_separator_frontmatter_normalization(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {
            "slide_number": 1,
            "title": "封面",
            "slide_role": "cover",
            "content_shape": "title-subtitle",
            "goal": "开场",
            "slidev_pattern_hint": {"preferred_layouts": ["cover", "center"], "preferred_patterns": ["hero-title"]},
            "slidev_visual_hint": {"name": "cover-hero", "preferred_classes": ["deck-cover"], "required_signals": ["hero-title", "short-subtitle"]},
        },
        {
            "slide_number": 2,
            "title": "对比",
            "slide_role": "comparison",
            "content_shape": "compare-grid",
            "goal": "对比",
            "slidev_pattern_hint": {"preferred_layouts": ["two-cols"], "preferred_patterns": ["two-cols", "table"]},
            "slidev_visual_hint": {"name": "comparison-split", "preferred_classes": ["deck-comparison"], "required_signals": ["split-compare", "contrast-labels"]},
        },
        {
            "slide_number": 3,
            "title": "收尾",
            "slide_role": "closing",
            "content_shape": "next-step",
            "goal": "收束",
            "slidev_pattern_hint": {"preferred_layouts": ["end", "center"], "preferred_patterns": ["next-step"]},
            "slidev_visual_hint": {"name": "closing-takeaway", "preferred_classes": ["deck-closing"], "required_signals": ["next-step-or-takeaway"]},
        },
    ]

    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _double_separator_frontmatter_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is True
    assert {warning["code"] for warning in deck_review["warnings"]} >= {"double_separator_frontmatter_normalized"}
    assert deck_review["contract_summary"]["actual_slide_count"] == 3


def test_slidev_deck_review_blocks_unfenced_slide_frontmatter(monkeypatch, tmp_path):
    _copy_slidev_skills(tmp_path, monkeypatch)

    outline_items = [
        {
            "slide_number": 1,
            "title": "封面",
            "slide_role": "cover",
            "content_shape": "title-subtitle",
            "goal": "开场",
            "slidev_pattern_hint": {"preferred_layouts": ["cover", "center"], "preferred_patterns": ["hero-title"]},
            "slidev_visual_hint": {"name": "cover-hero", "preferred_classes": ["deck-cover"], "required_signals": ["hero-title", "short-subtitle"]},
        },
        {
            "slide_number": 2,
            "title": "对比",
            "slide_role": "comparison",
            "content_shape": "compare-grid",
            "goal": "对比",
            "slidev_pattern_hint": {"preferred_layouts": ["two-cols"], "preferred_patterns": ["two-cols", "table"]},
            "slidev_visual_hint": {"name": "comparison-split", "preferred_classes": ["deck-comparison"], "required_signals": ["split-compare", "contrast-labels"]},
        },
        {
            "slide_number": 3,
            "title": "收尾",
            "slide_role": "closing",
            "content_shape": "next-step",
            "goal": "收束",
            "slidev_pattern_hint": {"preferred_layouts": ["end", "center"], "preferred_patterns": ["next-step"]},
            "slidev_visual_hint": {"name": "closing-takeaway", "preferred_classes": ["deck-closing"], "required_signals": ["next-step-or-takeaway"]},
        },
    ]

    deck_review = asyncio.run(
        execute_skill(
            "slidev-deck-quality",
            "review_deck.py",
            {"slides": [], "parameters": {"markdown": _unfenced_frontmatter_markdown(), "outline_items": outline_items}},
        )
    )

    assert deck_review["ok"] is False
    assert {issue["code"] for issue in deck_review["issues"]} >= {"unfenced_slide_frontmatter"}


def test_slidev_mvp_service_requires_quality_review_before_save(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _simple_markdown()
    outline_items = [
        {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
        {"slide_number": 2, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
    ]
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=2)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=2,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    outline_result = asyncio.run(registry.get("set_slidev_outline").handler({"items": outline_items}))
    assert "Recorded Slidev outline" in outline_result
    runtime.validation = {"ok": True, "slide_count": 2, "issues": [], "warnings": []}
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    try:
        asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Mini Deck", "markdown": markdown}))
    except SlidevMvpValidationError as exc:
        assert exc.reason_code == "outline_review_missing"
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_slidev_mvp_service_allows_save_when_only_warnings_remain(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _slidev_markdown()
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=5)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=5,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(registry.get("set_slidev_outline").handler({"items": _quality_outline_items_five()}))
    runtime.outline_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "outline_role_run_repetition", "message": "warn"}],
        "roles": [item["slide_role"] for item in _quality_outline_items_five()],
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.outline_review_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.reference_selection = slidev_mvp_mod._select_slidev_references(
        outline_items=_quality_outline_items_five(),
        topic="demo",
        num_pages=5,
        material_excerpt="demo",
    )
    runtime.reference_selection_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.deck_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "framework_role_weakened", "message": "warn"}],
        "signatures": [],
        "slide_reports": [],
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.deck_review_hash = slidev_mvp_mod._text_hash(markdown)
    runtime.validation = {"ok": True, "slide_count": 5, "issues": [], "warnings": [{"code": "weak_cover", "message": "warn"}]}
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    result = asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Warning Deck", "markdown": markdown}))

    assert result.stop_loop is True
    assert runtime.saved_artifact is not None
    assert runtime.saved_artifact.quality["outline_review"]["ok"] is True
    assert runtime.saved_artifact.quality["deck_review"]["ok"] is True
    assert runtime.saved_artifact.quality["structure_warnings"]


def test_slidev_mvp_service_persists_normalized_first_slide(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _blank_first_slide_markdown()
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=2)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=2,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(
        registry.get("set_slidev_outline").handler(
            {
                "items": [
                    {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                    {"slide_number": 2, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
                ]
            }
        )
    )
    runtime.outline_review = {"ok": True, "issues": [], "warnings": [], "roles": ["cover", "closing"], "contract_summary": {"hard_issue_count": 0, "warning_count": 0}}
    runtime.outline_review_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.reference_selection = slidev_mvp_mod._select_slidev_references(
        outline_items=state.outline["items"],
        topic="demo",
        num_pages=2,
        material_excerpt="demo",
    )
    runtime.reference_selection_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.deck_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "blank_first_slide_normalized", "message": "warn"}],
        "signatures": [],
        "slide_reports": [],
        "blank_first_slide_detected": True,
        "visual_recipe_summary": {"matched_recipe_count": 0, "weak_recipe_count": 0, "missing_recipe_count": 0, "expected_recipe_names": []},
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.deck_review_hash = slidev_mvp_mod._text_hash(markdown)
    runtime.validation = {
        "ok": True,
        "slide_count": 2,
        "issues": [],
        "warnings": [{"code": "blank_first_slide_normalized", "message": "warn"}],
        "blank_first_slide_detected": True,
        "native_usage_summary": {"layouts": ["cover"], "layout_counts": {"cover": 1}, "pattern_counts": {}, "class_counts": {"deck-cover": 1}, "recipe_classes": {"deck-cover": 1}, "native_slide_count": 2, "plain_slide_count": 0, "visual_recipe_slide_count": 1},
    }
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Blank Cover Bug", "markdown": markdown}))

    assert runtime.saved_artifact is not None
    assert runtime.saved_artifact.markdown.startswith("---\ntheme: default\ntitle: Blank Cover Bug\nlayout: cover\nclass: deck-cover\n---")
    assert runtime.saved_artifact.quality["blank_first_slide_detected"] is True


def test_slidev_mvp_service_persists_normalized_double_separator_frontmatter(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _double_separator_frontmatter_markdown()
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=3)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=3,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(
        registry.get("set_slidev_outline").handler(
            {
                "items": [
                    {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                    {"slide_number": 2, "title": "对比", "slide_role": "comparison", "content_shape": "compare-grid", "goal": "对比"},
                    {"slide_number": 3, "title": "收尾", "slide_role": "closing", "content_shape": "next-step", "goal": "收尾"},
                ]
            }
        )
    )
    runtime.outline_review = {"ok": True, "issues": [], "warnings": [], "roles": ["cover", "comparison", "closing"], "contract_summary": {"hard_issue_count": 0, "warning_count": 0}}
    runtime.outline_review_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.reference_selection = slidev_mvp_mod._select_slidev_references(
        outline_items=state.outline["items"],
        topic="demo",
        num_pages=3,
        material_excerpt="demo",
    )
    runtime.reference_selection_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.deck_review = {
        "ok": True,
        "issues": [],
        "warnings": [{"code": "double_separator_frontmatter_normalized", "message": "warn"}],
        "signatures": [],
        "slide_reports": [],
        "blank_first_slide_detected": False,
        "visual_recipe_summary": {"matched_recipe_count": 0, "weak_recipe_count": 0, "missing_recipe_count": 0, "expected_recipe_names": []},
        "contract_summary": {"hard_issue_count": 0, "warning_count": 1},
    }
    runtime.deck_review_hash = slidev_mvp_mod._text_hash(markdown)
    runtime.validation = {
        "ok": True,
        "slide_count": 3,
        "issues": [],
        "warnings": [{"code": "double_separator_frontmatter_normalized", "message": "warn"}],
        "blank_first_slide_detected": False,
        "native_usage_summary": {"layouts": ["two-cols", "end"], "layout_counts": {"two-cols": 1, "end": 1}, "pattern_counts": {}, "class_counts": {"deck-comparison": 1, "deck-closing": 1}, "recipe_classes": {"deck-comparison": 1, "deck-closing": 1}, "native_slide_count": 3, "plain_slide_count": 0, "visual_recipe_slide_count": 2},
    }
    runtime.validation_hash = slidev_mvp_mod._text_hash(markdown)

    asyncio.run(registry.get("save_slidev_artifact").handler({"title": "Double Separator", "markdown": markdown}))

    assert runtime.saved_artifact is not None
    assert "\n---\n\n---\nlayout: two-cols" not in runtime.saved_artifact.markdown
    assert runtime.saved_artifact.quality["composition_normalization"]["double_separator_frontmatter_detected"] is True
    assert runtime.saved_artifact.quality["composition_normalization"]["normalized_double_separator_frontmatter_count"] == 2


def test_slidev_review_tools_pull_context_from_state(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=5)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=5,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())
    asyncio.run(registry.get("set_slidev_outline").handler({"items": _quality_outline_items_five()}))
    markdown = _slidev_markdown()
    assert state.document_metadata["slidev_pattern_hints"][0]["preferred_layouts"] == ["cover", "center"]

    outline_review = asyncio.run(registry.get("review_slidev_outline").handler({}))
    deck_review = asyncio.run(registry.get("review_slidev_deck").handler({"markdown": markdown}))
    validation = asyncio.run(registry.get("validate_slidev_deck").handler({"markdown": markdown}))

    assert outline_review["ok"] is True
    assert deck_review["ok"] is True
    assert validation["ok"] is True
    assert runtime.outline_review == outline_review
    assert runtime.deck_review == deck_review
    assert runtime.validation == validation
    assert state.document_metadata["slidev_visual_hints"][0]["visual_recipe"]["name"] == "cover-hero"


def test_slidev_mvp_service_reports_failed_outline_review_reason_after_max_turns(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    model = StubModel(
        responses=[
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="update_todo",
                        args={"items": [{"id": 1, "task": "规划 deck", "status": "in_progress"}]},
                        tool_call_id="call-1",
                    )
                ]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]
            ),
            AssistantMessage(
                parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-3b")]
            ),
            AssistantMessage(
                parts=[
                    ToolCall(
                        tool_name="set_slidev_outline",
                        args={
                            "items": [
                                {"slide_number": 1, "title": "封面", "slide_role": "cover", "content_shape": "title-subtitle", "goal": "开场"},
                                {"slide_number": 2, "title": "框架", "slide_role": "framework", "content_shape": "framework-grid", "goal": "解释结构"},
                            ]
                        },
                        tool_call_id="call-4",
                    )
                ]
            ),
            AssistantMessage(parts=["done"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    try:
        asyncio.run(service.generate_deck(topic="demo", content="demo", num_pages=2, build=False))
    except SlidevMvpValidationError as exc:
        assert exc.reason_code == "outline_review_missing"
        assert "review_slidev_outline" in str(exc)
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_slidev_mvp_service_controller_finalizes_short_deck_without_explicit_save(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    markdown = _slidev_markdown()
    model = StubModel(
        responses=[
            AssistantMessage(parts=[ToolCall(tool_name="update_todo", args={"items": [{"id": 1, "task": "规划 deck", "status": "in_progress"}]}, tool_call_id="call-1")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-4")]),
            AssistantMessage(parts=[ToolCall(tool_name="set_slidev_outline", args={"items": _quality_outline_items_five()}, tool_call_id="call-5")]),
            AssistantMessage(parts=[ToolCall(tool_name="review_slidev_outline", args={}, tool_call_id="call-6")]),
            AssistantMessage(parts=[ToolCall(tool_name="select_slidev_references", args={}, tool_call_id="call-7")]),
            AssistantMessage(parts=[ToolCall(tool_name="review_slidev_deck", args={"markdown": markdown}, tool_call_id="call-8")]),
            AssistantMessage(parts=[ToolCall(tool_name="validate_slidev_deck", args={"markdown": markdown}, tool_call_id="call-9")]),
            AssistantMessage(parts=["done"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    artifact = asyncio.run(service.generate_deck(topic="demo", content="demo", num_pages=5, build=False))

    assert artifact.validation["ok"] is True
    assert artifact.quality["outline_review"]["ok"] is True
    assert artifact.quality["selected_style"]["name"]
    assert artifact.agentic["long_deck_mode"] is False
    assert artifact.slides_path.exists()


def test_slidev_mvp_controller_finalization_ignores_sticky_early_save_failure(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=5)
    state.outline = {"items": _quality_outline_items_five()}
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=5,
    )
    runtime.outline_review = {"ok": True, "issues": [], "warnings": []}
    runtime.outline_review_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.reference_selection = slidev_mvp_mod._select_slidev_references(
        outline_items=_quality_outline_items_five(),
        topic="demo",
        num_pages=5,
        material_excerpt="demo",
    )
    runtime.reference_selection_hash = slidev_mvp_mod._outline_hash(state.outline)
    runtime.save_failure = SlidevMvpValidationError(
        "stale failure",
        reason_code="deck_review_missing",
        next_action="old save error",
    )
    runtime.latest_markdown = _slidev_markdown()

    artifact = asyncio.run(service._controller_finalize_deck(title="Demo", state=state, runtime=runtime))

    assert artifact.validation["ok"] is True
    assert runtime.save_failure is None
    assert artifact.quality["selected_style"]["name"]


def test_slidev_mvp_service_uses_long_deck_chunk_orchestration_for_12_pages(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())

    async def fake_parallel_subagents(specs, *, registry=None, model=None):
        del registry, model
        return [
            slidev_mvp_mod.AgenticLoopResult(output_text=_chunk_fragment(index), turns=1, stop_reason="text")
            for index, _spec in enumerate(specs, start=1)
        ]

    monkeypatch.setattr(slidev_mvp_mod, "run_parallel_subagents", fake_parallel_subagents)

    model = StubModel(
        responses=[
            AssistantMessage(parts=[ToolCall(tool_name="update_todo", args={"items": [{"id": 1, "task": "长 deck 规划", "status": "in_progress"}]}, tool_call_id="call-1")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-4")]),
            AssistantMessage(parts=[ToolCall(tool_name="set_slidev_outline", args={"items": _quality_outline_items_twelve()}, tool_call_id="call-5")]),
            AssistantMessage(parts=[ToolCall(tool_name="review_slidev_outline", args={}, tool_call_id="call-6")]),
            AssistantMessage(parts=[ToolCall(tool_name="select_slidev_references", args={}, tool_call_id="call-7")]),
            AssistantMessage(parts=["planning complete"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="人工智能对未来工作影响",
            content="准备一个关于人工智能对未来工作影响的12页演示文稿",
            num_pages=12,
            build=False,
        )
    )

    assert artifact.agentic["long_deck_mode"] is True
    assert artifact.agentic["used_subagent"] is True
    assert artifact.validation["slide_count"] == 12
    assert artifact.validation["ok"] is True
    assert artifact.quality["chunk_summary"]["planned_chunks"] == 4
    assert artifact.quality["chunk_summary"]["completed_chunks"] == 4
    assert len(artifact.quality["chunk_reports"]) == 4


def test_slidev_mvp_service_retries_only_failed_chunk_in_long_deck_mode(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    calls: list[list[str]] = []

    async def fake_parallel_subagents(specs, *, registry=None, model=None):
        del registry, model
        chunk_ids = [spec.task.split(" ")[3] for spec in specs]
        calls.append(chunk_ids)
        outputs: list[slidev_mvp_mod.AgenticLoopResult] = []
        for chunk_id in chunk_ids:
            if chunk_id == "chunk-2" and len(calls) == 1:
                outputs.append(slidev_mvp_mod.AgenticLoopResult(output_text="## broken fragment", turns=1, stop_reason="text"))
                continue
            chunk_index = int(chunk_id.split("-")[-1])
            outputs.append(slidev_mvp_mod.AgenticLoopResult(output_text=_chunk_fragment(chunk_index), turns=1, stop_reason="text"))
        return outputs

    monkeypatch.setattr(slidev_mvp_mod, "run_parallel_subagents", fake_parallel_subagents)

    model = StubModel(
        responses=[
            AssistantMessage(parts=[ToolCall(tool_name="update_todo", args={"items": [{"id": 1, "task": "长 deck 规划", "status": "in_progress"}]}, tool_call_id="call-1")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-4")]),
            AssistantMessage(parts=[ToolCall(tool_name="set_slidev_outline", args={"items": _quality_outline_items_twelve()}, tool_call_id="call-5")]),
            AssistantMessage(parts=[ToolCall(tool_name="review_slidev_outline", args={}, tool_call_id="call-6")]),
            AssistantMessage(parts=[ToolCall(tool_name="select_slidev_references", args={}, tool_call_id="call-7")]),
            AssistantMessage(parts=["planning complete"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    artifact = asyncio.run(
        service.generate_deck(
            topic="人工智能对未来工作影响",
            content="准备一个关于人工智能对未来工作影响的12页演示文稿",
            num_pages=12,
            build=False,
        )
    )

    assert calls == [["chunk-1", "chunk-2", "chunk-3", "chunk-4"], ["chunk-2"]]
    assert artifact.quality["chunk_summary"]["retried_chunks"] == 1
    chunk_two = next(report for report in artifact.quality["chunk_reports"] if report["chunk_id"] == "chunk-2")
    assert chunk_two["attempts"] == 2


def test_slidev_mvp_service_exposes_failed_chunk_reasons_in_long_deck_mode(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())

    async def fake_parallel_subagents(specs, *, registry=None, model=None):
        del registry, model
        outputs: list[slidev_mvp_mod.AgenticLoopResult] = []
        for spec in specs:
            chunk_id = spec.task.split(" ")[3]
            if chunk_id == "chunk-1":
                outputs.append(slidev_mvp_mod.AgenticLoopResult(output_text="## broken fragment", turns=1, stop_reason="text"))
                continue
            chunk_index = int(chunk_id.split("-")[-1])
            outputs.append(slidev_mvp_mod.AgenticLoopResult(output_text=_chunk_fragment(chunk_index), turns=1, stop_reason="text"))
        return outputs

    monkeypatch.setattr(slidev_mvp_mod, "run_parallel_subagents", fake_parallel_subagents)

    model = StubModel(
        responses=[
            AssistantMessage(parts=[ToolCall(tool_name="update_todo", args={"items": [{"id": 1, "task": "长 deck 规划", "status": "in_progress"}]}, tool_call_id="call-1")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-syntax"}, tool_call_id="call-2")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-deck-quality"}, tool_call_id="call-3")]),
            AssistantMessage(parts=[ToolCall(tool_name="load_skill", args={"name": "slidev-design-system"}, tool_call_id="call-4")]),
            AssistantMessage(parts=[ToolCall(tool_name="set_slidev_outline", args={"items": _quality_outline_items_twelve()}, tool_call_id="call-5")]),
            AssistantMessage(parts=[ToolCall(tool_name="review_slidev_outline", args={}, tool_call_id="call-6")]),
            AssistantMessage(parts=[ToolCall(tool_name="select_slidev_references", args={}, tool_call_id="call-7")]),
            AssistantMessage(parts=["planning complete"]),
        ]
    )
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
        model=model,
    )

    try:
        asyncio.run(
            service.generate_deck(
                topic="人工智能对未来工作影响",
                content="准备一个关于人工智能对未来工作影响的12页演示文稿",
                num_pages=12,
                build=False,
            )
        )
    except SlidevMvpValidationError as exc:
        assert exc.reason_code == "chunk_generation_failed"
        assert "chunk-1(" in str(exc)
        assert "review=" in str(exc) or "validation=" in str(exc)
        state = service.last_state
        assert state is not None
        chunk_summary = state.document_metadata["slidev_chunk_summary"]
        assert chunk_summary["failed_chunks"] == ["chunk-1"]
        chunk_reports = state.document_metadata["slidev_chunk_reports"]
        failed_report = next(report for report in chunk_reports if report["chunk_id"] == "chunk-1")
        assert failed_report["status"] == "failed"
        assert failed_report["review_issue_codes"] or failed_report["validation_issue_codes"]
    else:
        raise AssertionError("expected SlidevMvpValidationError")


def test_set_slidev_outline_requires_continuous_unique_numbers(monkeypatch, tmp_path):
    from app.services.generation import slidev_mvp as slidev_mvp_mod
    from app.services.generation.agentic.todo import TodoManager
    from app.services.pipeline.graph import PipelineState

    skill_registry = _copy_slidev_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(slidev_mvp_mod, "session_store", FakeSessionStore())
    service = SlidevMvpService(
        workspace_id="workspace-slidev",
        skill_registry=skill_registry,
        artifact_root=tmp_path / "artifacts",
        sandbox_dir=tmp_path / "sandbox",
    )
    state = PipelineState(topic="demo", raw_content="demo", num_pages=2)
    runtime = slidev_mvp_mod._RuntimeContext(
        deck_id="deck-test",
        artifact_dir=tmp_path / "artifacts" / "deck-test",
        slides_path=tmp_path / "artifacts" / "deck-test" / "slides.md",
        requested_pages=2,
    )
    registry = service._build_registry(state=state, runtime=runtime, todo_manager=TodoManager())

    try:
        asyncio.run(
            registry.get("set_slidev_outline").handler(
                {
                    "items": [
                        {
                            "slide_number": 1,
                            "title": "封面",
                            "slide_role": "cover",
                            "content_shape": "title-subtitle",
                            "goal": "开场",
                        },
                        {
                            "slide_number": 3,
                            "title": "收尾",
                            "slide_role": "closing",
                            "content_shape": "next-step",
                            "goal": "收尾",
                        },
                    ]
                }
            )
        )
    except ValueError as exc:
        assert "continuous 1..N sequence" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_slidev_mvp_api_returns_artifact_metadata(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            assert self.workspace_id == "workspace-api"
            assert kwargs["build"] is False
            return SlidevMvpArtifacts(
                deck_id="deck-api-1",
                title="API Deck",
                markdown=_simple_markdown(),
                artifact_dir=Path("/tmp/api-artifact"),
                slides_path=Path("/tmp/api-artifact/slides.md"),
                build_output_dir=None,
                dev_command="pnpm exec slidev /tmp/api-artifact/slides.md",
                build_command="pnpm exec slidev build /tmp/api-artifact/slides.md --out /tmp/api-artifact/dist",
                validation={"ok": True, "slide_count": 2, "issues": [], "warnings": []},
                quality={"outline_review": {"ok": True}, "deck_review": {"ok": True}, "structure_warnings": []},
                agentic={"turns": 4, "stop_reason": "slidev-artifact-saved"},
            )

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={
            "topic": "API Deck",
            "content": "offline slidev",
            "num_pages": 2,
            "build": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deck_id"] == "deck-api-1"
    assert payload["validation"]["ok"] is True
    assert payload["quality"]["outline_review"]["ok"] is True
    assert payload["agentic"]["stop_reason"] == "slidev-artifact-saved"


def test_slidev_mvp_api_maps_validation_errors(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            raise SlidevMvpValidationError(
                "Deck 大纲结构审查未通过，不能保存 artifact。",
                reason_code="outline_review_failed",
                next_action="修正大纲后重新调用 review_slidev_outline()",
            )

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "Deck 大纲结构审查未通过" in detail
    assert "reason=outline_review_failed" in detail


def test_slidev_mvp_api_maps_model_http_errors(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            raise ModelHTTPError(429, "minimax/minimax-m2.5", {"message": "rate limited"})

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={
            "topic": "API Deck",
            "content": "offline slidev",
            "num_pages": 2,
        },
    )

    assert response.status_code == 503
    assert "上游模型请求失败 (429)" in response.json()["detail"]


def test_slidev_mvp_api_maps_provider_malformed_errors(monkeypatch):
    from app.api.v2 import generation as generation_api

    class FakeService:
        def __init__(self, *, workspace_id: str):
            self.workspace_id = workspace_id

        async def generate_deck(self, **kwargs):
            raise SlidevMvpProviderError(
                "上游模型返回了不完整或异常的响应，Slidev deck 生成已中止。",
                reason_code="provider_malformed_response",
                next_action="请重试生成；若持续失败，请切换模型或稍后重试。",
            )

    monkeypatch.setattr(generation_api, "SlidevMvpService", FakeService)
    client = TestClient(app)

    response = client.post(
        "/api/v2/generation/slidev-mvp",
        headers={"X-Workspace-Id": "workspace-api"},
        json={
            "topic": "API Deck",
            "content": "offline slidev",
            "num_pages": 2,
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "上游模型返回了不完整或异常的响应" in detail
    assert "reason=provider_malformed_response" in detail
