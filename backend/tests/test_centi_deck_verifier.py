from app.services.generation.centi_deck_verifier import inspect_centi_deck_artifact


def _artifact(*slides: dict) -> dict:
    return {
        "title": "deck",
        "slides": list(slides),
    }


def _slide(slide_id: str, title: str, module_source: str) -> dict:
    return {
        "slideId": slide_id,
        "title": title,
        "plainText": "summary",
        "moduleSource": module_source,
    }


def test_centi_deck_verifier_flags_global_animation_targets():
    artifact = _artifact(
        _slide(
            "slide-1",
            "一页讲完所有背景",
            """
export default {
  render() {
    return `<section><div>这是一个非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长非常长的段落，用来模拟页面看起来像文档而不是演示页。</div></section>`;
  },
  enter(el, ctx) {
    ctx.gsap.from('h1', { opacity: 0 });
  }
};
""",
        )
    )

    issues = inspect_centi_deck_artifact(artifact)
    categories = {issue["category"] for issue in issues}
    assert "animation-scope" in categories


def test_centi_deck_verifier_flags_repetitive_structure_on_third_similar_slide():
    card_module = """
export default {
  render() {
    return `<section><h2>Title</h2><div class="card" style="display:grid;border-radius:1rem">A</div></section>`;
  }
};
"""
    issues = inspect_centi_deck_artifact(
        _artifact(
            _slide("slide-1", "第一页", card_module),
            _slide("slide-2", "第二页", card_module),
            _slide("slide-3", "第三页", card_module),
        )
    )

    repetitive = [issue for issue in issues if issue["category"] == "repetitive-structure"]
    assert len(repetitive) == 1
    assert repetitive[0]["slide_id"] == "slide-3"


def test_centi_deck_verifier_accepts_recipe_like_slide_without_issues():
    artifact = _artifact(
        _slide(
            "cover",
            "未来，你只需要会问",
            """
export default {
  render() {
    return `<section><h1 style="font-size:clamp(2rem,5vw,4rem)">未来，你只需要会问</h1><p>一句话结论</p></section>`;
  },
  enter(el, ctx) {
    ctx.gsap.from(el.querySelector('h1'), { opacity: 0, y: 20 });
  }
};
""",
        )
    )

    assert inspect_centi_deck_artifact(artifact) == []
