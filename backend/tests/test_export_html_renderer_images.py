from app.services.export.html_renderer import render_presentation_html


def test_html_renderer_renders_metrics_with_image_url() -> None:
    html = render_presentation_html(
        {
            "title": "Demo",
            "slides": [
                {
                    "layoutId": "metrics-with-image",
                    "layoutType": "metrics-with-image",
                    "contentData": {
                        "title": "Key Metrics",
                        "metrics": [
                            {"value": "42%", "label": "Conversion"},
                            {"value": "7d", "label": "Payback"},
                        ],
                        "image": {
                            "source": "existing",
                            "prompt": "hero image",
                            "url": "https://example.com/hero.png",
                            "alt": "Hero",
                        },
                    },
                }
            ],
        }
    )

    assert "<img" in html
    assert "object-fit:cover" in html
    assert "https://example.com/hero.png" in html


def test_html_renderer_renders_image_and_description_placeholder_when_missing_url() -> None:
    html = render_presentation_html(
        {
            "title": "Demo",
            "slides": [
                {
                    "layoutId": "image-and-description",
                    "layoutType": "image-and-description",
                    "contentData": {
                        "title": "Customer Story",
                        "description": "Long form description used for placeholder test content.",
                        "image": {
                            "source": "user",
                            "prompt": "请上传产品截图",
                            "url": "",
                            "alt": "",
                        },
                    },
                }
            ],
        }
    )

    assert "<img" not in html
    assert "待用户补图/上传" in html
    assert "请上传产品截图" in html


def test_html_renderer_rejects_svg_data_urls() -> None:
    html = render_presentation_html(
        {
            "title": "Demo",
            "slides": [
                {
                    "layoutId": "metrics-with-image",
                    "layoutType": "metrics-with-image",
                    "contentData": {
                        "title": "Unsafe Inline Asset",
                        "metrics": [],
                        "image": {
                            "source": "existing",
                            "prompt": "hero image",
                            "url": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                            "alt": "",
                        },
                    },
                }
            ],
        }
    )

    assert "<img" not in html
    assert "待绑定现有素材" in html


def test_html_renderer_uses_slide_title_as_alt_fallback() -> None:
    html = render_presentation_html(
        {
            "title": "Demo",
            "slides": [
                {
                    "layoutId": "image-and-description",
                    "layoutType": "image-and-description",
                    "contentData": {
                        "title": "Customer Story",
                        "description": "Long form description used for placeholder test content.",
                        "image": {
                            "source": "existing",
                            "url": "https://example.com/customer-story.png",
                            "alt": "",
                        },
                    },
                }
            ],
        }
    )

    assert 'alt="Customer Story"' in html
