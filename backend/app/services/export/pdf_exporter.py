"""PDF 导出 — Playwright 渲染 HTML → PDF

需要预装 Playwright: uv add playwright && uv run playwright install chromium
"""

import logging

logger = logging.getLogger(__name__)


async def export_pdf(html_content: str) -> bytes:
    """将 HTML 内容渲染为 PDF"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright 未安装。请运行: uv add playwright && uv run playwright install chromium"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.set_content(html_content, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )

        await browser.close()
        return pdf_bytes


def build_presentation_html(presentation_dict: dict) -> str:
    """从 Presentation JSON 构建完整 HTML（用于 PDF 渲染）"""
    slides = presentation_dict.get("slides", [])

    slides_html = ""
    for slide in slides:
        components_html = ""
        for comp in slide.get("components", []):
            pos = comp.get("position", {})
            style = comp.get("style", {})

            css_parts = [
                f"position: absolute",
                f"left: {pos.get('x', 0)}%",
                f"top: {pos.get('y', 0)}%",
                f"width: {pos.get('width', 50)}%",
                f"height: {pos.get('height', 20)}%",
            ]
            if style.get("fontSize"):
                css_parts.append(f"font-size: {style['fontSize']}px")
            if style.get("fontWeight"):
                css_parts.append(f"font-weight: {style['fontWeight']}")
            if style.get("color"):
                css_parts.append(f"color: {style['color']}")
            if style.get("textAlign"):
                css_parts.append(f"text-align: {style['textAlign']}")

            content = comp.get("content", "")
            # 将换行转为 <br>
            content_html = content.replace("\n", "<br>") if content else ""

            css = "; ".join(css_parts)
            components_html += f'<div style="{css}">{content_html}</div>\n'

        slides_html += f"""
        <div class="slide" style="position: relative; width: 100%; aspect-ratio: 16/9; background: white; page-break-after: always; overflow: hidden;">
            {components_html}
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif; }}
        .slide {{ margin: 0; }}
        @page {{ size: landscape; margin: 0; }}
    </style>
</head>
<body>
    {slides_html}
</body>
</html>"""
