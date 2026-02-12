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

        # 等待字体加载
        await page.wait_for_timeout(500)

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
    title = presentation_dict.get("title", "演示文稿")
    total = len(slides)

    slides_html = ""
    for idx, slide in enumerate(slides):
        components_html = ""
        for comp in slide.get("components", []):
            pos = comp.get("position", {})
            style = comp.get("style", {})

            css_parts = [
                "position: absolute",
                f"left: {pos.get('x', 0)}%",
                f"top: {pos.get('y', 0)}%",
                f"width: {pos.get('width', 50)}%",
                f"height: {pos.get('height', 20)}%",
                "overflow: hidden",
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
            comp_type = comp.get("type", "text")

            if comp_type == "text":
                content_html = _render_text_content(content)
            elif comp_type in ("image", "chart"):
                content_html = (
                    f'<div style="display:flex;align-items:center;justify-content:center;'
                    f'height:100%;background:#f3f4f6;border-radius:4px;color:#9ca3af;font-size:14px;">'
                    f'[{comp_type}: {content or "占位"}]</div>'
                )
            else:
                content_html = content or ""

            css = "; ".join(css_parts)
            components_html += f'<div style="{css}">{content_html}</div>\n'

        # 页码
        page_num = idx + 1
        page_number_html = (
            f'<div style="position:absolute;bottom:2%;right:3%;'
            f'font-size:10px;color:#9ca3af;">{page_num} / {total}</div>'
        )

        slides_html += f"""
        <div class="slide" style="position:relative;width:100%;aspect-ratio:16/9;background:white;page-break-after:always;overflow:hidden;">
            {components_html}
            {page_number_html}
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', sans-serif; }}
        .slide {{ margin: 0; }}
        @page {{ size: landscape; margin: 0; }}
    </style>
</head>
<body>
    {slides_html}
</body>
</html>"""


def _render_text_content(content: str) -> str:
    """将文本内容渲染为 HTML，支持列表"""
    if not content:
        return ""
    lines = content.split("\n")
    html_parts = []
    for line in lines:
        line = line.strip()
        if not line:
            html_parts.append("<br>")
            continue
        # 无序列表
        import re
        bullet_match = re.match(r'^[•\-*]\s+(.*)', line)
        if bullet_match:
            html_parts.append(f'<div style="padding-left:1.5em;">• {_escape(bullet_match.group(1))}</div>')
            continue
        # 有序列表
        ordered_match = re.match(r'^(\d+)[.)]\s+(.*)', line)
        if ordered_match:
            html_parts.append(f'<div style="padding-left:1.5em;">{ordered_match.group(1)}. {_escape(ordered_match.group(2))}</div>')
            continue
        html_parts.append(f'<div>{_escape(line)}</div>')
    return "\n".join(html_parts)


def _escape(text: str) -> str:
    """HTML 转义"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
