import asyncio
from types import SimpleNamespace

from app.services.document import parser as parser_mod
from app.services.pipeline.graph import PipelineState, stage_generate_outline, stage_parse_document


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
    class _FakeResult:
        def __init__(self, output_dict):
            self.output = SimpleNamespace(model_dump=lambda: output_dict)

        def usage(self):
            return SimpleNamespace(requests=1)

    class _FakeOutlineAgent:
        def __init__(self):
            self.prompts: list[str] = []

        async def run(self, prompt: str):
            self.prompts.append(prompt)
            return _FakeResult(
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

    async def _case():
        from app.services.agents import outline_synthesizer as outline_mod

        agent = _FakeOutlineAgent()
        monkeypatch.setattr(outline_mod, "outline_synthesizer_agent", agent, raising=False)

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
