import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.harness.slidev_mvp import run_slidev_mvp


def test_run_slidev_mvp_writes_markdown(monkeypatch, tmp_path: Path):
    from app.services.harness import slidev_mvp as slidev_mod

    async def fake_parse(state):
        state.document_metadata = {"char_count": len(state.raw_content)}

    async def fake_outline(state):
        state.outline = {
            "items": [
                {
                    "slide_number": 1,
                    "title": "封面",
                    "content_brief": "一句话摘要",
                    "key_points": ["要点一"],
                    "suggested_slide_role": "cover",
                }
            ]
        }

    async def fake_execute_skill(skill_name, script_name, input_data, timeout=30):  # noqa: ARG001
        return {"markdown": "---\ntheme: default\n---\n# Demo\n"}

    monkeypatch.setattr(slidev_mod, "stage_parse_document", fake_parse)
    monkeypatch.setattr(slidev_mod, "stage_generate_outline", fake_outline)
    monkeypatch.setattr(slidev_mod, "execute_skill", fake_execute_skill)
    monkeypatch.setattr(slidev_mod.settings, "project_root", tmp_path)

    result = asyncio.run(
        run_slidev_mvp(
            topic="Demo",
            content="测试内容",
            num_pages=3,
        )
    )
    assert result.markdown.startswith("---")
    assert Path(result.output_path).exists()
    assert [item.step for item in result.trace] == [
        "parse_document",
        "generate_outline",
        "slidev_skill",
        "persist_output",
    ]


def test_slidev_mvp_api(monkeypatch):
    from app.api.v2 import harness as harness_api

    async def fake_run_slidev_mvp(*, topic, content, num_pages):  # noqa: ARG001
        return type(
            "Result",
            (),
            {
                "markdown": "# Demo\n",
                "output_path": "/tmp/demo.md",
                "outline": {"items": [{"slide_number": 1, "title": "封面"}]},
                "trace": [type("Trace", (), {"step": "outline", "detail": "done"})()],
            },
        )()

    monkeypatch.setattr(harness_api, "run_slidev_mvp", fake_run_slidev_mvp)

    client = TestClient(app)
    resp = client.post(
        "/api/v2/harness/slidev-mvp",
        json={"topic": "Demo", "content": "测试内容", "num_pages": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["markdown"] == "# Demo\n"
    assert body["output_path"] == "/tmp/demo.md"
    assert body["trace"][0]["step"] == "outline"
