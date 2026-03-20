import asyncio
from types import SimpleNamespace

from app.models.slide import Slide
from app.services.agents import layout_verifier


class _FakeAgent:
    def __init__(self, output):
        self.output = output
        self.prompts = []

    async def run(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(output=self.output)


def test_run_aesthetic_verification_falls_back_to_text(monkeypatch):
    fake_agent = _FakeAgent('{"score": 88, "issues": []}')

    async def fake_vision(agent, slides, presentation_dict):  # noqa: ARG001
        raise RuntimeError("BrowserType.launch: Executable doesn't exist")

    monkeypatch.setattr(
        layout_verifier,
        "_get_aesthetic_verifier_agent",
        lambda: fake_agent,
    )
    monkeypatch.setattr(layout_verifier, "_run_vision_verification", fake_vision)

    slide = Slide(
        slideId="slide-1",
        layoutType="intro-slide",
        layoutId="intro-slide",
        contentData={"title": "封面"},
        components=[],
    )

    result = asyncio.run(
        layout_verifier.run_aesthetic_verification(
            [slide],
            presentation_dict={"title": "测试", "slides": [{}]},
        )
    )

    assert result is not None
    assert result.mode == "text"
    assert result.degraded_reason == "vision_error_fallback"
    assert result.result is not None
    assert result.result.score == 88
    assert len(fake_agent.prompts) == 1
    assert isinstance(fake_agent.prompts[0], str)
    assert "请评估以下演示文稿的设计质量" in fake_agent.prompts[0]
    assert any(issue.source == "vision_error_fallback" for issue in result.result.issues)


def test_run_aesthetic_verification_timeout_adds_warning_issue(monkeypatch):
    fake_agent = _FakeAgent('{"score": 82, "issues": []}')

    async def slow_vision(agent, slides, presentation_dict):  # noqa: ARG001
        await asyncio.sleep(0.05)
        return '{"score": 99, "issues": []}'

    monkeypatch.setattr(
        layout_verifier,
        "_get_aesthetic_verifier_agent",
        lambda: fake_agent,
    )
    monkeypatch.setattr(layout_verifier, "_run_vision_verification", slow_vision)

    slide = Slide(
        slideId="slide-1",
        layoutType="intro-slide",
        layoutId="intro-slide",
        contentData={"title": "封面"},
        components=[],
    )

    result = asyncio.run(
        layout_verifier.run_aesthetic_verification(
            [slide],
            presentation_dict={"title": "测试", "slides": [{}]},
            vision_timeout_seconds=0.01,
        )
    )

    assert result is not None
    assert result.mode == "text"
    assert result.degraded_reason == "vision_timeout_fallback"
    assert result.result is not None
    assert result.result.score == 82
    assert any("视觉截图评估超时" in issue.message for issue in result.result.issues)
    assert any(issue.source == "vision_timeout_fallback" for issue in result.result.issues)
