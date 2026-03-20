import asyncio
from types import SimpleNamespace

from app.services.document import parser as parser_mod
from app.services.pipeline.graph import (
    OutlineSchemaError,
    PipelineState,
    stage_generate_outline,
    stage_parse_document,
)


class _FakeResult:
    def __init__(self, output_dict):
        self.output = SimpleNamespace(model_dump=lambda: output_dict)

    def usage(self):
        return SimpleNamespace(requests=1)


class _FakeOutlineAgent:
    def __init__(self, output_dict):
        self.output_dict = output_dict
        self.prompts: list[str] = []

    async def run(self, prompt: str):
        self.prompts.append(prompt)
        return _FakeResult(self.output_dict)


def test_extract_structure_signals_captures_images_tables_charts_and_timeline():
    markdown = """
# 标题

这里有一张图：
![alt](images/foo.png)
<img src="https://example.com/bar.jpg" />

| 指标 | 数值 |
| --- | --- |
| A | 1 |
| B | 2 |

2024-03-01 发布，2025年12月31日 截止，2025 Q3 复盘。
chart trend milestone timeline
"""
    signals = parser_mod.extract_structure_signals(markdown)
    assert signals["image_count"] >= 2
    assert signals["table_count"] >= 1
    assert "chart" in [s.lower() for s in signals.get("chart_keyword_hits", [])]
    assert signals.get("timeline_date_hits")
    assert signals.get("timeline_quarter_hits")


def test_parse_stage_writes_structure_signals_and_outline_prompt_includes_summary(monkeypatch):
    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod

        agent = _FakeOutlineAgent(
            {
                "narrative_arc": "测试叙事",
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "content_brief": "",
                        "key_points": ["测试"],
                        "suggested_slide_role": "cover",
                        "content_hints": [],
                    }
                ],
            }
        )
        # Be robust to module-level __getattr__ lazy agent creation (which may require API keys).
        monkeypatch.setattr(outline_mod, "get_outline_synthesizer_agent", lambda: agent, raising=True)
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "")

        state = PipelineState(
            raw_content="![alt](a.png)\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n2024-03-01",
            topic="测试主题",
            num_pages=1,
            outline={},
        )

        await stage_parse_document(state)
        assert "structure_signals" in state.document_metadata
        assert state.document_metadata["structure_signals"]["image_count"] == 1
        assert state.document_metadata["structure_signals"]["table_count"] >= 1

        await stage_generate_outline(state)
        assert agent.prompts
        prompt = agent.prompts[0]
        assert "结构信号摘要" in prompt
        assert "图片:" in prompt
        assert "表格:" in prompt

    asyncio.run(_case())


def test_outline_stage_uses_layer12_summaries_for_large_source_backed_documents(monkeypatch):
    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod
        from app.services.document import source_store

        agent = _FakeOutlineAgent(
            {
                "narrative_arc": "测试叙事",
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "content_brief": "摘要内容",
                        "key_points": ["测试"],
                        "suggested_slide_role": "cover",
                    }
                ],
            }
        )
        monkeypatch.setattr(outline_mod, "get_outline_synthesizer_agent", lambda: agent, raising=True)
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)
        monkeypatch.setattr(parser_mod, "estimate_tokens", lambda content: 12001)
        monkeypatch.setattr(
            source_store,
            "get_layer12_summaries",
            lambda source_ids: "Layer 1 summary\n\nLayer 2 summary" if source_ids else "",
        )

        state = PipelineState(
            raw_content="A" * 20000,
            source_ids=["src-1", "src-2"],
            topic="测试主题",
            num_pages=1,
            outline={},
        )
        state.document_metadata["source_hints"] = {"total_sources": 2, "images": 1}

        await stage_generate_outline(state)
        prompt = agent.prompts[0]
        assert "来源摘要（Layer 1/2）" in prompt
        assert "用户补充上下文（前 3000 字符）" in prompt
        assert state.document_metadata["outline_input"]["input_mode"] == "layer12_summary"
        assert state.document_metadata["outline_input"]["summary_source_count"] == 2

    asyncio.run(_case())


def test_outline_stage_truncates_large_documents_without_summaries(monkeypatch):
    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod
        from app.services.document import source_store

        agent = _FakeOutlineAgent(
            {
                "narrative_arc": "测试叙事",
                "items": [
                    {
                        "slide_number": 1,
                        "title": "封面",
                        "content_brief": "摘要内容",
                        "key_points": ["测试"],
                        "suggested_slide_role": "cover",
                    }
                ],
            }
        )
        monkeypatch.setattr(outline_mod, "get_outline_synthesizer_agent", lambda: agent, raising=True)
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)
        monkeypatch.setattr(parser_mod, "estimate_tokens", lambda content: 12001)
        monkeypatch.setattr(source_store, "get_layer12_summaries", lambda source_ids: "")

        state = PipelineState(
            raw_content="B" * 20000,
            source_ids=["src-1"],
            topic="测试主题",
            num_pages=1,
            outline={},
        )

        await stage_generate_outline(state)
        prompt = agent.prompts[0]
        assert "内容（前 12000 字符）" in prompt
        assert "用户补充上下文（前 3000 字符）" not in prompt
        assert state.document_metadata["outline_input"]["input_mode"] == "truncated_raw"

    asyncio.run(_case())


def test_outline_stage_accepts_alias_fields_and_normalizes_to_canonical_schema(monkeypatch):
    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod

        agent = _FakeOutlineAgent(
            {
                "narrative_arc": "测试叙事",
                "slides": [
                    {
                        "page_number": 1,
                        "title": "封面",
                        "summary": "核心摘要",
                        "bullet_points": ["要点一", "要点二"],
                        "references": "src-1",
                        "structure_hints": "chart",
                        "suggested_layout_category": "cover",
                    }
                ],
            }
        )
        monkeypatch.setattr(outline_mod, "get_outline_synthesizer_agent", lambda: agent, raising=True)
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)

        state = PipelineState(
            raw_content="短内容",
            topic="测试主题",
            num_pages=1,
            outline={},
        )

        await stage_generate_outline(state)
        item = state.outline["items"][0]
        assert item["slide_number"] == 1
        assert item["content_brief"] == "核心摘要"
        assert item["key_points"] == ["要点一", "要点二"]
        assert item["source_references"] == ["src-1"]
        assert item["content_hints"] == ["chart"]
        assert item["suggested_slide_role"] == "cover"

    asyncio.run(_case())


def test_outline_stage_wraps_schema_validation_failures(monkeypatch):
    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod

        agent = _FakeOutlineAgent(
            {
                "narrative_arc": "测试叙事",
                "slides": "not-a-slide-list",
            }
        )
        monkeypatch.setattr(outline_mod, "get_outline_synthesizer_agent", lambda: agent, raising=True)
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)

        state = PipelineState(
            raw_content="短内容",
            topic="测试主题",
            num_pages=1,
            outline={},
        )

        try:
            await stage_generate_outline(state)
        except OutlineSchemaError as exc:
            assert exc.schema_error_type == "ValidationError"
            assert "outline schema validation failed" in str(exc)
        else:
            raise AssertionError("expected outline schema error")

    asyncio.run(_case())
