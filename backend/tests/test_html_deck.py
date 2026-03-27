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
