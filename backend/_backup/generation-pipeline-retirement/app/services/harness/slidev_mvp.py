"""Dev-only Slidev MVP path for validating the harness + skill system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.harness import load_generation_harness_config
from app.services.pipeline.graph import PipelineState, stage_generate_outline, stage_parse_document
from app.services.skill_runtime.executor import execute_skill


@dataclass
class SlidevMvpTrace:
    step: str
    detail: str


@dataclass
class SlidevMvpResult:
    markdown: str
    output_path: str
    trace: list[SlidevMvpTrace] = field(default_factory=list)
    outline: dict[str, Any] = field(default_factory=dict)


async def run_slidev_mvp(
    *,
    topic: str,
    content: str,
    num_pages: int,
) -> SlidevMvpResult:
    cfg = load_generation_harness_config()
    state = PipelineState(
        raw_content=content or topic,
        topic=topic or "Slidev MVP",
        num_pages=max(3, min(num_pages, settings.max_slide_pages)),
        job_id="slidev-mvp",
    )
    trace: list[SlidevMvpTrace] = []

    await stage_parse_document(state)
    trace.append(SlidevMvpTrace(step="parse_document", detail="解析输入并提取结构信号"))

    await stage_generate_outline(state)
    trace.append(
        SlidevMvpTrace(
            step="generate_outline",
            detail=f"生成 {len(state.outline.get('items', []))} 页结构化大纲",
        )
    )

    rendered = await execute_skill(
        skill_name="slidev-mvp",
        script_name="render_slidev_markdown.py",
        input_data={
            "slides": [],
            "parameters": {
                "title": topic or "Slidev MVP",
                "topic": topic or "Slidev MVP",
                "outline": state.outline,
                "theme": cfg.slidev.theme,
                "paginate": cfg.slidev.paginate,
            },
        },
    )
    markdown = str(rendered.get("markdown") or "").strip() + "\n"
    trace.append(SlidevMvpTrace(step="slidev_skill", detail="调用 slidev-mvp skill 渲染 Markdown"))

    output_dir = settings.project_root / ".codex-output" / "slidev"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (topic or "slidev-mvp").strip().replace("/", "-").replace(" ", "-")[:40] or "slidev-mvp"
    output_path = output_dir / f"{safe_name}.md"
    output_path.write_text(markdown, encoding="utf-8")
    trace.append(SlidevMvpTrace(step="persist_output", detail=f"写入 {output_path}"))

    return SlidevMvpResult(
        markdown=markdown,
        output_path=str(output_path),
        trace=trace,
        outline=state.outline,
    )
