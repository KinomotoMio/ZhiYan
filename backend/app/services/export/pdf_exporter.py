"""PDF 导出 — Playwright 渲染 HTML → PDF

需要预装 Playwright: uv add playwright && uv run playwright install chromium
"""

import logging
from contextlib import suppress
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


async def _export_pdf_from_url(url: str) -> bytes:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright 未安装。请运行: uv add playwright && uv run playwright install chromium"
        )
    from app.services.export.playwright_runtime import launch_chromium_with_auto_install

    async with async_playwright() as p:
        browser = await launch_chromium_with_auto_install(p)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        await page.goto(url, wait_until="networkidle")

        # 等待字体加载
        await page.wait_for_timeout(500)

        pdf_bytes = await page.pdf(
            width="13.333in",
            height="7.5in",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )

        await browser.close()
        return pdf_bytes


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


async def export_runtime_viewer_pdf(
    *,
    document_html: str | None = None,
    viewer_path: str | Path | None = None,
) -> bytes:
    """Open the HTML runtime viewer in print mode and export it to PDF."""
    temp_path: Path | None = None
    try:
        if viewer_path is not None:
            resolved_path = Path(viewer_path).resolve()
        else:
            html = str(document_html or "").strip()
            if not html:
                raise RuntimeError("HTML runtime viewer 内容为空，无法导出 PDF。")
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
                handle.write(html)
                temp_path = Path(handle.name)
            resolved_path = temp_path.resolve()
        return await _export_pdf_from_url(f"{resolved_path.as_uri()}?mode=print")
    finally:
        if temp_path is not None:
            with suppress(Exception):
                temp_path.unlink()


def build_presentation_html(presentation_dict: dict) -> str:
    """从 Presentation JSON 构建完整 HTML（用于 PDF 渲染）"""
    from app.services.export.html_renderer import render_presentation_html

    return render_presentation_html(presentation_dict)
