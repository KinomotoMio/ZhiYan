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
    expected = layout_verifier.VerificationResult(
        passed=True,
        issues=[],
        score=88,
    )
    fake_agent = _FakeAgent(expected)

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
    assert result.score == 88
    assert len(fake_agent.prompts) == 1
    assert isinstance(fake_agent.prompts[0], str)
    assert "请评估以下演示文稿的设计质量" in fake_agent.prompts[0]
