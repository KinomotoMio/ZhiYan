import asyncio

from app.models.slide import Slide
from app.services.agents import layout_verifier


def test_run_aesthetic_verification_falls_back_to_text(monkeypatch):
    seen_inputs = []

    async def fake_vision(slides, presentation_dict):  # noqa: ARG001
        raise RuntimeError("BrowserType.launch: Executable doesn't exist")

    async def fake_text(slides):
        seen_inputs.append(slides)
        return '{"score": 88, "issues": []}'

    monkeypatch.setattr(layout_verifier, "_run_text_aesthetic_verification", fake_text)
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
    assert len(seen_inputs) == 1
    assert seen_inputs[0][0].slide_id == "slide-1"


def test_run_aesthetic_verification_timeout_adds_warning_issue(monkeypatch):
    async def slow_vision(slides, presentation_dict):  # noqa: ARG001
        await asyncio.sleep(0.05)
        return '{"score": 99, "issues": []}'

    async def fake_text(slides):  # noqa: ARG001
        return '{"score": 82, "issues": []}'

    monkeypatch.setattr(layout_verifier, "_run_text_aesthetic_verification", fake_text)
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
    assert result.score == 82
    assert any("视觉截图评估超时" in issue.message for issue in result.issues)
