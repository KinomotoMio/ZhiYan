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
    from app.services.export.playwright_runtime import launch_chromium_with_auto_install

    async with async_playwright() as p:
        browser = await launch_chromium_with_auto_install(p)
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
    from app.services.export.html_renderer import render_presentation_html

    return render_presentation_html(presentation_dict)
