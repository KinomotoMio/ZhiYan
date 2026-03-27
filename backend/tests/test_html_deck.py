from app.services.html_deck import normalize_html_deck


def test_normalize_html_deck_preserves_section_attributes():
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>HTML 属性保真</title>
        <style>.slide-cover { color: white; }</style>
      </head>
      <body>
        <section
          class="slide-cover hero"
          id="cover-slide"
          style="background:#111827"
          aria-label="封面页"
          data-slide-id="legacy-cover"
          data-slide-title="旧标题"
          data-track="cover"
        >
          <h1>新标题</h1>
        </section>
      </body>
    </html>
    """

    normalized_html, meta, presentation = normalize_html_deck(
        html=raw_html,
        fallback_title="回退标题",
    )

    assert 'class="slide-cover hero"' in normalized_html
    assert 'id="cover-slide"' in normalized_html
    assert 'style="background:#111827"' in normalized_html
    assert 'aria-label="封面页"' in normalized_html
    assert 'data-track="cover"' in normalized_html
    assert 'data-slide-id="slide-1"' not in normalized_html
    assert normalized_html.count('data-slide-id="legacy-cover"') == 1
    assert normalized_html.count('data-slide-title="旧标题"') == 1
    assert meta["slides"][0]["slide_id"] == "legacy-cover"
    assert meta["slides"][0]["title"] == "旧标题"
    assert presentation["slides"][0]["slideId"] == "legacy-cover"


def test_normalize_html_deck_uses_query_param_bootstrap_and_preserves_speaker_notes():
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>HTML Notes</title>
      </head>
      <body>
        <section data-slide-id="slide-1" data-slide-title="封面">
          <div><h1>封面</h1></div>
        </section>
        <section data-slide-id="slide-2" data-slide-title="正文">
          <div><h2>正文</h2></div>
          <aside class="notes">旧注解</aside>
        </section>
      </body>
    </html>
    """

    normalized_html, meta, presentation = normalize_html_deck(
        html=raw_html,
        fallback_title="回退标题",
        existing_slides=[
            {"slideId": "slide-1", "speakerNotes": "封面注解"},
            {"slideId": "slide-2", "speakerNotes": "新的正文注解"},
        ],
    )

    assert "const query = new URLSearchParams(window.location.search);" in normalized_html
    assert "const previewMode = query.get('mode') === 'thumbnail' ? 'thumbnail' : 'interactive';" in normalized_html
    assert "hash: false" in normalized_html
    assert "deck.slide(initialSlide);" in normalized_html
    assert '<aside class="notes">封面注解</aside>' in normalized_html
    assert '<aside class="notes">新的正文注解</aside>' in normalized_html
    assert meta["slides"][0]["speaker_notes"] == "封面注解"
    assert meta["slides"][1]["speaker_notes"] == "新的正文注解"
    assert presentation["slides"][0]["speakerNotes"] == "封面注解"
    assert presentation["slides"][1]["speakerNotes"] == "新的正文注解"
